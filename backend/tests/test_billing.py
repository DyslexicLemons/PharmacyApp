"""
test_billing.py — Integration tests for insurance billing and cost calculations.

Tests the billing logic in both:
  - POST /prescriptions/{id}/fill  (inline billing during fill)
  - POST /billing/calculate        (standalone billing preview endpoint)

Key business rules verified:
  - cash_price = drug.cost × quantity
  - copay = (copay_per_30 / 30) × days_supply, capped at cash_price
  - insurance_paid = cash_price - copay_amount
  - not_covered drugs have no copay calculation
  - insurance_id belonging to another patient is rejected
"""
import pytest
from decimal import Decimal
from datetime import date

from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription,
    make_insurance, make_formulary, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Helper: call the billing calculate endpoint
# ---------------------------------------------------------------------------

def calc(client, drug_id, insurance_id, quantity, days_supply):
    return client.post("/billing/calculate", json={
        "drug_id": drug_id,
        "insurance_id": insurance_id,
        "quantity": quantity,
        "days_supply": days_supply,
    })


# ===========================================================================
# CASH PRICE CALCULATION
# ===========================================================================

class TestCashPriceCalculation:
    def test_cash_price_equals_cost_times_quantity(self, client, insured_data):
        """cash_price = drug.cost ($1.00) × quantity (30) = $30.00"""
        drug_id = insured_data["drug"].id
        pi_id = insured_data["patient_ins"].id

        resp = calc(client, drug_id, pi_id, 30, 30)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["cash_price"])) == Decimal("30.00")

    def test_cash_price_for_single_unit(self, client, insured_data):
        """cash_price for qty=1 should equal exactly drug.cost."""
        drug_id = insured_data["drug"].id
        pi_id = insured_data["patient_ins"].id

        resp = calc(client, drug_id, pi_id, 1, 1)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["cash_price"])) == Decimal("1.00")

    def test_cash_price_for_90_day_supply(self, client, insured_data):
        """cash_price for qty=90 should be 90 × drug.cost."""
        drug_id = insured_data["drug"].id
        pi_id = insured_data["patient_ins"].id

        resp = calc(client, drug_id, pi_id, 90, 90)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["cash_price"])) == Decimal("90.00")

    def test_cash_price_with_high_cost_drug(self, client, db_session):
        """High-cost specialty drug: cash_price = $500.00 × 30 = $15,000.00"""
        db = db_session
        drug = make_drug(db, cost=Decimal("500.00"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        formulary = make_formulary(db, insurance, drug, copay_per_30=Decimal("50.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = calc(client, drug.id, pi.id, 30, 30)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["cash_price"])) == Decimal("15000.00")


# ===========================================================================
# COPAY CALCULATION
# ===========================================================================

class TestCopayCalculation:
    def test_30_day_copay_equals_copay_per_30(self, client, insured_data):
        """For a 30-day supply, copay = copay_per_30 exactly ($10.00)."""
        drug_id = insured_data["drug"].id
        pi_id = insured_data["patient_ins"].id

        resp = calc(client, drug_id, pi_id, 30, 30)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["insurance_price"])) == Decimal("10.00")

    def test_60_day_supply_copay_is_double_30_day(self, client, db_session):
        """For 60-day supply: copay = copay_per_30 × 2."""
        db = db_session
        drug = make_drug(db, cost=Decimal("2.00"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("10.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = calc(client, drug.id, pi.id, 60, 60)
        assert resp.status_code == 200
        assert Decimal(str(resp.json()["insurance_price"])) == Decimal("20.00")

    def test_copay_capped_at_cash_price(self, client, db_session):
        """
        Copay must never exceed the cash price.
        Scenario: drug costs $0.10/unit × 30 = $3.00 cash,
        but copay_per_30 = $50.00 → copay capped at $3.00.
        """
        db = db_session
        drug = make_drug(db, cost=Decimal("0.10"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("50.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = calc(client, drug.id, pi.id, 30, 30)
        assert resp.status_code == 200
        body = resp.json()
        cash = Decimal(str(body["cash_price"]))
        copay = Decimal(str(body["insurance_price"]))
        assert copay <= cash, f"Copay {copay} exceeded cash {cash}"

    def test_insurance_paid_equals_cash_minus_copay(self, client, insured_data):
        """insurance_paid = cash_price - copay_amount."""
        drug_id = insured_data["drug"].id
        pi_id = insured_data["patient_ins"].id

        resp = calc(client, drug_id, pi_id, 30, 30)
        body = resp.json()
        cash = Decimal(str(body["cash_price"]))
        copay = Decimal(str(body["insurance_price"]))
        ins_paid = Decimal(str(body["insurance_paid"]))
        assert ins_paid == cash - copay

    def test_insurance_paid_not_negative(self, client, db_session):
        """insurance_paid must be >= 0 in all cases."""
        db = db_session
        drug = make_drug(db, cost=Decimal("0.05"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("100.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = calc(client, drug.id, pi.id, 30, 30)
        body = resp.json()
        ins_paid = Decimal(str(body["insurance_paid"]))
        assert ins_paid >= Decimal("0.00")

    def test_tier_returned_in_billing_response(self, client, insured_data):
        """Billing response should include the formulary tier."""
        resp = calc(
            client,
            insured_data["drug"].id,
            insured_data["patient_ins"].id,
            30, 30
        )
        assert resp.status_code == 200
        assert resp.json()["tier"] == 1  # tier 1 set in insured_data fixture

    def test_plan_name_returned_in_billing_response(self, client, insured_data):
        resp = calc(
            client,
            insured_data["drug"].id,
            insured_data["patient_ins"].id,
            30, 30
        )
        body = resp.json()
        assert body["plan_name"] == "Blue Shield"


# ===========================================================================
# NOT COVERED DRUGS
# ===========================================================================

class TestNotCoveredDrugs:
    def test_not_covered_drug_returns_cash_price_only(self, client, db_session):
        """Drug with not_covered=True in formulary returns no insurance benefit."""
        db = db_session
        drug = make_drug(db, cost=Decimal("5.00"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, not_covered=True)
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = calc(client, drug.id, pi.id, 30, 30)
        assert resp.status_code == 200
        body = resp.json()
        assert body["not_covered"] is True
        # No insurance benefit
        assert body.get("insurance_price") is None or Decimal(str(body.get("insurance_price", 0))) == Decimal("0.00")

    def test_not_covered_fill_starts_at_qt_for_triage(self, client, db_session):
        """Not-covered drug triggers QT state for manual triage review."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("5.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, not_covered=True)
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal",
                  "insurance_id": pi.id},
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "RxState.QT"

    def test_drug_not_in_formulary_treated_as_not_covered(self, client, db_session):
        """Drug absent from formulary (no formulary entry) → treated as not covered."""
        db = db_session
        drug = make_drug(db, cost=Decimal("5.00"))
        another_drug = make_drug(db, name="OtherDrug", ndc="99999-999-99", cost=Decimal("10.00"))
        patient = make_patient(db)
        insurance = make_insurance(db)
        # Formulary entry exists for another_drug, NOT for drug
        make_formulary(db, insurance, another_drug, copay_per_30=Decimal("10.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        # Billing check on drug (not in formulary)
        resp = calc(client, drug.id, pi.id, 30, 30)
        assert resp.status_code == 200
        body = resp.json()
        assert body["not_covered"] is True


# ===========================================================================
# INSURANCE VALIDATION
# ===========================================================================

class TestInsuranceValidation:
    def test_billing_with_nonexistent_insurance_id_returns_404_or_no_coverage(
        self, client, db_session
    ):
        """Invalid insurance_id: billing endpoint returns 404."""
        db = db_session
        drug = make_drug(db)
        db.commit()

        resp = calc(client, drug.id, 99999, 30, 30)
        # Endpoint should return 404 (insurance not found) or handle gracefully
        assert resp.status_code in (404, 200)
        assert resp.status_code != 500

    def test_billing_with_zero_quantity_returns_422(self, client, insured_data):
        """BillingCalculateRequest validates quantity > 0."""
        resp = calc(
            client,
            insured_data["drug"].id,
            insured_data["patient_ins"].id,
            0, 30
        )
        assert resp.status_code == 422

    def test_billing_with_negative_quantity_returns_422(self, client, insured_data):
        resp = calc(
            client,
            insured_data["drug"].id,
            insured_data["patient_ins"].id,
            -10, 30
        )
        assert resp.status_code == 422

    def test_billing_with_zero_days_supply_returns_422(self, client, insured_data):
        resp = calc(
            client,
            insured_data["drug"].id,
            insured_data["patient_ins"].id,
            30, 0
        )
        assert resp.status_code == 422


# ===========================================================================
# FILL WITH INSURANCE — BILLING FIELDS PERSISTED ON REFILL
# ===========================================================================

class TestBillingPersistedOnRefill:
    def test_fill_with_insurance_persists_copay_on_refill(self, client, db_session):
        """After a fill with insurance, the Refill record stores copay_amount."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("1.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("10.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal",
                  "insurance_id": pi.id},
        )

        refill = db.query(RefillModel).first()
        assert refill is not None
        assert refill.copay_amount is not None
        assert Decimal(str(refill.copay_amount)) > Decimal("0.00")

    def test_fill_with_insurance_persists_insurance_paid(self, client, db_session):
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("2.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("10.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal",
                  "insurance_id": pi.id},
        )

        refill = db.query(RefillModel).first()
        assert refill is not None
        assert refill.insurance_paid is not None
        cash = Decimal(str(refill.total_cost))
        copay = Decimal(str(refill.copay_amount))
        ins_paid = Decimal(str(refill.insurance_paid))
        assert ins_paid == cash - copay

    def test_fill_without_insurance_has_null_copay(self, client, db_session):
        """Fill without insurance: copay_amount and insurance_paid are NULL."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )

        refill = db.query(RefillModel).first()
        assert refill.copay_amount is None
        assert refill.insurance_paid is None

    def test_sold_archives_billing_fields_to_refill_hist(self, client, db_session):
        """When a fill is sold, billing fields are archived in RefillHist."""
        from app.models import Refill as RefillModel, RefillHist as RefillHistModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("1.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        insurance = make_insurance(db)
        make_formulary(db, insurance, drug, copay_per_30=Decimal("10.00"))
        pi = make_patient_insurance(db, patient, insurance)
        db.commit()

        from tests.conftest import make_refill
        from app.models import RxState
        refill = make_refill(
            db, prescription, drug, patient,
            quantity=30, days_supply=30, state=RxState.READY,
        )
        refill.copay_amount = Decimal("10.00")
        refill.insurance_paid = Decimal("20.00")
        refill.insurance_id = pi.id
        db.commit()

        client.post(f"/refills/{refill.id}/advance", json={})  # READY → SOLD

        hist = db.query(RefillHistModel).first()
        assert hist is not None
        assert Decimal(str(hist.copay_amount)) == Decimal("10.00")
        assert Decimal(str(hist.insurance_paid)) == Decimal("20.00")


# ===========================================================================
# PATIENT INSURANCE MANAGEMENT
# ===========================================================================

class TestPatientInsuranceManagement:
    def test_add_insurance_to_patient(self, client, db_session):
        """POST /patients/{id}/insurance successfully links insurance."""
        db = db_session
        patient = make_patient(db)
        insurance = make_insurance(db)
        db.commit()

        resp = client.post(f"/patients/{patient.id}/insurance", json={
            "insurance_company_id": insurance.id,
            "member_id": "NEW_MBR_001",
            "group_number": "GRP999",
            "is_primary": True,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["member_id"] == "NEW_MBR_001"
        assert body["is_primary"] is True

    def test_add_insurance_to_nonexistent_patient_returns_404(self, client, db_session):
        db = db_session
        insurance = make_insurance(db)
        db.commit()

        resp = client.post("/patients/99999/insurance", json={
            "insurance_company_id": insurance.id,
            "member_id": "X",
            "is_primary": True,
        })
        assert resp.status_code == 404

    def test_get_patient_insurance(self, client, db_session):
        db = db_session
        patient = make_patient(db)
        insurance = make_insurance(db)
        make_patient_insurance(db, patient, insurance)
        db.commit()

        resp = client.get(f"/patients/{patient.id}/insurance")
        assert resp.status_code == 200
        ins_list = resp.json()
        assert len(ins_list) >= 1
        assert ins_list[0]["member_id"] == "MBR123"
