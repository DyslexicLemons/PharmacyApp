"""
test_adjudication.py — Integration tests for POST /refills/{id}/adjudicate.

This endpoint calls the InsuranceAdjudicationGateway to submit a claim and
persists copay_amount / insurance_paid on the Refill row.  All tests run
against a real PostgreSQL test DB.
"""
import pytest
from decimal import Decimal

from app.models import Refill, RxState
from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription,
    make_refill, make_insurance, make_formulary, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Helper: build a full scenario with a QV2 refill
# ---------------------------------------------------------------------------

def setup_qv2_refill(db, cost=Decimal("1.00"), copay_per_30=Decimal("10.00"),
                     not_covered=False, quantity=30, days_supply=30):
    prescriber = make_prescriber(db)
    drug = make_drug(db, ndc="12345-678-90", cost=cost)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
    insurance = make_insurance(db)
    make_formulary(db, insurance, drug, tier=1,
                   copay_per_30=copay_per_30, not_covered=not_covered)
    patient_ins = make_patient_insurance(db, patient, insurance)
    refill = make_refill(
        db, prescription, drug, patient,
        quantity=quantity, days_supply=days_supply,
        state=RxState.QV2,
    )
    refill.insurance_id = patient_ins.id
    db.commit()
    return refill, patient_ins, drug


# ===========================================================================
# HAPPY PATH
# ===========================================================================

class TestAdjudicateApproved:
    def test_approved_claim_returns_200(self, client, db_session):
        refill, _, _ = setup_qv2_refill(db_session)

        resp = client.post(f"/refills/{refill.id}/adjudicate")

        assert resp.status_code == 200
        assert resp.json()["approved"] is True

    def test_approved_claim_persists_copay_on_refill(self, client, db_session):
        """
        drug.cost=$1.00, qty=30 → cash=$30.00
        copay_per_30=$10.00, 30-day supply → copay=$10.00
        """
        refill, _, _ = setup_qv2_refill(
            db_session, cost=Decimal("1.00"), copay_per_30=Decimal("10.00")
        )

        client.post(f"/refills/{refill.id}/adjudicate")

        db_session.expire(refill)
        updated = db_session.query(Refill).filter(Refill.id == refill.id).first()
        assert updated.copay_amount is not None
        assert Decimal(str(updated.copay_amount)) == Decimal("10.00")

    def test_approved_claim_persists_insurance_paid_on_refill(self, client, db_session):
        refill, _, _ = setup_qv2_refill(
            db_session, cost=Decimal("1.00"), copay_per_30=Decimal("10.00")
        )

        client.post(f"/refills/{refill.id}/adjudicate")

        db_session.expire(refill)
        updated = db_session.query(Refill).filter(Refill.id == refill.id).first()
        assert updated.insurance_paid is not None
        # cash_price ($30.00) - copay ($10.00) = $20.00
        assert Decimal(str(updated.insurance_paid)) == Decimal("20.00")

    def test_approved_claim_response_includes_provider_name(self, client, db_session):
        refill, _, _ = setup_qv2_refill(db_session)

        resp = client.post(f"/refills/{refill.id}/adjudicate")

        assert "provider" in resp.json()
        assert resp.json()["provider"] == "LocalInsuranceGateway"

    def test_approved_claim_response_amounts_are_strings(self, client, db_session):
        refill, _, _ = setup_qv2_refill(db_session)

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        body = resp.json()

        assert isinstance(body["amount_due"], str)
        assert isinstance(body["amount_paid"], str)

    def test_approved_claim_amount_due_matches_persisted_copay(self, client, db_session):
        refill, _, _ = setup_qv2_refill(
            db_session, cost=Decimal("1.00"), copay_per_30=Decimal("10.00")
        )

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        body = resp.json()

        db_session.expire(refill)
        updated = db_session.query(Refill).filter(Refill.id == refill.id).first()
        assert Decimal(body["amount_due"]) == Decimal(str(updated.copay_amount))

    def test_copay_capped_at_cash_price(self, client, db_session):
        """
        drug.cost=$0.10 × 30 = $3.00 cash.
        copay_per_30=$50.00 → capped at $3.00.
        """
        refill, _, _ = setup_qv2_refill(
            db_session, cost=Decimal("0.10"), copay_per_30=Decimal("50.00"), quantity=30
        )

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        body = resp.json()

        assert Decimal(body["amount_due"]) <= Decimal("3.00")
        assert Decimal(body["amount_paid"]) >= Decimal("0")


# ===========================================================================
# NOT COVERED
# ===========================================================================

class TestAdjudicateNotCovered:
    def test_not_covered_returns_rejected_claim(self, client, db_session):
        refill, _, _ = setup_qv2_refill(db_session, not_covered=True)

        resp = client.post(f"/refills/{refill.id}/adjudicate")

        assert resp.status_code == 200
        body = resp.json()
        assert body["approved"] is False
        assert body["rejection_code"] == "NOT_COVERED"

    def test_not_covered_does_not_update_refill_billing_fields(self, client, db_session):
        refill, _, _ = setup_qv2_refill(db_session, not_covered=True)

        client.post(f"/refills/{refill.id}/adjudicate")

        db_session.expire(refill)
        updated = db_session.query(Refill).filter(Refill.id == refill.id).first()
        assert updated.copay_amount is None
        assert updated.insurance_paid is None


# ===========================================================================
# WRONG STATE
# ===========================================================================

class TestAdjudicateWrongState:
    def test_adjudicate_in_qt_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, 90, 90)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QT)
        db_session.commit()

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        assert resp.status_code == 400
        assert "QV2" in resp.json()["detail"]

    def test_adjudicate_in_ready_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, 90, 90)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.READY)
        db_session.commit()

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        assert resp.status_code == 400

    def test_adjudicate_in_qp_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, 90, 90)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QP)
        db_session.commit()

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        assert resp.status_code == 400


# ===========================================================================
# MISSING REFILL / INSURANCE
# ===========================================================================

class TestAdjudicateEdgeCases:
    def test_adjudicate_nonexistent_refill_returns_404(self, client):
        resp = client.post("/refills/99999/adjudicate")
        assert resp.status_code == 404

    def test_adjudicate_without_insurance_returns_400(self, client, db_session):
        """Refill in QV2 with no insurance on file returns 400."""
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, 90, 90)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QV2)
        # No PatientInsurance record created for this patient
        db_session.commit()

        resp = client.post(f"/refills/{refill.id}/adjudicate")
        assert resp.status_code == 400
        assert "insurance" in resp.json()["detail"].lower()
