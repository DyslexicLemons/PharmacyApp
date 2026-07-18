"""
test_eprescribe.py — Tests for the external e-prescribing (eRx) intake API.

Covers: OAuth2 client-credentials token issuance, NewRx submission landing
in QT, prescriber auto-creation, patient/drug must-exist 404s, token_type
cross-rejection between staff and clinic tokens (critical given both are
signed with the same JWT_SECRET_KEY), queue cache invalidation, and admin
clinic-client management.
"""
from datetime import datetime, timedelta, timezone

import fakeredis
import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app import cache as cache_module
from app.main import app
from app.auth import ALGORITHM, SECRET_KEY, create_access_token, create_client_token, get_current_user
from app.database import get_db
from app.models import AuditLog, ERxClient, Prescriber, Refill, RxState, User
from tests.conftest import make_prescriber, make_drug, make_patient, make_erx_client


# ---------------------------------------------------------------------------
# fakeredis — mirrors test_refill_cache.py so queue-invalidation is testable
# without a real Redis instance.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    server = fakeredis.FakeServer()
    fake = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setattr(cache_module, "_client", fake)
    yield fake


# ---------------------------------------------------------------------------
# raw_client — only get_db is overridden, so get_current_user/get_current_client
# run for real. Needed to exercise actual JWT verification end-to-end (the
# standard `client` fixture bypasses get_current_user entirely).
# ---------------------------------------------------------------------------

@pytest.fixture
def raw_client(engine):
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, base_url="http://testserver/api/v1") as c:
        yield c
    app.dependency_overrides.clear()


def _valid_newrx_payload(npi=1234567890):
    return {
        "patient": {"first_name": "John", "last_name": "Doe", "dob": "1980-01-15"},
        "prescriber": {
            "npi": npi, "first_name": "Alice", "last_name": "Chen",
            "address": "100 Medical Dr, Springfield", "phone_number": "555-0100",
        },
        "medication": {"drug_name": "Lisinopril", "manufacturer": "GeneriCo"},
        "sig": {"directions": "Take 1 tablet by mouth daily"},
        "quantity": 30,
        "refills": 3,
        "written_date": "2026-07-18",
    }


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------

class TestTokenIssuance:
    def test_valid_credentials_return_token(self, raw_client, db_session):
        make_erx_client(db_session, client_id="clinic_a", client_secret="secret-a")
        db_session.commit()

        resp = raw_client.post("/eprescribe/oauth/token", json={
            "client_id": "clinic_a", "client_secret": "secret-a",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 900
        assert body["access_token"]

    def test_wrong_secret_rejected(self, raw_client, db_session):
        make_erx_client(db_session, client_id="clinic_b", client_secret="secret-b")
        db_session.commit()

        resp = raw_client.post("/eprescribe/oauth/token", json={
            "client_id": "clinic_b", "client_secret": "wrong",
        })
        assert resp.status_code == 401

    def test_unknown_client_id_rejected(self, raw_client):
        resp = raw_client.post("/eprescribe/oauth/token", json={
            "client_id": "clinic_nonexistent", "client_secret": "whatever",
        })
        assert resp.status_code == 401

    def test_inactive_client_rejected(self, raw_client, db_session):
        make_erx_client(db_session, client_id="clinic_c", client_secret="secret-c", is_active=False)
        db_session.commit()

        resp = raw_client.post("/eprescribe/oauth/token", json={
            "client_id": "clinic_c", "client_secret": "secret-c",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# NewRx submission
# ---------------------------------------------------------------------------

class TestNewRxSubmission:
    def test_success_lands_refill_in_qt(self, raw_client, db_session):
        make_prescriber(db_session)
        make_drug(db_session)
        make_patient(db_session)
        clinic, secret = make_erx_client(db_session, client_id="clinic_ok")
        db_session.commit()
        token = create_client_token(clinic)

        resp = raw_client.post("/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(token))

        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "QT"
        refill = db_session.get(Refill, body["refill_id"])
        assert refill.state == RxState.QT
        assert refill.source == "external"

    def test_patient_not_found_404(self, raw_client, db_session):
        make_prescriber(db_session)
        make_drug(db_session)
        clinic, secret = make_erx_client(db_session, client_id="clinic_nopatient")
        db_session.commit()
        token = create_client_token(clinic)

        resp = raw_client.post("/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(token))

        assert resp.status_code == 404
        assert "Patient" in resp.json()["detail"]

    def test_unknown_prescriber_is_auto_created(self, raw_client, db_session):
        make_drug(db_session)
        make_patient(db_session)
        clinic, secret = make_erx_client(db_session, client_id="clinic_newpx")
        db_session.commit()
        token = create_client_token(clinic)
        new_npi = 9998887770

        resp = raw_client.post(
            "/eprescribe/newrx", json=_valid_newrx_payload(npi=new_npi), headers=_auth(token)
        )

        assert resp.status_code == 200
        prescriber = db_session.query(Prescriber).filter(Prescriber.npi == new_npi).first()
        assert prescriber is not None
        audit = db_session.query(AuditLog).filter(AuditLog.action == "PRESCRIBER_CREATED").first()
        assert audit is not None
        assert str(new_npi) in audit.details

    def test_drug_not_found_404(self, raw_client, db_session):
        make_prescriber(db_session)
        make_patient(db_session)
        clinic, secret = make_erx_client(db_session, client_id="clinic_nodrug")
        db_session.commit()
        token = create_client_token(clinic)

        resp = raw_client.post("/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(token))

        assert resp.status_code == 404
        assert "Drug" in resp.json()["detail"]

    def test_no_token_rejected(self, raw_client, db_session):
        make_prescriber(db_session)
        make_drug(db_session)
        make_patient(db_session)
        db_session.commit()

        resp = raw_client.post("/eprescribe/newrx", json=_valid_newrx_payload())
        assert resp.status_code == 401

    def test_staff_token_rejected(self, raw_client, db_session):
        """A staff login token must never work against the clinic-only intake endpoint."""
        make_prescriber(db_session)
        make_drug(db_session)
        make_patient(db_session)
        db_session.commit()
        staff = User(id=999999, username="staff", hashed_password="x", is_active=True,
                     is_admin=True, role="admin")
        staff_token = create_access_token(staff)

        resp = raw_client.post(
            "/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(staff_token)
        )
        assert resp.status_code == 401

    def test_expired_client_token_rejected(self, raw_client, db_session):
        clinic, secret = make_erx_client(db_session, client_id="clinic_expired")
        db_session.commit()
        expired_token = jwt.encode(
            {
                "sub": str(clinic.id),
                "client_id": clinic.client_id,
                "clinic_name": clinic.clinic_name,
                "token_type": "client",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )

        resp = raw_client.post(
            "/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(expired_token)
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Reverse cross-rejection: a clinic token must never work against a
# staff-only endpoint, even though both are signed with the same secret.
# ---------------------------------------------------------------------------

class TestReverseCrossRejection:
    def test_client_token_rejected_by_staff_endpoint(self, raw_client, db_session):
        clinic, secret = make_erx_client(db_session, client_id="clinic_reverse")
        db_session.commit()
        client_token = create_client_token(clinic)

        resp = raw_client.get("/eprescribe/clients", headers=_auth(client_token))
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Queue cache invalidation
# ---------------------------------------------------------------------------

class TestCacheInvalidation:
    def test_newrx_invalidates_queue_cache(self, raw_client, db_session, fake_redis):
        make_prescriber(db_session)
        make_drug(db_session)
        make_patient(db_session)
        clinic, secret = make_erx_client(db_session, client_id="clinic_cache")
        db_session.commit()
        token = create_client_token(clinic)

        fake_redis.setex("refills:queue:ALL:15:0:due:asc", 30, "[]")
        assert fake_redis.get("refills:queue:ALL:15:0:due:asc") is not None

        resp = raw_client.post("/eprescribe/newrx", json=_valid_newrx_payload(), headers=_auth(token))
        assert resp.status_code == 200

        assert fake_redis.get("refills:queue:ALL:15:0:due:asc") is None


# ---------------------------------------------------------------------------
# Admin: clinic client management
# ---------------------------------------------------------------------------

class TestAdminClientManagement:
    def test_create_requires_admin(self, engine):
        """A non-admin (technician) user gets 403, mirroring existing RBAC tests."""
        TestSession = sessionmaker(bind=engine)

        def override_get_db():
            session = TestSession()
            try:
                yield session
            finally:
                session.close()

        def override_get_current_user():
            return User(id=None, username="tech", hashed_password="x",
                        is_active=True, is_admin=False, role="technician")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            with TestClient(app, base_url="http://testserver/api/v1") as c:
                resp = c.post("/eprescribe/clients", json={"clinic_name": "Sneaky Clinic"})
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_create_returns_secret_once(self, client, db_session):
        resp = client.post("/eprescribe/clients", json={"clinic_name": "Springfield Clinic"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["client_id"].startswith("clinic_")
        assert body["client_secret"]
        assert body["clinic_name"] == "Springfield Clinic"

    def test_list_excludes_secret(self, client, db_session):
        make_erx_client(db_session, client_id="clinic_list", clinic_name="List Clinic")
        db_session.commit()

        resp = client.get("/eprescribe/clients")
        assert resp.status_code == 200
        items = resp.json()
        assert any(i["client_id"] == "clinic_list" for i in items)
        for item in items:
            assert "client_secret" not in item
            assert "hashed_client_secret" not in item

    def test_deactivate_revokes_token_issuance(self, client, db_session):
        """/eprescribe/oauth/token has no auth dependency, so the admin-overridden
        `client` fixture is safe to reuse for this call too."""
        clinic, secret = make_erx_client(db_session, client_id="clinic_revoke", client_secret="revoke-me")
        db_session.commit()

        resp = client.delete(f"/eprescribe/clients/{clinic.id}")
        assert resp.status_code == 204

        token_resp = client.post("/eprescribe/oauth/token", json={
            "client_id": "clinic_revoke", "client_secret": "revoke-me",
        })
        assert token_resp.status_code == 401
