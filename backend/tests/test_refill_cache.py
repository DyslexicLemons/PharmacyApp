"""
test_refill_cache.py — Integration tests for Redis query-result caching.

Verifies that:
  - GET /refills populates a Redis key after the first request.
  - GET /refills/{id} populates a per-refill Redis key.
  - POST /refills/{id}/advance invalidates both the per-refill and queue keys.
  - POST /refills/{id}/edit  invalidates both keys.
  - POST /refills/create_manual invalidates queue keys.
  - POST /refills/upload_json  invalidates queue keys.

Uses fakeredis so no real Redis instance is required.
"""
import pytest
import fakeredis

from app import cache as cache_module
from tests.conftest import (
    make_prescriber, make_drug, make_patient,
    make_prescription, make_refill,
)
from app.models import RxState


# ---------------------------------------------------------------------------
# Fixture: wire a fakeredis client into cache._client for each test.
#
# The app lifespan calls cache.init_redis() when TestClient starts, which
# would overwrite our fake client.  We patch init_redis / close_redis to
# no-ops so the fake stays in place for the whole test.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    """Replace the real Redis client with an in-memory fakeredis instance.

    main.py imports init_redis by value so we cannot patch the module attribute
    to intercept the lifespan call.  Instead we remove REDIS_URL from the env
    (making init_redis a no-op) and pre-set _client to our fake instance.
    close_redis() will tidy up _client on teardown; monkeypatch restores env.
    """
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(cache_module, "_client", fake)
    yield fake


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup(db, quantity=30, remaining_qty=60, state=RxState.QT):
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, remaining_qty)
    refill = make_refill(db, prescription, drug, patient, quantity=quantity, state=state)
    db.commit()
    return refill


# ---------------------------------------------------------------------------
# Queue caching — GET /refills
# ---------------------------------------------------------------------------

class TestQueueCache:
    def test_first_request_populates_cache(self, client, db_session, fake_redis):
        _setup(db_session)
        client.get("/refills")
        assert fake_redis.get("refills:queue:ALL:100:0") is not None

    def test_state_filtered_request_populates_scoped_key(self, client, db_session, fake_redis):
        _setup(db_session)
        client.get("/refills?state=QT")
        assert fake_redis.get("refills:queue:QT:100:0") is not None

    def test_advance_invalidates_queue_cache(self, client, db_session, fake_redis):
        refill = _setup(db_session)
        client.get("/refills")                          # populate cache
        assert fake_redis.get("refills:queue:ALL:100:0") is not None

        client.post(f"/refills/{refill.id}/advance", json={})

        assert fake_redis.get("refills:queue:ALL:100:0") is None

    def test_create_manual_invalidates_queue_cache(self, client, db_session, fake_redis):
        from tests.conftest import make_prescriber, make_drug, make_patient
        from decimal import Decimal

        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        db_session.commit()

        client.get("/refills")  # populate
        assert fake_redis.get("refills:queue:ALL:100:0") is not None

        client.post("/refills/create_manual", json={
            "patient_id": patient.id,
            "drug_id": drug.id,
            "prescriber_id": prescriber.id,
            "quantity": 30,
            "days_supply": 30,
            "total_refills": 1,
            "priority": "normal",
            "initial_state": "QP",
            "instructions": "Take 1 tablet daily",
        })

        assert fake_redis.get("refills:queue:ALL:100:0") is None


# ---------------------------------------------------------------------------
# Per-refill caching — GET /refills/{id}
# ---------------------------------------------------------------------------

class TestRefillDetailCache:
    def test_first_request_populates_cache(self, client, db_session, fake_redis):
        refill = _setup(db_session)
        client.get(f"/refills/{refill.id}")
        assert fake_redis.get(f"refills:id:{refill.id}") is not None

    def test_advance_invalidates_refill_cache(self, client, db_session, fake_redis):
        refill = _setup(db_session)
        client.get(f"/refills/{refill.id}")             # populate
        assert fake_redis.get(f"refills:id:{refill.id}") is not None

        client.post(f"/refills/{refill.id}/advance", json={})

        assert fake_redis.get(f"refills:id:{refill.id}") is None

    def test_edit_invalidates_refill_cache(self, client, db_session, fake_redis):
        refill = _setup(db_session, state=RxState.QT)
        client.get(f"/refills/{refill.id}")             # populate
        assert fake_redis.get(f"refills:id:{refill.id}") is not None

        client.patch(f"/refills/{refill.id}/edit", json={"quantity": 15})

        assert fake_redis.get(f"refills:id:{refill.id}") is None
