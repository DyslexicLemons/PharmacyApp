"""
seed_for_loadtest.py — populate enough queue volume for a meaningful load test.

The refill queue endpoints being load-tested (GET /refills, GET /refills/{id})
are only interesting under load if the queue actually holds a realistic number
of rows across every state — an empty or 10-row table hides both N+1 query
cost and cache behavior. This script drives the existing admin
/commands/generate_* endpoints (see backend/app/routers/admin.py) instead of
writing to the database directly, so it exercises the same code path a real
operator would and stays valid if those endpoints change shape.

Usage (run from backend/):
    .venv/Scripts/python loadtest/seed_for_loadtest.py

Requires an admin account. Credentials are never hardcoded — provide them via
env vars (matching the no-hardcoded-credentials rule in backend/.env.example):
    LOADTEST_BASE_URL   default: http://localhost:8000/api/v1
    LOADTEST_USERNAME    required
    LOADTEST_PASSWORD    required
    LOADTEST_PRESCRIBERS default: 20
    LOADTEST_PATIENTS    default: 150
    LOADTEST_PRESCRIPTIONS_BATCHES default: 6   (500 per batch, the endpoint's cap)
"""

from __future__ import annotations

import os
import sys

import httpx

BASE_URL = os.environ.get("LOADTEST_BASE_URL", "http://localhost:8000/api/v1")
USERNAME = os.environ.get("LOADTEST_USERNAME")
PASSWORD = os.environ.get("LOADTEST_PASSWORD")

PRESCRIBERS = int(os.environ.get("LOADTEST_PRESCRIBERS", "20"))
PATIENTS = int(os.environ.get("LOADTEST_PATIENTS", "150"))
PRESCRIPTION_BATCHES = int(os.environ.get("LOADTEST_PRESCRIPTIONS_BATCHES", "6"))
PRESCRIPTIONS_PER_BATCH = 500  # /commands/generate_prescriptions caps at 500


def main() -> None:
    if not USERNAME or not PASSWORD:
        print(
            "LOADTEST_USERNAME and LOADTEST_PASSWORD must be set — see the "
            "module docstring. Refusing to guess or fall back to a default "
            "account.",
            file=sys.stderr,
        )
        sys.exit(1)

    with httpx.Client(base_url=BASE_URL, timeout=30.0) as client:
        resp = client.post("/login", json={"username": USERNAME, "password": PASSWORD})
        resp.raise_for_status()
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        print(f"Generating {PRESCRIBERS} prescribers...")
        r = client.post("/commands/generate_prescribers", json={"count": PRESCRIBERS}, headers=headers)
        r.raise_for_status()
        print(f"  -> {r.json()}")

        print(f"Generating {PATIENTS} patients...")
        r = client.post("/commands/generate_patients", json={"count": PATIENTS}, headers=headers)
        r.raise_for_status()
        print(f"  -> {r.json()}")

        total_refills = 0
        for i in range(PRESCRIPTION_BATCHES):
            print(f"Generating prescriptions batch {i + 1}/{PRESCRIPTION_BATCHES} (state=RANDOM)...")
            r = client.post(
                "/commands/generate_prescriptions",
                json={"count": PRESCRIPTIONS_PER_BATCH, "state": "RANDOM"},
                headers=headers,
            )
            r.raise_for_status()
            body = r.json()
            total_refills += body["refills_created"]
            print(f"  -> {body}")

        print(f"\nDone. ~{total_refills} active refills spread across queue states.")


if __name__ == "__main__":
    main()
