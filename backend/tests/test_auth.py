"""Tests for authentication and user management endpoints.

Covers: disable_user invalidates quick codes, self-disable guard, 404 on
unknown/already-disabled user.
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.auth import get_current_user
from app.database import get_db
from app.models import QuickCode, User


# ---------------------------------------------------------------------------
# Fixture: admin user with a real DB id so the self-disable guard is testable
# ---------------------------------------------------------------------------

@pytest.fixture()
def admin_client(engine):
    """
    TestClient with a real admin user seeded in the DB.
    get_current_user is overridden to return that user so require_admin passes
    and admin.id is a real integer.
    """
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    # Seed admin user
    setup_session = TestSession()
    admin = User(
        username="admin_fixture",
        hashed_password="x",
        is_active=True,
        is_admin=True,
    )
    setup_session.add(admin)
    setup_session.commit()
    setup_session.refresh(admin)
    admin_id = admin.id
    setup_session.close()

    def override_get_current_user():
        s = TestSession()
        u = s.query(User).filter(User.id == admin_id).first()
        s.close()
        return u

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app, base_url="http://testserver/api/v1") as c:
        yield c, admin_id

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_user(engine, username="target_user") -> tuple[int, int]:
    """Seed a regular active user with one unexpired DB quick code.
    Returns (user_id, quick_code_id)."""
    Session = sessionmaker(bind=engine)
    s = Session()
    user = User(username=username, hashed_password="x", is_active=True, is_admin=False)
    s.add(user)
    s.flush()
    qc = QuickCode(
        code="ABC",
        user_id=user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        used=False,
    )
    s.add(qc)
    s.commit()
    user_id = user.id
    qc_id = qc.id
    s.close()
    return user_id, qc_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDisableUser:
    def test_disable_user_marks_inactive_and_invalidates_quick_codes(self, admin_client, engine):
        client, _ = admin_client
        user_id, qc_id = _seed_user(engine)

        resp = client.delete(f"/users/{user_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        Session = sessionmaker(bind=engine)
        s = Session()
        user = s.query(User).filter(User.id == user_id).first()
        assert user.is_active is False

        qc = s.query(QuickCode).filter(QuickCode.id == qc_id).first()
        assert qc.used is True
        s.close()

    def test_disable_user_cannot_disable_self(self, admin_client, engine):
        client, admin_id = admin_client

        resp = client.delete(f"/users/{admin_id}")
        assert resp.status_code == 400

    def test_disable_user_returns_404_for_unknown_user(self, admin_client, engine):
        client, _ = admin_client

        resp = client.delete("/users/999999")
        assert resp.status_code == 404

    def test_disable_user_returns_404_if_already_disabled(self, admin_client, engine):
        client, _ = admin_client
        user_id, _ = _seed_user(engine, username="already_disabled")

        client.delete(f"/users/{user_id}")  # first disable
        resp = client.delete(f"/users/{user_id}")  # second attempt
        assert resp.status_code == 404
