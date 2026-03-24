"""
test_fill_prescription.py — Integration tests for POST /prescriptions/{id}/fill.

This is the highest-priority endpoint: it is the gateway for dispensing drugs.
Wrong behavior here can cause patient safety incidents.
"""
import pytest
from decimal import Decimal
from datetime import date, timedelta

from app.models import RxState, RefillHist
from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription,
    make_refill, make_insurance, make_formulary, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Helper: build a valid fill payload
# ---------------------------------------------------------------------------

def fill_payload(quantity=30, days_supply=30, priority="normal", **kwargs):
    payload = {"quantity": quantity, "days_supply": days_supply, "priority": priority}
    payload.update(kwargs)
    return payload


# ===========================================================================
# SUCCESS CASES
# ===========================================================================

class TestFillPrescriptionSuccess:
    def test_fill_creates_refill_in_qv1_state(self, client, base_data):
        """A fresh prescription with no history defaults to QV1."""
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30))
        assert resp.status_code == 200
        body = resp.json()
        assert body["state"] == "RxState.QV1"
        assert "refill_id" in body

    def test_fill_decrements_remaining_quantity(self, client, base_data):
        """After a fill, remaining_quantity on the prescription decreases by qty."""
        db = base_data["db"]
        rx = base_data["prescription"]
        rx_id = rx.id
        original_remaining = rx.remaining_quantity

        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30))
        assert resp.status_code == 200

        db.refresh(rx)
        assert rx.remaining_quantity == original_remaining - 30

    def test_fill_with_exact_remaining_quantity_succeeds(self, client, db_session):
        """Fill exactly the remaining quantity — boundary condition."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # Only 30 remaining
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 200

    def test_fill_with_partial_quantity_succeeds(self, client, base_data):
        """Fill less than remaining quantity is allowed."""
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(10))
        assert resp.status_code == 200

    def test_fill_returns_refill_id(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30))
        assert isinstance(resp.json()["refill_id"], int)
        assert resp.json()["refill_id"] > 0

    def test_fill_scheduled_creates_scheduled_state(self, client, base_data):
        """When scheduled=True, refill enters SCHEDULED state (no qty decrement yet)."""
        rx_id = base_data["prescription"].id
        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            json=fill_payload(30, scheduled=True, due_date=str(date.today() + timedelta(days=30)))
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "RxState.SCHEDULED"

    def test_scheduled_fill_does_not_decrement_quantity(self, client, db_session):
        """SCHEDULED fills don't enter ACTIVE_STATES, so remaining_qty stays unchanged."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        resp = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json=fill_payload(30, scheduled=True, due_date=str(date.today() + timedelta(days=30)))
        )
        assert resp.status_code == 200

        db.refresh(prescription)
        # SCHEDULED is not in ACTIVE_STATES, so no decrement
        assert prescription.remaining_quantity == 90

    def test_fill_with_history_match_starts_at_qp(self, client, db_session):
        """
        If previous fill had the same qty/days/insurance, skip QV1 → start at QP.
        This tests the "history shortcut" optimization.
        """
        from app.models import RefillHist
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)

        # Seed a completed history entry that matches qty=30, days=30, no insurance
        hist = RefillHist(
            prescription_id=prescription.id,
            patient_id=patient.id,
            drug_id=drug.id,
            quantity=30,
            days_supply=30,
            completed_date=date.today() - timedelta(days=35),
            sold_date=date.today() - timedelta(days=35),
            total_cost=Decimal("15.00"),
        )
        db.add(hist)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 200
        assert resp.json()["state"] == "RxState.QP"

    def test_fill_stat_priority(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30, priority="stat"))
        assert resp.status_code == 200

    def test_fill_high_priority(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30, priority="high"))
        assert resp.status_code == 200

    def test_fill_with_future_due_date(self, client, base_data):
        rx_id = base_data["prescription"].id
        future = str(date.today() + timedelta(days=7))
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(30, due_date=future))
        assert resp.status_code == 200

    def test_fill_creates_audit_log_entry(self, client, db_session):
        """Verify an AuditLog row is written when a fill is created."""
        from app.models import AuditLog
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber)
        db.commit()

        client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        log = db.query(AuditLog).filter(AuditLog.action == "FILL_CREATED").first()
        assert log is not None
        assert log.entity_type == "refill"


# ===========================================================================
# PRESCRIPTION NOT FOUND
# ===========================================================================

class TestFillPrescriptionNotFound:
    def test_nonexistent_prescription_returns_404(self, client, base_data):
        resp = client.post("/prescriptions/99999/fill", json=fill_payload(30))
        assert resp.status_code == 404

    def test_zero_id_returns_404_or_422(self, client, base_data):
        resp = client.post("/prescriptions/0/fill", json=fill_payload(30))
        assert resp.status_code in (404, 422)

    def test_negative_id_returns_422(self, client, base_data):
        # FastAPI path params: negative int is valid syntax; 404 from DB lookup
        resp = client.post("/prescriptions/-1/fill", json=fill_payload(30))
        assert resp.status_code in (404, 422)

    def test_string_id_returns_422(self, client, base_data):
        resp = client.post("/prescriptions/abc/fill", json=fill_payload(30))
        assert resp.status_code == 422


# ===========================================================================
# PHARMACY SAFETY: NO REMAINING QUANTITY
# ===========================================================================

class TestFillNoRemainingQuantity:
    def test_zero_remaining_returns_409(self, client, db_session):
        """Cannot fill a prescription with 0 remaining quantity."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # remaining_qty explicitly set to 0
        prescription = make_prescription(db, patient, drug, prescriber, 90, 0)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409
        assert "remaining" in resp.json()["detail"].lower()

    def test_negative_remaining_returns_409(self, client, db_session):
        """Prescriptions with negative remaining (data corruption) cannot be filled."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, -5)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409


# ===========================================================================
# PHARMACY SAFETY: OVERFILL PREVENTION
# ===========================================================================

class TestFillOverfillPrevention:
    def test_quantity_exceeds_remaining_returns_422(self, client, db_session):
        """Requesting more than remaining authorized quantity must be blocked."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # Only 20 remaining
        prescription = make_prescription(db, patient, drug, prescriber, 90, 20)
        db.commit()

        # Try to fill 30 (more than 20 remaining)
        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 422
        assert "exceeds" in resp.json()["detail"].lower()

    def test_quantity_one_over_remaining_returns_422(self, client, db_session):
        """Boundary: exactly 1 unit over the remaining should be blocked."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(31))
        assert resp.status_code == 422

    def test_very_large_quantity_returns_422(self, client, db_session):
        """Absurdly large quantity is blocked by overfill guard."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(999_999))
        assert resp.status_code == 422


# ===========================================================================
# PHARMACY SAFETY: DUPLICATE / CONCURRENT FILL PREVENTION
# ===========================================================================

class TestFillDuplicatePrevention:
    def test_second_fill_while_first_active_returns_409(self, client, db_session):
        """Cannot open a second active fill when one is already in-progress."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        # Seed an existing active fill in QT state
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QT)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409
        assert "active fill" in resp.json()["detail"].lower()

    def test_fill_blocked_when_in_qv1(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QV1)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409

    def test_fill_blocked_when_in_qp(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QP)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409

    def test_fill_blocked_when_ready_for_pickup(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.READY)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 409

    def test_fill_allowed_when_previous_was_sold(self, client, db_session):
        """A SOLD fill is complete; a new fill should be permitted."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.SOLD)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 200

    def test_fill_allowed_when_previous_was_rejected(self, client, db_session):
        """A REJECTED fill is done; a new fill should be permitted."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.REJECTED)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 200

    def test_fill_allowed_when_previous_was_hold(self, client, db_session):
        """HOLD is not a BLOCKING_STATE; a new fill can be started."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, quantity=30, state=RxState.HOLD)
        db.commit()

        resp = client.post(f"/prescriptions/{prescription.id}/fill", json=fill_payload(30))
        assert resp.status_code == 200


# ===========================================================================
# SCHEMA VALIDATION ON THE REQUEST BODY
# ===========================================================================

class TestFillRequestValidation:
    def test_zero_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(0))
        assert resp.status_code == 422

    def test_negative_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json=fill_payload(-10))
        assert resp.status_code == 422

    def test_zero_days_supply_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={"quantity": 30, "days_supply": 0})
        assert resp.status_code == 422

    def test_negative_days_supply_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={"quantity": 30, "days_supply": -30})
        assert resp.status_code == 422

    def test_invalid_priority_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "critical"}
        )
        assert resp.status_code == 422

    def test_missing_quantity_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={"days_supply": 30})
        assert resp.status_code == 422

    def test_missing_days_supply_returns_422(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = client.post(f"/prescriptions/{rx_id}/fill", json={"quantity": 30})
        assert resp.status_code == 422


# ===========================================================================
# INSURANCE INTEGRATION AT FILL TIME
# ===========================================================================

class TestFillWithInsurance:
    def test_fill_with_valid_insurance_returns_billing_info(self, client, insured_data):
        """When insurance_id is provided, response includes copay/insurance_paid."""
        rx_id = insured_data["prescription"].id
        pi_id = insured_data["patient_ins"].id

        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            json=fill_payload(30, insurance_id=pi_id)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "cash_price" in body
        assert "copay_amount" in body
        assert "insurance_paid" in body
        assert body["copay_amount"] >= 0

    def test_fill_copay_does_not_exceed_cash_price(self, client, insured_data):
        """Copay is capped at the cash price of the drug."""
        rx_id = insured_data["prescription"].id
        pi_id = insured_data["patient_ins"].id

        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            json=fill_payload(30, insurance_id=pi_id)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["copay_amount"] <= body["cash_price"]

    def test_fill_not_covered_drug_starts_at_qt(self, client, db_session):
        """Drug not covered by insurance → enters QT for manual triage."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("5.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        insurance = make_insurance(db)
        # not_covered = True on the formulary entry
        make_formulary(db, insurance, drug, not_covered=True)
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json=fill_payload(30, insurance_id=pi.id)
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "QT" in body["state"]
        # QT is an ACTIVE_STATE — remaining_qty should have been decremented
        db.refresh(prescription)
        assert prescription.remaining_quantity == 60
        # triage_reason must be set so staff know why the script is in QT
        from app.models import Refill
        refill = db.query(Refill).filter(Refill.id == body["refill_id"]).first()
        assert refill.triage_reason == "insurance does not cover drug"

    def test_fill_with_nonexistent_insurance_id_falls_back_gracefully(self, client, base_data):
        """Invalid insurance_id is treated as no insurance (falls back to cash)."""
        rx_id = base_data["prescription"].id
        resp = client.post(
            f"/prescriptions/{rx_id}/fill",
            json=fill_payload(30, insurance_id=99999)
        )
        # Should succeed with cash price (no billing breakdown in response)
        assert resp.status_code == 200
        body = resp.json()
        assert "copay_amount" not in body
