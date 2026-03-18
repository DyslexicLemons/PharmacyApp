"""
test_edge_cases.py — Boundary conditions, edge cases, and pharmacy safety tests.

Covers the "what if" scenarios that could cause silent data corruption or
patient safety issues if not properly handled.
"""
import pytest
from decimal import Decimal
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

from app.models import RxState, Priority, Refill, Prescription, RefillHist, QuickCode, User
from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription,
    make_refill, make_insurance, make_formulary, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def fill(client, rx_id, quantity=30, days_supply=30, **kwargs):
    payload = {"quantity": quantity, "days_supply": days_supply, "priority": "normal"}
    payload.update(kwargs)
    return client.post(f"/prescriptions/{rx_id}/fill", json=payload)


def advance(client, refill_id, **kwargs):
    payload = {"schedule_next_fill": False}
    payload.update(kwargs)
    return client.post(f"/refills/{refill_id}/advance", json=payload)


# ===========================================================================
# QUANTITY BOUNDARY TESTS
# ===========================================================================

class TestQuantityBoundaries:
    def test_fill_quantity_of_one_succeeds(self, client, base_data):
        """Minimum non-zero fill quantity (1 unit) is valid."""
        rx_id = base_data["prescription"].id
        resp = fill(client, rx_id, quantity=1)
        assert resp.status_code == 200

    def test_fill_quantity_zero_rejected_by_schema(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = fill(client, rx_id, quantity=0)
        assert resp.status_code == 422

    def test_fill_quantity_negative_rejected_by_schema(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = fill(client, rx_id, quantity=-1)
        assert resp.status_code == 422

    def test_fill_exactly_remaining_sets_remaining_to_zero(self, client, db_session):
        """After filling the exact remaining, remaining_quantity == 0."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        fill(client, prescription.id, quantity=30)
        db.refresh(prescription)
        assert prescription.remaining_quantity == 0

    def test_prescription_with_one_remaining_can_fill_one(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 1)
        db.commit()

        resp = fill(client, prescription.id, quantity=1)
        assert resp.status_code == 200

    def test_prescription_with_one_remaining_cannot_fill_two(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 1)
        db.commit()

        resp = fill(client, prescription.id, quantity=2)
        assert resp.status_code == 422

    def test_remaining_quantity_never_goes_negative(self, client, db_session):
        """Guards against quantity going negative under any valid code path."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        fill(client, prescription.id, quantity=30)
        db.refresh(prescription)
        assert prescription.remaining_quantity >= 0

    def test_days_supply_of_one_is_valid(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = fill(client, rx_id, quantity=1, days_supply=1)
        assert resp.status_code == 200

    def test_days_supply_of_90_is_valid(self, client, base_data):
        rx_id = base_data["prescription"].id
        resp = fill(client, rx_id, quantity=30, days_supply=90)
        assert resp.status_code == 200


# ===========================================================================
# PRESCRIPTION QUANTITY CALCULATION
# ===========================================================================

class TestPrescriptionQuantityCalculation:
    def test_original_quantity_equals_refill_qty_times_total_refills(self, client, db_session):
        """POST /prescriptions: original_qty = refill_quantity × total_refills."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        payload = {
            "date": str(date.today()),
            "patient_id": patient.id,
            "drug_id": drug.id,
            "brand_required": 0,
            "directions": "Take 1 tablet daily",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": prescriber.npi,
        }
        resp = client.post("/prescriptions", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["original_quantity"] == 90   # 30 × 3
        assert body["remaining_quantity"] == 90

    def test_remaining_quantity_decrements_correctly_across_multiple_fills(self, client, db_session):
        """
        Sequential fills from the same prescription each decrement correctly:
        90 → 60 (after 1st fill SOLD) → 30 (after 2nd fill SOLD)
        """
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        # First fill: QT → QV1 → QP → QV2 → READY → SOLD
        fill(client, prescription.id, quantity=30)
        rx1 = db.query(RefillModel).order_by(RefillModel.id.desc()).first()
        for _ in range(4):  # QT→QV1→QP→QV2→READY then SOLD
            advance(client, rx1.id)
        advance(client, rx1.id)  # READY → SOLD

        db.refresh(prescription)
        assert prescription.remaining_quantity == 60

        # Second fill
        fill(client, prescription.id, quantity=30)
        rx2 = db.query(RefillModel).filter(RefillModel.state != RxState.SOLD).order_by(RefillModel.id.desc()).first()
        for _ in range(5):
            advance(client, rx2.id)

        db.refresh(prescription)
        assert prescription.remaining_quantity == 30


# ===========================================================================
# PATIENT EDGE CASES
# ===========================================================================

class TestPatientEdgeCases:
    def test_create_patient_with_minimum_data(self, client, db_session):
        resp = client.post("/patients", json={
            "first_name": "A",
            "last_name": "B",
            "dob": "2000-01-01",
            "address": "1 X St",
        })
        assert resp.status_code == 200
        assert resp.json()["first_name"] == "A"

    def test_get_nonexistent_patient_returns_404(self, client, db_session):
        resp = client.get("/patients/99999")
        assert resp.status_code == 404

    def test_patient_with_no_prescriptions_returns_empty_list(self, client, db_session):
        db = db_session
        patient = make_patient(db)
        db.commit()

        resp = client.get(f"/patients/{patient.id}")
        assert resp.status_code == 200
        assert resp.json()["prescriptions"] == []

    def test_search_patient_by_name(self, client, db_session):
        db = db_session
        make_patient(db, first="Zara", last="Zebra")
        db.commit()

        resp = client.get("/patients", params={"q": "Zebra,Zara"})
        assert resp.status_code == 200

    def test_get_patient_returns_correct_fields(self, client, db_session):
        db = db_session
        patient = make_patient(db, first="Jane", last="Smith", dob=date(1985, 6, 15))
        db.commit()

        resp = client.get(f"/patients/{patient.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["first_name"] == "Jane"
        assert body["last_name"] == "Smith"


# ===========================================================================
# PRESCRIPTION CREATION EDGE CASES
# ===========================================================================

class TestPrescriptionCreationEdgeCases:
    def test_create_prescription_with_nonexistent_patient_returns_404(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        db.commit()

        payload = {
            "date": str(date.today()),
            "patient_id": 99999,  # Does not exist
            "drug_id": drug.id,
            "brand_required": 0,
            "directions": "Take daily",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": prescriber.npi,
        }
        resp = client.post("/prescriptions", json=payload)
        assert resp.status_code == 404

    def test_create_prescription_with_nonexistent_prescriber_returns_404(self, client, db_session):
        db = db_session
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        payload = {
            "date": str(date.today()),
            "patient_id": patient.id,
            "drug_id": drug.id,
            "brand_required": 0,
            "directions": "Take daily",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": 9999999999,  # Does not exist
        }
        resp = client.post("/prescriptions", json=payload)
        assert resp.status_code == 404

    def test_create_prescription_writes_audit_log(self, client, db_session):
        from app.models import AuditLog
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        client.post("/prescriptions", json={
            "date": str(date.today()),
            "patient_id": patient.id,
            "drug_id": drug.id,
            "brand_required": 0,
            "directions": "Take daily",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": prescriber.npi,
        })
        log = db.query(AuditLog).filter(AuditLog.action == "PRESCRIPTION_CREATED").first()
        assert log is not None


# ===========================================================================
# COST CALCULATION EDGE CASES
# ===========================================================================

class TestCostCalculationEdgeCases:
    def test_total_cost_equals_drug_cost_times_quantity(self, client, db_session):
        """total_cost = drug.cost × quantity, verified via the refill record."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("2.50"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        fill(client, prescription.id, quantity=30)
        refill = db.query(RefillModel).first()
        assert Decimal(str(refill.total_cost)) == Decimal("75.00")  # 2.50 × 30

    def test_low_cost_drug_fills_correctly(self, client, db_session):
        """Drugs with very small costs (e.g., $0.01 per unit) calculate correctly."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("0.01"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        fill(client, prescription.id, quantity=30)
        refill = db.query(RefillModel).first()
        assert Decimal(str(refill.total_cost)) == Decimal("0.30")

    def test_high_cost_specialty_drug_fills_correctly(self, client, db_session):
        """High-cost specialty drugs (e.g., $500/unit) calculate correctly."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("500.00"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        fill(client, prescription.id, quantity=30)
        refill = db.query(RefillModel).first()
        assert Decimal(str(refill.total_cost)) == Decimal("15000.00")


# ===========================================================================
# CONFLICT CHECK
# ===========================================================================

class TestConflictCheck:
    def test_no_conflict_for_new_drug(self, client, db_session):
        db = db_session
        patient = make_patient(db)
        drug = make_drug(db)
        db.commit()

        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": patient.id, "drug_id": drug.id}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_conflict"] is False
        assert body["active_refills"] == []

    def test_conflict_detected_when_active_refill_exists(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, state=RxState.QT)
        db.commit()

        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": patient.id, "drug_id": drug.id}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["has_conflict"] is True
        assert len(body["active_refills"]) == 1

    def test_no_conflict_after_sold_refill(self, client, db_session):
        """A SOLD refill should not show as a conflict."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        make_refill(db, prescription, drug, patient, state=RxState.SOLD)
        db.commit()

        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": patient.id, "drug_id": drug.id}
        )
        assert resp.status_code == 200
        assert resp.json()["has_conflict"] is False

    def test_recent_fill_message_shown(self, client, db_session):
        """A RefillHist entry within 90 days populates recent_fills."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        hist = RefillHist(
            prescription_id=prescription.id,
            patient_id=patient.id,
            drug_id=drug.id,
            quantity=30,
            days_supply=30,
            completed_date=date.today() - timedelta(days=10),
            sold_date=date.today() - timedelta(days=10),
            total_cost=Decimal("15.00"),
        )
        db.add(hist)
        db.commit()

        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": patient.id, "drug_id": drug.id}
        )
        body = resp.json()
        assert body["has_conflict"] is False
        assert len(body["recent_fills"]) == 1
        assert "Next due" in body["message"]

    def test_old_fill_beyond_90_days_not_shown(self, client, db_session):
        """Fills older than 90 days should NOT appear in recent_fills."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        old_hist = RefillHist(
            prescription_id=prescription.id,
            patient_id=patient.id,
            drug_id=drug.id,
            quantity=30,
            days_supply=30,
            completed_date=date.today() - timedelta(days=100),
            sold_date=date.today() - timedelta(days=100),
            total_cost=Decimal("15.00"),
        )
        db.add(old_hist)
        db.commit()

        resp = client.get(
            "/refills/check_conflict",
            params={"patient_id": patient.id, "drug_id": drug.id}
        )
        assert resp.json()["recent_fills"] == []


# ===========================================================================
# NIOSH HAZARDOUS DRUG FLAG
# ===========================================================================

class TestNioshHazardousFlag:
    def test_niosh_drug_can_still_be_filled(self, client, db_session):
        """
        NIOSH flag is informational — it triggers a UI warning but does NOT
        block the fill in the API.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, niosh=True)  # Hazardous drug
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        resp = fill(client, prescription.id, quantity=30)
        assert resp.status_code == 200

    def test_drug_niosh_flag_reflected_in_drug_data(self, client, db_session):
        db = db_session
        drug = make_drug(db, niosh=True)
        db.commit()

        resp = client.get("/drugs")
        assert resp.status_code == 200
        drugs = resp.json()["items"]
        niosh_drugs = [d for d in drugs if d["niosh"] is True]
        assert len(niosh_drugs) >= 1


# ===========================================================================
# REFILL GET ENDPOINTS
# ===========================================================================

class TestRefillGetEndpoints:
    def test_get_refills_no_filter_returns_all(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 30)
        make_refill(db, prescription, drug, patient, state=RxState.QT)
        make_refill(db, prescription, drug, patient, state=RxState.HOLD)
        db.commit()

        resp = client.get("/refills")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

    def test_get_refills_filter_by_state(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 30)
        make_refill(db, prescription, drug, patient, state=RxState.QT)
        make_refill(db, prescription, drug, patient, state=RxState.HOLD)
        db.commit()

        resp = client.get("/refills", params={"state": "QT"})
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1
        assert resp.json()["items"][0]["state"] == "QT"

    def test_get_refills_invalid_state_returns_400(self, client, db_session):
        resp = client.get("/refills", params={"state": "INVALID"})
        assert resp.status_code == 400

    def test_get_refill_by_id(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient)
        db.commit()

        resp = client.get(f"/refills/{refill.id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == refill.id

    def test_get_nonexistent_refill_returns_404(self, client, db_session):
        resp = client.get("/refills/99999")
        assert resp.status_code == 404


# ===========================================================================
# SCHEDULED FILL: NEXT-DUE DATE CALCULATION
# ===========================================================================

class TestAutoScheduleNextFill:
    def test_scheduled_next_fill_due_date_equals_today_plus_days_supply(self, client, db_session):
        """When schedule_next_fill=True, the new refill's due_date = today + days_supply."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                              state=RxState.READY)
        db.commit()

        resp = client.post(f"/refills/{refill.id}/advance", json={"schedule_next_fill": True})
        assert resp.status_code == 200

        scheduled = db.query(RefillModel).filter(
            RefillModel.state == RxState.SCHEDULED
        ).first()
        expected_due = date.today() + timedelta(days=30)
        assert scheduled.due_date == expected_due


# ===========================================================================
# SCHEDULED → QT PROMOTION (Celery task quantity invariant)
# ===========================================================================

class TestScheduledPromotion:
    """
    Verify that promote_scheduled_refills correctly deducts remaining_quantity
    when auto-promoting SCHEDULED refills into QT.

    The task creates its own SessionLocal() session, so test data must be
    committed before calling it, and test objects must be refreshed after.
    """

    def test_promote_deducts_quantity(self, db_session):
        """Promoting a SCHEDULED refill to QT decrements remaining_quantity."""
        from app.tasks import promote_scheduled_refills
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                    state=RxState.SCHEDULED, due_date=date.today())
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=True):
            result = promote_scheduled_refills()

        assert result["promoted"] == 1
        db.expire_all()
        db.refresh(prescription)
        assert prescription.remaining_quantity == 60  # 90 - 30

    def test_promote_sets_state_to_qt(self, db_session):
        """Promoting a SCHEDULED refill sets its state to QT."""
        from app.models import Refill as RefillModel
        from app.tasks import promote_scheduled_refills
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                             state=RxState.SCHEDULED, due_date=date.today())
        db.commit()
        refill_id = refill.id

        with patch("app.tasks._acquire_lock", return_value=True):
            promote_scheduled_refills()

        db.expire_all()
        promoted = db.query(RefillModel).filter(RefillModel.id == refill_id).first()
        assert promoted.state == RxState.QT

    def test_promote_skips_when_insufficient_quantity(self, db_session):
        """A SCHEDULED refill is not promoted when remaining_quantity < refill.quantity."""
        from app.models import Refill as RefillModel
        from app.tasks import promote_scheduled_refills
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 0)  # 0 remaining
        refill = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                             state=RxState.SCHEDULED, due_date=date.today())
        db.commit()
        refill_id = refill.id

        with patch("app.tasks._acquire_lock", return_value=True):
            result = promote_scheduled_refills()

        assert result["promoted"] == 0
        db.expire_all()
        skipped = db.query(RefillModel).filter(RefillModel.id == refill_id).first()
        assert skipped.state == RxState.SCHEDULED  # unchanged
        db.refresh(prescription)
        assert prescription.remaining_quantity == 0  # unchanged

    def test_promote_skips_future_due_date(self, db_session):
        """A SCHEDULED refill whose due_date is in the future is not promoted."""
        from app.models import Refill as RefillModel
        from app.tasks import promote_scheduled_refills
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                             state=RxState.SCHEDULED, due_date=date.today() + timedelta(days=7))
        db.commit()
        refill_id = refill.id

        with patch("app.tasks._acquire_lock", return_value=True):
            result = promote_scheduled_refills()

        assert result["promoted"] == 0
        db.expire_all()
        future = db.query(RefillModel).filter(RefillModel.id == refill_id).first()
        assert future.state == RxState.SCHEDULED

    def test_promote_multiple_refills_same_prescription(self, db_session):
        """
        Two SCHEDULED refills on the same prescription — only the first is
        promoted if the prescription has enough quantity for one but not both.
        """
        from app.models import Refill as RefillModel
        from app.tasks import promote_scheduled_refills
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 30)  # only 30 left
        r1 = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                         state=RxState.SCHEDULED, due_date=date.today() - timedelta(days=1))
        r2 = make_refill(db, prescription, drug, patient, quantity=30, days_supply=30,
                         state=RxState.SCHEDULED, due_date=date.today())
        db.commit()
        r1_id, r2_id = r1.id, r2.id

        with patch("app.tasks._acquire_lock", return_value=True):
            result = promote_scheduled_refills()

        assert result["promoted"] == 1
        db.expire_all()
        states = {
            r.id: r.state
            for r in db.query(RefillModel).filter(RefillModel.id.in_([r1_id, r2_id])).all()
        }
        qt_count = sum(1 for s in states.values() if s == RxState.QT)
        scheduled_count = sum(1 for s in states.values() if s == RxState.SCHEDULED)
        assert qt_count == 1
        assert scheduled_count == 1
        db.refresh(prescription)
        assert prescription.remaining_quantity == 0


# ===========================================================================
# QUICK CODE PURGE (Celery task)
# ===========================================================================

def _make_user(db) -> User:
    u = User(username="purge_test_user", hashed_password="x", is_active=True, is_admin=False)
    db.add(u)
    db.flush()
    return u


def _make_quick_code(db, user_id: int, expires_at: datetime, used: bool = False) -> QuickCode:
    qc = QuickCode(code="TST", user_id=user_id, expires_at=expires_at, used=used)
    db.add(qc)
    db.flush()
    return qc


class TestPurgeExpiredQuickCodes:
    """
    Verify that purge_expired_quick_codes removes stale DB-backed quick codes
    while leaving recent or unexpired rows untouched.

    The task creates its own SessionLocal() session, so test data must be
    committed before calling it, and objects must be refreshed after.
    """

    def test_purges_old_expired_rows(self, db_session):
        """Rows expired more than 1 hour ago are deleted."""
        from app.tasks import purge_expired_quick_codes
        db = db_session
        user = _make_user(db)
        old_expiry = datetime.now(timezone.utc) - timedelta(hours=2)
        _make_quick_code(db, user.id, expires_at=old_expiry)
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=True):
            result = purge_expired_quick_codes()

        assert result["deleted"] == 1
        assert db.query(QuickCode).count() == 0

    def test_retains_recently_expired_rows(self, db_session):
        """Rows expired less than 1 hour ago are kept (grace window)."""
        from app.tasks import purge_expired_quick_codes
        db = db_session
        user = _make_user(db)
        recent_expiry = datetime.now(timezone.utc) - timedelta(minutes=30)
        _make_quick_code(db, user.id, expires_at=recent_expiry)
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=True):
            result = purge_expired_quick_codes()

        assert result["deleted"] == 0
        assert db.query(QuickCode).count() == 1

    def test_retains_unexpired_rows(self, db_session):
        """Active (not yet expired) rows are never deleted."""
        from app.tasks import purge_expired_quick_codes
        db = db_session
        user = _make_user(db)
        future_expiry = datetime.now(timezone.utc) + timedelta(minutes=10)
        _make_quick_code(db, user.id, expires_at=future_expiry)
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=True):
            result = purge_expired_quick_codes()

        assert result["deleted"] == 0
        assert db.query(QuickCode).count() == 1

    def test_skips_when_lock_held(self, db_session):
        """Returns skipped=True without touching the DB when lock is unavailable."""
        from app.tasks import purge_expired_quick_codes
        db = db_session
        user = _make_user(db)
        old_expiry = datetime.now(timezone.utc) - timedelta(hours=2)
        _make_quick_code(db, user.id, expires_at=old_expiry)
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=False):
            result = purge_expired_quick_codes()

        assert result == {"skipped": True}
        assert db.query(QuickCode).count() == 1  # row untouched

    def test_purges_multiple_old_rows_leaves_fresh(self, db_session):
        """Mixed table: old rows deleted, fresh row retained."""
        from app.tasks import purge_expired_quick_codes
        db = db_session
        user = _make_user(db)
        now = datetime.now(timezone.utc)
        _make_quick_code(db, user.id, expires_at=now - timedelta(hours=3))
        _make_quick_code(db, user.id, expires_at=now - timedelta(hours=5))
        _make_quick_code(db, user.id, expires_at=now + timedelta(minutes=5))  # still valid
        db.commit()

        with patch("app.tasks._acquire_lock", return_value=True):
            result = purge_expired_quick_codes()

        assert result["deleted"] == 2
        assert db.query(QuickCode).count() == 1
