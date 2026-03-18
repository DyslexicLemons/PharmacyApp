"""
test_queue_summary.py — tests for GET /api/v1/admin/queue-summary.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user
from app.database import get_db
from app.models import User, RxState

from .conftest import (
    make_drug, make_patient, make_prescriber,
    make_prescription, make_refill,
)


# ---------------------------------------------------------------------------
# Non-admin client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def non_admin_client(engine):
    from sqlalchemy.orm import sessionmaker
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    def override_non_admin():
        return User(id=None, username="regular", hashed_password="x",
                    is_active=True, is_admin=False)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_non_admin
    with TestClient(app, base_url="http://testserver/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_queue_summary_empty_db(client):
    """Empty database returns all-zero counts."""
    resp = client.get("/queue-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_active"] == 0
    assert body["overdue_scheduled"] == 0
    assert body["expiring_soon_30d"] == 0
    counts = body["refills_by_state"]
    for state in ("QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED", "REJECTED"):
        assert counts[state] == 0
    assert "generated_at" in body


def test_queue_summary_state_counts(client, db_session):
    """Refills in various states are counted correctly."""
    db = db_session
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    rx = make_prescription(db, patient, drug, prescriber, 300, 300)

    make_refill(db, rx, drug, patient, state=RxState.QT)
    make_refill(db, rx, drug, patient, state=RxState.QT)
    make_refill(db, rx, drug, patient, state=RxState.QV1)
    make_refill(db, rx, drug, patient, state=RxState.HOLD)
    db.commit()

    resp = client.get("/queue-summary")
    assert resp.status_code == 200
    body = resp.json()
    counts = body["refills_by_state"]
    assert counts["QT"] == 2
    assert counts["QV1"] == 1
    assert counts["HOLD"] == 1
    assert counts["QP"] == 0
    assert body["total_active"] == 4


def test_queue_summary_overdue_scheduled(client, db_session):
    """SCHEDULED refills with due_date in the past appear in overdue_scheduled."""
    db = db_session
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    rx = make_prescription(db, patient, drug, prescriber, 300, 300)

    yesterday = date.today() - timedelta(days=1)
    tomorrow = date.today() + timedelta(days=1)

    make_refill(db, rx, drug, patient, state=RxState.SCHEDULED, due_date=yesterday)
    make_refill(db, rx, drug, patient, state=RxState.SCHEDULED, due_date=yesterday)
    make_refill(db, rx, drug, patient, state=RxState.SCHEDULED, due_date=tomorrow)
    db.commit()

    resp = client.get("/queue-summary")
    assert resp.status_code == 200
    assert resp.json()["overdue_scheduled"] == 2


def test_queue_summary_expiring_soon(client, db_session):
    """Active prescriptions expiring within 30 days appear in expiring_soon_30d."""
    db = db_session
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)

    # Expiring in 15 days — should be counted
    rx_soon = make_prescription(db, patient, drug, prescriber)
    rx_soon.expiration_date = date.today() + timedelta(days=15)

    # Expiring in 60 days — should NOT be counted
    rx_later = make_prescription(db, patient, drug, prescriber)
    rx_later.expiration_date = date.today() + timedelta(days=60)

    # Already expired — should NOT be counted (is_inactive would be True after task runs,
    # but expiration_date < today means it's past the window regardless)
    rx_past = make_prescription(db, patient, drug, prescriber)
    rx_past.expiration_date = date.today() - timedelta(days=1)

    # Inactive but expiring soon — should NOT be counted
    rx_inactive = make_prescription(db, patient, drug, prescriber)
    rx_inactive.expiration_date = date.today() + timedelta(days=5)
    rx_inactive.is_inactive = True

    db.commit()

    resp = client.get("/queue-summary")
    assert resp.status_code == 200
    assert resp.json()["expiring_soon_30d"] == 1


def test_queue_summary_requires_admin(non_admin_client):
    """Non-admin users receive 403."""
    resp = non_admin_client.get("/queue-summary")
    assert resp.status_code == 403
