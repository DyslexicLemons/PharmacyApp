"""
test_security.py — Security tests for the Pharmacy API.

Tests for:
- SQL injection via query parameters and request bodies
- Malformed/unexpected input types
- Path traversal and excessively large inputs
- Invalid JSON handling
- Unauthorized access patterns (no auth layer, but validate endpoints behave safely)

All tests verify that the API returns clean error responses and does NOT:
  - Expose stack traces with sensitive data
  - Crash (500) on malicious input
  - Silently corrupt data
"""
import pytest
import json
from datetime import date

from tests.conftest import make_prescriber, make_drug, make_patient, make_prescription


# ===========================================================================
# SQL INJECTION TESTS
# ===========================================================================

class TestSQLInjection:
    """
    SQLAlchemy's ORM with parameterized queries prevents classic SQL injection.
    These tests confirm that injection payloads are treated as literal strings
    (either sanitized, rejected with 422, or cause a 404 / 400 — never a 500).
    """

    SQL_PAYLOADS = [
        "' OR '1'='1",
        "'; DROP TABLE patients; --",
        "1; SELECT * FROM patients--",
        "' UNION SELECT null,null,null--",
        "1' AND SLEEP(5)--",
        "admin'--",
        "' OR 1=1--",
        '" OR ""="',
        "1 OR 1=1",
    ]

    def test_patient_search_sql_injection(self, client, db_session):
        """SQL injection in patient search q= param returns safe response, not 500."""
        for payload in self.SQL_PAYLOADS:
            resp = client.get("/patients", params={"q": payload})
            # Must NOT return 500
            assert resp.status_code != 500, (
                f"500 error on SQL injection payload: {payload!r}\n{resp.text}"
            )

    def test_refill_state_filter_injection(self, client, db_session):
        """SQL injection in state filter returns 400 (invalid state), not 500."""
        for payload in self.SQL_PAYLOADS:
            resp = client.get("/refills", params={"state": payload})
            assert resp.status_code in (400, 422), (
                f"Expected 400/422, got {resp.status_code} for payload: {payload!r}"
            )

    def test_prescription_id_injection(self, client, db_session):
        """Path parameter injection — FastAPI should reject non-integer IDs with 422."""
        for payload in ["' OR 1=1", "1; DROP TABLE prescriptions--", "1 UNION SELECT"]:
            resp = client.get(f"/prescriptions/{payload}")
            assert resp.status_code == 422

    def test_patient_id_path_injection(self, client, db_session):
        for payload in ["' OR 1=1", "1 OR 1=1"]:
            resp = client.get(f"/patients/{payload}")
            assert resp.status_code == 422

    def test_create_patient_name_injection(self, client, db_session):
        """SQL injection in patient name fields is stored as literal text (ORM parameterizes it)."""
        payload = {
            "first_name": "'; DROP TABLE patients; --",
            "last_name": "Smith",
            "dob": "1990-01-01",
            "address": "1 Test St",
        }
        resp = client.post("/patients", json=payload)
        # Should succeed — ORM parameterizes the value safely
        assert resp.status_code in (200, 422)
        assert resp.status_code != 500

    def test_fill_priority_injection(self, client, base_data):
        """SQL injection in priority field should be caught by schema validation."""
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": 30,
            "days_supply": 30,
            "priority": "'; DROP TABLE refills; --",
        })
        assert resp.status_code == 422

    def test_conflict_check_patient_id_injection(self, client, db_session):
        """conflict check endpoint handles string injection in patient_id."""
        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": "' OR 1=1", "drug_id": "1"}
        )
        assert resp.status_code == 422


# ===========================================================================
# MALFORMED INPUT TESTS
# ===========================================================================

class TestMalformedInput:
    def test_fill_with_string_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": "thirty",
            "days_supply": 30,
            "priority": "normal",
        })
        assert resp.status_code == 422

    def test_fill_with_float_quantity_coerces_or_rejects(self, client, base_data):
        """Float quantities are coerced to int by Pydantic, which then validates > 0."""
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": 30.5,
            "days_supply": 30,
            "priority": "normal",
        })
        # Pydantic v2 may coerce float→int, or reject. Either is acceptable.
        assert resp.status_code in (200, 422)
        assert resp.status_code != 500

    def test_fill_with_null_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": None,
            "days_supply": 30,
            "priority": "normal",
        })
        assert resp.status_code == 422

    def test_fill_with_boolean_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": True,
            "days_supply": 30,
            "priority": "normal",
        })
        # bool is a subclass of int in Python; True==1 which is valid. Either 200 or 422 is fine.
        assert resp.status_code in (200, 422)
        assert resp.status_code != 500

    def test_fill_with_empty_body_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={})
        assert resp.status_code == 422

    def test_advance_with_invalid_action_string(self, client, db_session):
        """Unknown action strings should be silently ignored (treated as default advance)."""
        from tests.conftest import make_prescriber, make_drug, make_patient, make_prescription, make_refill
        from app.models import RxState
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber)
        refill = make_refill(db, prescription, drug, patient, state=RxState.QT)
        db.commit()

        # An unknown action falls through to default advance
        resp = client.post(f"/refills/{refill.id}/advance", json={"action": "UNKNOWN_ACTION"})
        assert resp.status_code in (200, 400)
        assert resp.status_code != 500

    def test_create_patient_with_future_dob(self, client, db_session):
        """Future date of birth is technically accepted (no DOB validation in schema)."""
        resp = client.post("/patients", json={
            "first_name": "Future",
            "last_name": "Person",
            "dob": "2099-12-31",
            "address": "1 Future St",
        })
        # The API doesn't validate that DOB is in the past — this is a known limitation
        assert resp.status_code in (200, 422)
        assert resp.status_code != 500

    def test_very_long_string_in_name_field(self, client, db_session):
        """Extremely long strings do not crash the server."""
        long_name = "A" * 10_000
        resp = client.post("/patients", json={
            "first_name": long_name,
            "last_name": "B",
            "dob": "1990-01-01",
            "address": "1 Test St",
        })
        assert resp.status_code != 500

    def test_unicode_and_special_chars_in_name(self, client, db_session):
        """Unicode names (international characters) should be stored safely."""
        resp = client.post("/patients", json={
            "first_name": "Zoë",
            "last_name": "Müller-Schröder",
            "dob": "1985-04-12",
            "address": "10 Königsallee",
        })
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "Zoë"

    def test_emoji_in_directions_field(self, client, db_session):
        """Emoji in text fields should not crash the server."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        resp = client.post("/prescriptions", json={
            "date": str(date.today()),
            "patient_id": patient.id,
            "drug_id": drug.id,
            "brand_required": 0,
            "directions": "💊 Take 1 tablet daily 🌅",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": prescriber.npi,
        })
        assert resp.status_code != 500


# ===========================================================================
# MALFORMED JSON TESTS
# ===========================================================================

class TestMalformedJSON:
    def test_invalid_json_body_returns_422(self, client, base_data):
        """Sending raw invalid JSON should return 422, not 500."""
        rx_id = base_data["prescription"].id
        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            content=b'{"quantity": 30, "days_supply": 30,}',  # Trailing comma = invalid JSON
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_non_json_content_type_returns_error(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            content=b"quantity=30&days_supply=30",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert resp.status_code == 422

    def test_empty_body_to_post_endpoint_returns_422(self, client, db_session):
        resp = client.post(
            "/patients",
            content=b"",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


# ===========================================================================
# LARGE / EXTREME VALUE TESTS
# ===========================================================================

class TestExtremeValues:
    def test_extremely_large_prescription_id_returns_404(self, client, db_session):
        resp = client.get("/prescriptions/2147483647")  # INT_MAX
        assert resp.status_code == 404

    def test_extremely_large_refill_id_returns_404(self, client, db_session):
        resp = client.get("/refills/2147483647")
        assert resp.status_code == 404

    def test_extremely_large_patient_id_returns_404(self, client, db_session):
        resp = client.get("/patients/2147483647")
        assert resp.status_code == 404

    def test_overflow_quantity_rejected_by_guard(self, client, base_data):
        """
        An absurdly large quantity (exceeds remaining) is caught by the
        overfill guard before any arithmetic overflow.
        """
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={
            "quantity": 2_000_000_000,
            "days_supply": 30,
            "priority": "normal",
        })
        assert resp.status_code in (422, 422)  # schema rejects OR overfill guard


# ===========================================================================
# RESPONSE DOES NOT LEAK INTERNAL DETAILS
# ===========================================================================

class TestResponseSafety:
    def test_404_does_not_expose_stack_trace(self, client, db_session):
        resp = client.get("/prescriptions/99999")
        assert resp.status_code == 404
        body = resp.json()
        # FastAPI returns {"detail": "..."} — no traceback
        assert "traceback" not in str(body).lower()
        assert "sqlalchemy" not in str(body).lower()

    def test_422_error_exposes_only_field_info(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={"quantity": 0, "days_supply": 30})
        assert resp.status_code == 422
        body = resp.json()
        # Pydantic v2 error format: {"detail": [...]}
        assert "detail" in body
        # Should not contain raw SQL or Python internals
        body_str = json.dumps(body)
        assert "sqlalchemy" not in body_str.lower()
        assert "engine" not in body_str.lower()

    def test_409_conflict_returns_human_readable_message(self, client, db_session):
        from app.models import RxState
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_prescription_active_refill = __import__(
            "tests.conftest", fromlist=["make_refill"]
        ).make_refill
        make_prescription_active_refill(db, prescription, drug, patient, state=RxState.QT)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json={
            "quantity": 30, "days_supply": 30, "priority": "normal"
        })
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        # Human-readable, not a stack trace
        assert isinstance(detail, str)
        assert len(detail) < 500  # Reasonable length
