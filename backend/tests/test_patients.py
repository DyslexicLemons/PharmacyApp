"""
test_patients.py — Access control and PHI redaction tests for the patients API.

Covers:
- GET /patients/ is admin-only (403 for non-admin, 200 for admin)
- GET /patients/ response omits dob and address (PatientSearchResult schema)
- GET /patients/search response omits dob and address
- GET /patients/{pid} creates a PATIENT_VIEWED audit log entry
- GET /patients/search creates a PATIENT_SEARCH audit log entry
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.auth import get_current_user
from app.database import get_db
from app.models import AuditLog, User
from tests.conftest import make_patient


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
