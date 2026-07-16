"""
test_prescription_lock.py — Prescription view-lock behavior (app/cache.py).

Covers:
  - Happy path: acquire / status / release via the /{id}/lock endpoints.
  - Fail-open: Redis never reachable this run -> edits proceed uninterrupted
    (matches the app-wide caching/quick-code fallback mode).
  - Fail-closed: an established Redis client that raises mid-operation ->
    PrescriptionLockUnavailable -> 503, instead of silently letting the
    concurrency guard disappear (see PrescriptionLockUnavailable in cache.py).

Uses fakeredis so no real Redis instance is required for the fail-closed cases.
"""
import pytest
import fakeredis

from app import cache as cache_module
from tests.conftest import make_prescriber, make_drug, make_patient, make_prescription


def _setup_prescription(db):
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber)
    db.commit()
    return prescription


# ---------------------------------------------------------------------------
# Fixture: wire a fakeredis client into cache._client (mirrors test_refill_cache.py).
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis(monkeypatch):
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(cache_module, "_client", fake)
    yield fake


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestLockHappyPath:
    def test_acquire_then_status_then_release(self, client, db_session, fake_redis):
        rx = _setup_prescription(db_session)

        resp = client.post(f"/prescriptions/{rx.id}/lock")
        assert resp.status_code == 200

        status = client.get(f"/prescriptions/{rx.id}/lock")
        assert status.status_code == 200

        resp = client.delete(f"/prescriptions/{rx.id}/lock")
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Fail-open: Redis never reachable this run
# ---------------------------------------------------------------------------

class TestFailOpenWhenRedisNeverConfigured:
    """Forces cache._client to None (regardless of whether this machine has a
    real Redis running), the same as a dev/CI box with no Redis at all.
    Prescription edits must keep working, matching the existing
    cache/quick-code fallback behavior."""

    def test_update_prescription_succeeds_without_redis(self, client, db_session, monkeypatch):
        monkeypatch.setattr(cache_module, "_client", None)
        rx = _setup_prescription(db_session)

        resp = client.patch(f"/prescriptions/{rx.id}", json={"instructions": "Take with food"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Fail-closed: an established Redis connection breaks mid-operation
# ---------------------------------------------------------------------------

class TestFailClosedOnRedisBlip:
    def test_acquire_lock_endpoint_returns_503(self, client, db_session, fake_redis, monkeypatch):
        rx = _setup_prescription(db_session)

        def _boom(*args, **kwargs):
            raise ConnectionError("simulated Redis blip")

        monkeypatch.setattr(fake_redis, "set", _boom)

        resp = client.post(f"/prescriptions/{rx.id}/lock")
        assert resp.status_code == 503

    def test_update_prescription_returns_503_instead_of_silently_succeeding(
        self, client, db_session, fake_redis, monkeypatch
    ):
        rx = _setup_prescription(db_session)

        def _boom(*args, **kwargs):
            raise ConnectionError("simulated Redis blip")

        monkeypatch.setattr(fake_redis, "get", _boom)

        resp = client.patch(f"/prescriptions/{rx.id}", json={"instructions": "Take with food"})
        assert resp.status_code == 503

    def test_release_lock_stays_fail_open_on_redis_blip(self, client, db_session, fake_redis, monkeypatch):
        """Releasing is low-risk (TTL self-heals), so it must not 503."""
        rx = _setup_prescription(db_session)

        def _boom(*args, **kwargs):
            raise ConnectionError("simulated Redis blip")

        monkeypatch.setattr(fake_redis, "get", _boom)

        resp = client.delete(f"/prescriptions/{rx.id}/lock")
        assert resp.status_code == 204
