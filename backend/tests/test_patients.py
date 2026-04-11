"""
test_patients.py — Access control and PHI redaction tests for the patients API.

Covers:
- GET /patients/ is admin-only (403 for non-admin, 200 for admin)
- GET /patients/ response omits dob and address (PatientSearchResult schema)
- GET /patients/search response omits dob and address
- GET /patients/{pid} creates a PATIENT_VIEWED audit log entry
- GET /patients/search creates a PATIENT_SEARCH audit log entry
- DELETE /patients/{pid} happy path, cascade, active-refill block, audit log
"""
import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.auth import get_current_user
from app.database import get_db
from app.models import AuditLog, Patient, Prescription, Refill, RefillHist, PatientInsurance, RxState, User
from app.routers.patients import _get_latest_refill_for_prescription
from tests.conftest import (
    make_patient, make_drug, make_prescriber, make_prescription,
    make_refill, make_insurance, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Non-admin client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def non_admin_client(engine):
    """TestClient whose current user is a regular (non-admin) user."""
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    def override_get_current_user():
        return User(id=None, username="tech_user", hashed_password="x",
                    is_active=True, is_admin=False, role="technician")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(app, base_url="http://testserver/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Admin gate on GET /patients/
# ---------------------------------------------------------------------------

class TestPatientListAdminGate:
    def test_non_admin_gets_403(self, non_admin_client, db_session):
        resp = non_admin_client.get("/patients")
        assert resp.status_code == 403
        assert "Admin" in resp.json()["detail"]

    def test_admin_gets_200(self, client, db_session):
        resp = client.get("/patients")
        assert resp.status_code == 200

    def test_admin_response_has_no_dob_or_address(self, client, db_session):
        make_patient(db_session)
        db_session.commit()
        resp = client.get("/patients?limit=10")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        for item in items:
            assert "dob" not in item, "dob must not appear in list response"
            assert "address" not in item, "address must not appear in list response"
            assert "id" in item
            assert "first_name" in item
            assert "last_name" in item


# ---------------------------------------------------------------------------
# Search returns redacted schema
# ---------------------------------------------------------------------------

class TestPatientSearchRedaction:
    def test_search_response_has_no_dob_or_address(self, client, db_session):
        make_patient(db_session, first="John", last="Doe")
        db_session.commit()
        resp = client.get("/patients/search", params={"name": "Doe,Joh"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        for item in results:
            assert "dob" not in item, "dob must not appear in search response"
            assert "address" not in item, "address must not appear in search response"
            assert "id" in item
            assert "first_name" in item
            assert "last_name" in item

    def test_search_creates_audit_entry(self, client, db_session):
        make_patient(db_session, first="Jane", last="Smith")
        db_session.commit()
        resp = client.get("/patients/search", params={"name": "Smith,Jan"})
        assert resp.status_code == 200
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "PATIENT_SEARCH"
        ).first()
        assert audit is not None
        assert "Smith,Jan" in audit.details

    def test_non_admin_can_search(self, non_admin_client, db_session):
        """Search is available to all authenticated users (not admin-gated)."""
        make_patient(db_session, first="Alice", last="Brown")
        db_session.commit()
        resp = non_admin_client.get("/patients/search", params={"name": "Brown,Ali"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /patients/{pid} audit logging
# ---------------------------------------------------------------------------

class TestPatientDetailAudit:
    def test_patient_view_creates_audit_entry(self, client, db_session):
        patient = make_patient(db_session, first="Bob", last="Jones")
        db_session.commit()
        resp = client.get(f"/patients/{patient.id}")
        assert resp.status_code == 200
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "PATIENT_VIEWED",
            AuditLog.entity_id == patient.id,
        ).first()
        assert audit is not None
        assert "Jones" in audit.details

    def test_patient_detail_still_returns_full_demographics(self, client, db_session):
        """Full PHI is still returned on the individual profile endpoint."""
        patient = make_patient(db_session, first="Carol", last="White")
        db_session.commit()
        resp = client.get(f"/patients/{patient.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert "dob" in body
        assert "address" in body


# ---------------------------------------------------------------------------
# DELETE /patients/{pid}
# ---------------------------------------------------------------------------

class TestPatientDelete:
    def test_delete_patient_no_prescriptions_returns_204(self, client, db_session):
        """A patient with no prescriptions is deleted cleanly."""
        patient = make_patient(db_session, first="Empty", last="Record")
        db_session.commit()
        pid = patient.id

        resp = client.delete(f"/patients/{pid}")
        assert resp.status_code == 204

        db_session.expire_all()
        assert db_session.get(Patient, pid) is None

    def test_delete_patient_404_for_missing_patient(self, client, db_session):
        resp = client.delete("/patients/999999")
        assert resp.status_code == 404

    def test_delete_patient_writes_audit_log(self, client, db_session):
        patient = make_patient(db_session, first="Audit", last="Trail")
        db_session.commit()

        client.delete(f"/patients/{patient.id}")

        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "PATIENT_DELETED"
        ).first()
        assert audit is not None
        assert "Trail" in audit.details

    def test_delete_cascades_prescriptions_refills_insurance(self, client, db_session):
        """All child records are removed when the patient is deleted."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        insurance_co = make_insurance(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        # A completed (SOLD) refill — should not block deletion
        make_refill(db_session, rx, drug, patient, state=RxState.SOLD)
        make_patient_insurance(db_session, patient, insurance_co)
        db_session.commit()
        pid = patient.id

        resp = client.delete(f"/patients/{pid}")
        assert resp.status_code == 204

        # expunge_all clears the identity map so stale ORM references (created
        # by make_* helpers) don't trigger phantom UPDATEs on teardown after the
        # endpoint bulk-deleted them with synchronize_session=False.
        db_session.expunge_all()
        assert db_session.query(Patient).filter(Patient.id == pid).count() == 0
        assert db_session.query(Prescription).filter(Prescription.patient_id == pid).count() == 0
        assert db_session.query(Refill).filter(Refill.patient_id == pid).count() == 0
        assert db_session.query(PatientInsurance).filter(PatientInsurance.patient_id == pid).count() == 0

    @pytest.mark.parametrize("blocking_state", [
        RxState.QT, RxState.QV1, RxState.QP, RxState.QV2,
        RxState.READY, RxState.HOLD, RxState.SCHEDULED,
    ])
    def test_delete_blocked_by_active_refill(self, client, db_session, blocking_state):
        """409 is returned for each active workflow state."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        make_refill(db_session, rx, drug, patient, state=blocking_state)
        db_session.commit()

        resp = client.delete(f"/patients/{patient.id}")
        assert resp.status_code == 409
        assert "active prescription" in resp.json()["detail"].lower()

        # Patient must still exist
        db_session.expire_all()
        assert db_session.get(Patient, patient.id) is not None

    def test_delete_allowed_when_only_rejected_refills(self, client, db_session):
        """REJECTED refills are not active — deletion should succeed."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        make_refill(db_session, rx, drug, patient, state=RxState.REJECTED)
        db_session.commit()

        resp = client.delete(f"/patients/{patient.id}")
        assert resp.status_code == 204
        db_session.expunge_all()  # prevent stale ORM references from causing teardown errors


# ---------------------------------------------------------------------------
# _get_latest_refill_for_prescription — next_pickup date type regression
# ---------------------------------------------------------------------------

class TestGetLatestRefillNextPickup:
    """
    Regression tests for the bug where next_pickup was computed as a timezone-aware
    datetime (from RefillHist.sold_date + timedelta) instead of a plain date,
    causing a Pydantic ValidationError on LatestRefillOut.
    """

    def _make_hist(self, db, rx, drug, patient, sold_date, days_supply=30):
        hist = RefillHist(
            prescription_id=rx.id,
            patient_id=patient.id,
            drug_id=drug.id,
            quantity=30,
            days_supply=days_supply,
            total_cost=Decimal("15.00"),
            sold_date=sold_date,
            completed_date=sold_date,
        )
        db.add(hist)
        db.flush()
        return hist

    def test_next_pickup_is_date_not_datetime(self, db_session):
        """next_pickup must be a date even when sold_date is a tz-aware datetime."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        # Simulate a sold_date with a non-midnight time (as stored in prod)
        sold_dt = datetime(2026, 3, 1, 14, 23, 45, tzinfo=timezone.utc)
        self._make_hist(db_session, rx, drug, patient, sold_date=sold_dt, days_supply=30)
        db_session.commit()

        result = _get_latest_refill_for_prescription(db_session, rx.id)

        assert result is not None
        assert isinstance(result.next_pickup, date)
        assert not isinstance(result.next_pickup, datetime)  # date, not datetime subclass

    def test_next_pickup_value_is_correct(self, db_session):
        """next_pickup = sold_date + days_supply, rounded to calendar date."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        sold_dt = datetime(2026, 3, 1, 14, 23, 45, tzinfo=timezone.utc)
        self._make_hist(db_session, rx, drug, patient, sold_date=sold_dt, days_supply=30)
        db_session.commit()

        result = _get_latest_refill_for_prescription(db_session, rx.id)

        assert result.next_pickup == date(2026, 3, 31)

    def test_next_pickup_none_when_no_sold_date(self, db_session):
        """If sold_date is NULL, next_pickup should be None (not raise)."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        self._make_hist(db_session, rx, drug, patient, sold_date=None, days_supply=30)
        db_session.commit()

        result = _get_latest_refill_for_prescription(db_session, rx.id)

        assert result is not None
        assert result.next_pickup is None

    def test_returns_none_when_no_refills(self, db_session):
        """No active refills and no history → None."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        db_session.commit()

        result = _get_latest_refill_for_prescription(db_session, rx.id)

        assert result is None

    def test_active_refill_returns_state_not_next_pickup(self, db_session):
        """When an active (non-SOLD) refill exists, state is set and next_pickup is None."""
        drug = make_drug(db_session)
        prescriber = make_prescriber(db_session)
        patient = make_patient(db_session)
        rx = make_prescription(db_session, patient, drug, prescriber)
        make_refill(db_session, rx, drug, patient, state=RxState.QT)
        db_session.commit()

        result = _get_latest_refill_for_prescription(db_session, rx.id)

        assert result is not None
        assert result.state == "QT"
        assert result.next_pickup is None
