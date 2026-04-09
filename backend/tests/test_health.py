"""
test_health.py — tests for the /health endpoint and provider status endpoint.

Verifies that the endpoint correctly reflects Postgres and Redis availability,
and that the provider status endpoint reports registered provider names.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def raw_client():
    """TestClient without auth or DB overrides — health is unauthenticated."""
    with TestClient(app, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# Happy path — both deps reachable
# ---------------------------------------------------------------------------

def test_health_ok_no_redis(raw_client):
    """Returns 200 and postgres=ok when Redis is not configured."""
    with patch("app.cache.is_available", return_value=False):
        resp = raw_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"] == "not configured"
    assert "time" in body


def test_health_ok_with_redis(raw_client):
    """Returns 200 when both Postgres and Redis are reachable."""
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    with patch("app.cache.is_available", return_value=True), \
         patch("app.cache._client", mock_redis):
        resp = raw_client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"] == "ok"
    assert body["checks"]["redis"] == "ok"


# ---------------------------------------------------------------------------
# Degraded paths
# ---------------------------------------------------------------------------

def test_health_postgres_down(raw_client):
    """Returns 503 when Postgres is unreachable."""
    with patch("app.database.SessionLocal") as mock_session_cls:
        mock_session_cls.return_value.execute.side_effect = Exception("connection refused")
        with patch("app.cache.is_available", return_value=False):
            resp = raw_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert "error" in body["checks"]["postgres"]


def test_health_redis_down(raw_client):
    """Returns 503 when Redis is configured but unreachable."""
    mock_redis = MagicMock()
    mock_redis.ping.side_effect = Exception("connection refused")
    with patch("app.cache.is_available", return_value=True), \
         patch("app.cache._client", mock_redis):
        resp = raw_client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["postgres"] == "ok"
    assert "error" in body["checks"]["redis"]


# ---------------------------------------------------------------------------
# Provider status endpoint
# ---------------------------------------------------------------------------

def test_provider_status_returns_registered_providers(raw_client):
    """GET /api/v1/providers/status reports provider class names after startup."""
    resp = raw_client.get("/api/v1/providers/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "drug_catalog" in body
    assert "insurance_gateway" in body
    # After startup registration the values must be non-null class name strings
    assert body["drug_catalog"] is not None
    assert body["insurance_gateway"] is not None
    assert isinstance(body["drug_catalog"], str)
    assert isinstance(body["insurance_gateway"], str)
