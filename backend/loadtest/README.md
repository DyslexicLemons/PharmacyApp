# Load / perf testing

This directory measures the two things `backend/app/cache.py` and the refill
state-machine writes are implicitly betting on: that the query-result cache
(`_QUEUE_CACHE_TTL` / `_REFILL_CACHE_TTL` in `routers/refills.py`) meaningfully
cuts latency, and that `advance_refill`'s row lock + audit write hold up under
concurrent staff usage. Nothing here was in the repo before — it's a gap, not
a formality: caching and locking decisions that were reasoned about but never
measured against real concurrent load.

Uses [Locust](https://locust.io/) (already a dependency of the Python
backend, so no second toolchain to install). `locust` is in `requirements.txt`
under "Load/perf testing".

## Setup

From `backend/`, with the stack running (`docker compose up` or local
`uvicorn` + Postgres + Redis):

```
.venv/Scripts/pip install -r requirements.txt
```

You need an admin account. There is no static default — the app generates a
random admin password on first startup and logs it once (see
`_ensure_admin_user` in `app/main.py`). Grab that from the startup log, or
create/promote a user, then export it:

```
export LOADTEST_USERNAME=admin
export LOADTEST_PASSWORD=<from the startup log>
```

(PowerShell: `$env:LOADTEST_USERNAME = "admin"`, etc.)

Seed enough queue volume for the test to be meaningful — an empty or 10-row
queue hides both N+1 cost and cache behavior:

```
.venv/Scripts/python loadtest/seed_for_loadtest.py
```

Defaults to 20 prescribers, 150 patients, and ~3,000 prescriptions spread
randomly across every `RxState`. Override with `LOADTEST_PRESCRIBERS`,
`LOADTEST_PATIENTS`, `LOADTEST_PRESCRIPTIONS_BATCHES` if you want more.

## Running

Interactive, with the web UI (http://localhost:8089):

```
.venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000
```

Headless, for a fixed run you can diff against another run:

```
.venv/Scripts/locust -f loadtest/locustfile.py --host http://localhost:8000 \
    --headless -u 50 -r 10 -t 2m --csv=results/run1
```

- `-u 50` — 50 concurrent simulated users
- `-r 10` — ramp up 10 users/sec
- `-t 2m` — run for 2 minutes
- `--csv=results/run1` — writes `results/run1_stats.csv` (per-endpoint
  request count, failure count, and response-time percentiles) plus a
  `_stats_history.csv` time series

## What it exercises

| Task | Endpoint | Why |
|---|---|---|
| `view_queue` (weight 10) | `GET /refills` | The cached queue listing — varies `state`/`sort_by`/`offset` so requests spread across many cache keys instead of hammering one. |
| `view_refill_detail` (weight 6) | `GET /refills/{id}` | The cached single-refill lookup. |
| `check_conflict` (weight 2) | `GET /refills/check_conflict` | Uncached query, included as a baseline to compare cached vs. uncached latency in the same run. |
| `advance_refill` (weight 1) | `POST /refills/{id}/advance` | The write path: `with_for_update` row lock, audit insert, cache invalidation. Lower weight because in real usage reads vastly outnumber state transitions. |

Auth: the app rate-limits `POST /login` to 5/minute. Logging in per simulated
user would load-test the rate limiter instead of the app, so this test logs
in **once** at test start and shares the token across all simulated users —
matching how a real shift actually works (one login, session held all day).

`advance_refill` racing on the same row is expected to produce some 400s
(already moved by another simulated user) — that's the state machine working
as designed, not a bug. Only 5xx responses and connection failures count as
Locust failures; see the `catch_response` logic in `locustfile.py`.

## Measuring whether the cache actually helps

The point of this exercise isn't just "the API survives N req/s" — it's
turning the caching-layer decision from an assumption into a measured
number. Run the same headless command twice against freshly seeded data:

1. **Cache on** (normal config, `REDIS_URL` set): `--csv=results/cache_on`
2. **Cache off**: stop Redis (`docker compose stop redis`) or unset
   `REDIS_URL` and restart the backend — `cache.py` fails open to the
   database transparently, no code changes needed — then run again with
   `--csv=results/cache_off`

Compare the `GET /refills?state=[varied]` and `GET /refills/[id]` rows in the
two `_stats.csv` files (p50/p95/p99 latency, and requests/sec at the same
`-u`/`-r`). That delta is the actual, current benefit of the query cache on
this schema and this data volume — not a guess from reading `cache.py`.
