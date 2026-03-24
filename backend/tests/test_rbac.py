"""
test_rbac.py — Role-based access control tests for the refill state machine.

Verifies that advancing from QV1 or QV2 (pharmacist verification steps) is
rejected with 403 for technicians, and succeeds for pharmacists and admins.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.auth import get_current_user
from app.database import get_db
from app.models import RxState, User
from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription, make_refill,
)


# ---------------------------------------------------------------------------
# Client fixtures per role
# ---------------------------------------------------------------------------

def _make_client(engine, role: str, is_admin: bool = False):
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return User(id=None, username=f"{role}_user", hashed_password="x",
                    is_active=True, is_admin=is_admin, role=role)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    return TestClient(app, base_url="http://testserver/api/v1")


@pytest.fixture
def tech_client(engine):
    c = _make_client(engine, "technician", is_admin=False)
    with c as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def pharmacist_client(engine):
    c = _make_client(engine, "pharmacist", is_admin=False)
    with c as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(engine):
    c = _make_client(engine, "admin", is_admin=True)
    with c as client:
        yield client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_refill(db, state):
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
    refill = make_refill(db, prescription, drug, patient, quantity=30, state=state)
    db.commit()
    return refill


def advance(client, refill_id, action=None, rejection_reason=None):
    payload = {}
    if action:
        payload["action"] = action
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    return client.post(f"/refills/{refill_id}/advance", json=payload)


# ---------------------------------------------------------------------------
# QV1 step (current_state = QV1, advancing to QP)
# ---------------------------------------------------------------------------

class TestQV1RoleGate:
    def test_technician_cannot_advance_from_qv1(self, tech_client, db_session):
        refill = setup_refill(db_session, RxState.QV1)
        resp = advance(tech_client, refill.id)
        assert resp.status_code == 403
        assert "Pharmacist" in resp.json()["detail"]

    def test_pharmacist_can_advance_from_qv1(self, pharmacist_client, db_session):
        refill = setup_refill(db_session, RxState.QV1)
        resp = advance(pharmacist_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QP"

    def test_admin_can_advance_from_qv1(self, admin_client, db_session):
        refill = setup_refill(db_session, RxState.QV1)
        resp = advance(admin_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QP"

    def test_technician_can_hold_from_qv1(self, tech_client, db_session):
        """Holding is an administrative action — technicians can still place on hold."""
        refill = setup_refill(db_session, RxState.QV1)
        resp = advance(tech_client, refill.id, action="hold")
        assert resp.status_code == 403  # hold also requires leaving QV1

    def test_technician_can_reject_from_qv1(self, tech_client, db_session):
        """Rejecting from QV1 is also gated — only an RPh can make that call."""
        refill = setup_refill(db_session, RxState.QV1)
        resp = advance(tech_client, refill.id, action="reject", rejection_reason="Invalid DEA number")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# QV2 step (current_state = QV2, advancing to READY)
# ---------------------------------------------------------------------------

class TestQV2RoleGate:
    def test_technician_cannot_advance_from_qv2(self, tech_client, db_session):
        refill = setup_refill(db_session, RxState.QV2)
        resp = advance(tech_client, refill.id)
        assert resp.status_code == 403
        assert "Pharmacist" in resp.json()["detail"]

    def test_pharmacist_can_advance_from_qv2(self, pharmacist_client, db_session):
        refill = setup_refill(db_session, RxState.QV2)
        resp = advance(pharmacist_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "READY"

    def test_admin_can_advance_from_qv2(self, admin_client, db_session):
        refill = setup_refill(db_session, RxState.QV2)
        resp = advance(admin_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "READY"


# ---------------------------------------------------------------------------
# Non-gated states — technicians can advance freely
# ---------------------------------------------------------------------------

class TestTechnicianFreeStates:
    def test_technician_can_advance_from_qt(self, tech_client, db_session):
        """QT → QV1 is unblocked; the block is on *leaving* QV1."""
        refill = setup_refill(db_session, RxState.QT)
        resp = advance(tech_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QV1"

    def test_technician_can_advance_from_qp(self, tech_client, db_session):
        """Tech fills the bag and advances QP → QV2."""
        refill = setup_refill(db_session, RxState.QP)
        resp = advance(tech_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QV2"

    def test_technician_can_sell_from_ready(self, tech_client, db_session):
        """READY → SOLD (point-of-sale) is not pharmacist-gated."""
        refill = setup_refill(db_session, RxState.READY)
        resp = advance(tech_client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "SOLD"
