"""
locustfile.py — load/perf test for the refill queue read path and the
advance-refill write path.

Why these endpoints specifically:

- GET /refills (the queue) and GET /refills/{id} are the two "hot read"
  endpoints cache.py explicitly calls out (_QUEUE_CACHE_TTL / _REFILL_CACHE_TTL,
  see backend/app/routers/refills.py). Hitting them concurrently is what
  actually shows whether the 30-60s TTL cache is earning its keep, versus a
  hunch that it should.
- POST /refills/{id}/advance takes a row lock (`with_for_update`), writes an
  audit row, and invalidates cache keys on every call. It's the endpoint most
  likely to show contention under concurrent staff usage, which read-only
  tests can't surface.

Auth strategy: the app rate-limits POST /login to 5/minute (see
backend/app/routers/auth.py). Logging in per simulated user would immediately
exhaust that budget and load-test the rate limiter instead of the app. Real
staff log in once and keep a session for their shift, so this test does the
same: one login at test start (via the test_start event), token shared by
every simulated user for the run.

Usage (run from backend/), against a server already seeded via
seed_for_loadtest.py:

    LOADTEST_USERNAME=... LOADTEST_PASSWORD=... \\
        .venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000

Headless, for CSV output to compare runs (e.g. cache on vs. Redis stopped):

    LOADTEST_USERNAME=... LOADTEST_PASSWORD=... \\
        .venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000 \\
        --headless -u 50 -r 10 -t 2m --csv=results/cache_on
"""

from __future__ import annotations

import os
import random

from locust import HttpUser, task, between, events

USERNAME = os.environ.get("LOADTEST_USERNAME")
PASSWORD = os.environ.get("LOADTEST_PASSWORD")

QUEUE_STATES = ["QT", "QV1", "QP", "QV2", "READY", "ALL"]

# Populated once in on_test_start, read (never written) by every User instance.
_shared = {"token": None, "refill_ids": {"QT": [], "QV1": [], "QP": [], "QV2": []}}


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    if not USERNAME or not PASSWORD:
        raise SystemExit(
            "LOADTEST_USERNAME and LOADTEST_PASSWORD must be set in the "
            "environment — this test never guesses or hardcodes credentials."
        )

    import httpx

    with httpx.Client(base_url=environment.host, timeout=30.0) as client:
        resp = client.post("/api/v1/login", json={"username": USERNAME, "password": PASSWORD})
        resp.raise_for_status()
        _shared["token"] = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {_shared['token']}"}

        # Grab a working set of real refill IDs per state so advance_refill
        # tasks hit rows that actually exist and are in a state that accepts
        # the transition, instead of a synthetic ID that 404s every time.
        for state in _shared["refill_ids"]:
            resp = client.get(
                "/api/v1/refills", params={"state": state, "limit": 100}, headers=headers
            )
            resp.raise_for_status()
            _shared["refill_ids"][state] = [item["id"] for item in resp.json()["items"]]


class PharmacyUser(HttpUser):
    """Simulates a logged-in pharmacy staff member working the refill queue."""

    wait_time = between(0.5, 2.5)

    def on_start(self):
        if not _shared["token"]:
            raise RuntimeError("test_start listener did not run before a User started")
        self.client.headers["Authorization"] = f"Bearer {_shared['token']}"

    @task(10)
    def view_queue(self):
        """Hits the cached queue listing (_QUEUE_CACHE_TTL=30s) with varied params.

        Varying state/sort/offset spreads requests across many cache keys —
        deliberately so, to see the DB-query cost on cache misses, not just
        the best case of one key getting hammered.
        """
        state = random.choice(QUEUE_STATES)
        sort_by = random.choice(["due", "qty", "priority", "state"])
        offset = random.choice([0, 15, 30])
        with self.client.get(
            "/api/v1/refills",
            params={"state": state, "limit": 15, "offset": offset, "sort_by": sort_by},
            name="/refills?state=[varied]",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"unexpected status {resp.status_code}")

    @task(6)
    def view_refill_detail(self):
        """Hits the cached single-refill lookup (_REFILL_CACHE_TTL=60s)."""
        pool = [rid for ids in _shared["refill_ids"].values() for rid in ids]
        if not pool:
            return
        rx_id = random.choice(pool)
        with self.client.get(
            f"/api/v1/refills/{rx_id}", name="/refills/[id]", catch_response=True
        ) as resp:
            # A 404 here means the row moved on (e.g. archived to SOLD) since
            # the working set was captured — expected under concurrent writers,
            # not a failure of the endpoint itself.
            if resp.status_code not in (200, 404):
                resp.failure(f"unexpected status {resp.status_code}")

    @task(1)
    def advance_refill(self):
        """Hits the write path: row lock + audit insert + cache invalidation.

        Concurrent users racing to advance the same refill will produce some
        400s (already moved) — that's the state machine doing its job, not a
        bug, so only 5xx/connection failures are marked as failures.
        """
        state = random.choice(["QT", "QV1", "QP", "QV2"])
        pool = _shared["refill_ids"][state]
        if not pool:
            return
        rx_id = random.choice(pool)
        with self.client.post(
            f"/api/v1/refills/{rx_id}/advance",
            json={},
            name="/refills/[id]/advance",
            catch_response=True,
        ) as resp:
            if resp.status_code >= 500:
                resp.failure(f"server error {resp.status_code}")
            elif resp.status_code in (200, 400, 403, 404, 409, 423):
                resp.success()
            else:
                resp.failure(f"unexpected status {resp.status_code}")

    @task(2)
    def check_conflict(self):
        """Uncached query path (check_refill_conflict) for comparison against the cached ones."""
        pool = [rid for ids in _shared["refill_ids"].values() for rid in ids]
        if not pool:
            return
        # patient_id/drug_id don't need to correspond to a real refill for
        # this to exercise the query — it's an existence/duplicate check.
        self.client.get(
            "/api/v1/refills/check_conflict",
            params={"patient_id": random.randint(1, 150), "drug_id": random.randint(1, 20)},
            name="/refills/check_conflict",
        )
