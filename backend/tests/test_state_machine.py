"""
test_state_machine.py — Integration tests for POST /refills/{id}/advance.

Validates the entire fill state machine:
  QT → QV1 → QP → QV2 → READY → SOLD
with branching for HOLD and REJECTED.
"""
import pytest
from decimal import Decimal
from datetime import date

from app.models import RxState, Priority, RefillHist
from tests.conftest import (
    make_prescriber, make_drug, make_patient,
    make_prescription, make_refill,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def advance(client, refill_id, action=None, rejection_reason=None, rejected_by=None,
            schedule_next_fill=False):
    payload = {"schedule_next_fill": schedule_next_fill}
    if action:
        payload["action"] = action
    if rejection_reason:
        payload["rejection_reason"] = rejection_reason
    if rejected_by:
        payload["rejected_by"] = rejected_by
    return client.post(f"/refills/{refill_id}/advance", json=payload)


def setup_refill(db, state=RxState.QT, quantity=30, remaining_qty=60):
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, remaining_qty)
    refill = make_refill(db, prescription, drug, patient, quantity=quantity, state=state)
    db.commit()
    return prescription, refill


# ===========================================================================
# VALID FORWARD TRANSITIONS
# ===========================================================================

class TestForwardTransitions:
    def test_qt_advances_to_qv1(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QT)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QV1"

    def test_qv1_advances_to_qp(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QP"

    def test_qp_advances_to_qv2(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QP)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QV2"

    def test_qv2_advances_to_ready(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV2)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "READY"

    def test_ready_advances_to_sold(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.READY)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "SOLD"

    def test_full_workflow_qt_to_sold(self, client, db_session):
        """Full happy path: QT → QV1 → QP → QV2 → READY → SOLD in one test."""
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, 90, 60)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QT)
        db_session.commit()

        transitions = [
            ("advance", "QV1"),
            ("advance", "QP"),
            ("advance", "QV2"),
            ("advance", "READY"),
            ("advance", "SOLD"),
        ]
        for action_label, expected_state in transitions:
            resp = advance(client, refill.id)
            assert resp.status_code == 200, f"Failed at {expected_state}: {resp.json()}"
            assert resp.json()["state"] == expected_state


# ===========================================================================
# READY STATE SIDE EFFECTS
# ===========================================================================

class TestReadyStateSideEffects:
    def test_advancing_to_ready_sets_completed_date(self, client, db_session):
        """When a refill reaches READY, completed_date is set to today."""
        _, refill = setup_refill(db_session, RxState.QV2)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        body = resp.json()
        assert body["completed_date"] == str(date.today())

    def test_advancing_to_ready_assigns_bin_number(self, client, db_session):
        """A random bin number (1-100) is assigned when refill becomes READY."""
        _, refill = setup_refill(db_session, RxState.QV2)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        bin_num = resp.json()["bin_number"]
        assert bin_num is not None
        assert 1 <= bin_num <= 100


# ===========================================================================
# SOLD STATE SIDE EFFECTS
# ===========================================================================

class TestSoldStateSideEffects:
    def test_sold_archives_to_refill_hist(self, client, db_session):
        """Advancing to SOLD must write a row to refill_hist."""
        prescription, refill = setup_refill(db_session, RxState.READY)
        resp = advance(client, refill.id)
        assert resp.status_code == 200

        hist = db_session.query(RefillHist).filter(
            RefillHist.prescription_id == prescription.id
        ).first()
        assert hist is not None
        assert hist.sold_date == date.today()
        assert hist.quantity == refill.quantity

    def test_sold_archives_correct_cost(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db, cost=Decimal("2.50"))
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.READY)
        db.commit()

        advance(client, refill.id)
        hist = db.query(RefillHist).first()
        assert hist is not None
        assert Decimal(str(hist.total_cost)) == Decimal("75.00")  # 2.50 × 30

    def test_sold_no_further_transitions(self, client, db_session):
        """SOLD is a terminal state — advancing again should return 400."""
        _, refill = setup_refill(db_session, RxState.SOLD)
        resp = advance(client, refill.id)
        assert resp.status_code == 400
        assert "transition" in resp.json()["detail"].lower()

    def test_sold_with_schedule_next_fill_creates_scheduled_refill(self, client, db_session):
        """When schedule_next_fill=True, a new SCHEDULED refill is created."""
        from app.models import Refill
        prescription, refill = setup_refill(db_session, RxState.READY, quantity=30)

        resp = advance(client, refill.id, schedule_next_fill=True)
        assert resp.status_code == 200

        scheduled = db_session.query(Refill).filter(
            Refill.prescription_id == prescription.id,
            Refill.state == RxState.SCHEDULED,
        ).first()
        assert scheduled is not None
        assert scheduled.quantity == 30

    def test_sold_without_schedule_does_not_create_next_fill(self, client, db_session):
        """Default behavior: no next SCHEDULED refill created."""
        from app.models import Refill
        _, refill = setup_refill(db_session, RxState.READY)
        advance(client, refill.id, schedule_next_fill=False)

        count = db_session.query(Refill).filter(
            Refill.state == RxState.SCHEDULED
        ).count()
        assert count == 0


# ===========================================================================
# HOLD TRANSITIONS
# ===========================================================================

class TestHoldTransitions:
    def test_qt_can_go_to_hold(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QT)
        resp = advance(client, refill.id, action="hold")
        assert resp.status_code == 200
        assert resp.json()["state"] == "HOLD"

    def test_qv1_can_go_to_hold(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(client, refill.id, action="hold")
        assert resp.status_code == 200
        assert resp.json()["state"] == "HOLD"

    def test_qp_can_go_to_hold(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QP)
        resp = advance(client, refill.id, action="hold")
        assert resp.status_code == 200
        assert resp.json()["state"] == "HOLD"

    def test_qv2_can_go_to_hold(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV2)
        resp = advance(client, refill.id, action="hold")
        assert resp.status_code == 200
        assert resp.json()["state"] == "HOLD"

    def test_hold_returns_quantity_to_prescription(self, client, db_session):
        """
        When an ACTIVE fill is put on HOLD, the reserved quantity is returned
        to the prescription's remaining_quantity.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # remaining_qty = 60 (30 already reserved by an active fill)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QT)
        db.commit()

        advance(client, refill.id, action="hold")

        db.refresh(prescription)
        assert prescription.remaining_quantity == 90  # 60 + 30 returned

    def test_hold_from_qp_returns_quantity(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QP)
        db.commit()

        advance(client, refill.id, action="hold")

        db.refresh(prescription)
        assert prescription.remaining_quantity == 90

    def test_ready_cannot_go_to_hold(self, client, db_session):
        """READY → HOLD is not in the TRANSITIONS map."""
        _, refill = setup_refill(db_session, RxState.READY)
        resp = advance(client, refill.id, action="hold")
        assert resp.status_code == 400


# ===========================================================================
# RESUMING FROM HOLD / SCHEDULED
# ===========================================================================

class TestResumeFromNonActiveState:
    def test_hold_resumes_to_qp(self, client, db_session):
        """Advancing from HOLD moves to QP."""
        _, refill = setup_refill(db_session, RxState.HOLD, remaining_qty=90)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QP"

    def test_resume_from_hold_decrements_quantity(self, client, db_session):
        """Resuming from HOLD back into an active state re-reserves quantity."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # 90 remaining — nothing reserved yet (was returned when HOLD was set)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.HOLD)
        db.commit()

        advance(client, refill.id)  # HOLD → QP (active)

        db.refresh(prescription)
        assert prescription.remaining_quantity == 60  # 30 reserved again

    def test_resume_from_hold_fails_if_insufficient_quantity(self, client, db_session):
        """
        If quantity was consumed by another fill while on HOLD,
        resuming should fail with 409.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # Only 10 remaining but refill needs 30
        prescription = make_prescription(db, patient, drug, prescriber, 90, 10)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.HOLD)
        db.commit()

        resp = advance(client, refill.id)
        assert resp.status_code == 409
        assert "insufficient" in resp.json()["detail"].lower()

    def test_scheduled_advances_to_qp(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.SCHEDULED, remaining_qty=90)
        resp = advance(client, refill.id)
        assert resp.status_code == 200
        assert resp.json()["state"] == "QP"


# ===========================================================================
# REJECTION TRANSITIONS
# ===========================================================================

class TestRejectionTransitions:
    def test_qv1_can_be_rejected(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(
            client, refill.id,
            action="reject",
            rejection_reason="Invalid DEA number",
            rejected_by="Jane Smith RPh"
        )
        assert resp.status_code == 200
        assert resp.json()["state"] == "REJECTED"

    def test_rejection_records_reason_and_rejector(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(
            client, refill.id,
            action="reject",
            rejection_reason="Forged signature",
            rejected_by="Dr. Quality"
        )
        body = resp.json()
        assert body["rejection_reason"] == "Forged signature"
        assert body["rejected_by"] == "Dr. Quality"
        assert body["rejection_date"] == str(date.today())

    def test_rejection_without_reason_uses_default(self, client, db_session):
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(client, refill.id, action="reject")
        assert resp.status_code == 200
        assert resp.json()["rejection_reason"] == "No reason provided"
        assert resp.json()["rejected_by"] == "Unknown"

    def test_qt_cannot_be_rejected(self, client, db_session):
        """REJECTED is not a valid transition from QT."""
        _, refill = setup_refill(db_session, RxState.QT)
        resp = advance(client, refill.id, action="reject")
        assert resp.status_code == 400

    def test_qp_cannot_be_rejected(self, client, db_session):
        """QP → REJECTED is not in the TRANSITIONS map."""
        _, refill = setup_refill(db_session, RxState.QP)
        resp = advance(client, refill.id, action="reject")
        assert resp.status_code == 400

    def test_rejection_returns_quantity_to_prescription(self, client, db_session):
        """Rejecting from an active state returns reserved qty to the prescription."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # 60 remaining (30 reserved by active QV1 fill)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QV1)
        db.commit()

        advance(client, refill.id, action="reject", rejection_reason="Controlled substance abuse")

        db.refresh(prescription)
        assert prescription.remaining_quantity == 90  # quantity returned

    def test_rejected_state_has_no_further_transitions(self, client, db_session):
        """REJECTED is terminal — no further state changes allowed."""
        _, refill = setup_refill(db_session, RxState.REJECTED)
        resp = advance(client, refill.id)
        assert resp.status_code == 400

    def test_hold_can_be_rejected(self, client, db_session):
        """HOLD → REJECTED is a valid escape path."""
        _, refill = setup_refill(db_session, RxState.HOLD, remaining_qty=90)
        resp = advance(client, refill.id, action="reject")
        assert resp.status_code == 200
        assert resp.json()["state"] == "REJECTED"


# ===========================================================================
# REFILL NOT FOUND
# ===========================================================================

class TestAdvanceRefillNotFound:
    def test_nonexistent_refill_returns_404(self, client, db_session):
        resp = advance(client, 99999)
        assert resp.status_code == 404

    def test_string_id_returns_422(self, client, db_session):
        resp = client.post("/refills/abc/advance", json={})
        assert resp.status_code == 422


# ===========================================================================
# AUDIT LOG FOR STATE TRANSITIONS
# ===========================================================================

class TestStateTransitionAuditLog:
    def test_advance_writes_audit_log(self, client, db_session):
        from app.models import AuditLog
        _, refill = setup_refill(db_session, RxState.QT)
        advance(client, refill.id)
        log = db_session.query(AuditLog).filter(
            AuditLog.action == "STATE_TRANSITION"
        ).first()
        assert log is not None
        assert "QT" in log.details
        assert "QV1" in log.details

    def test_rejection_audit_log_includes_rejector(self, client, db_session):
        from app.models import AuditLog
        _, refill = setup_refill(db_session, RxState.QV1)
        advance(client, refill.id, action="reject", rejected_by="TestRPh")
        log = db_session.query(AuditLog).filter(
            AuditLog.action == "STATE_TRANSITION",
            AuditLog.details.contains("TestRPh")
        ).first()
        assert log is not None

    def test_rejection_reason_too_long_is_rejected(self, client, db_session):
        """rejection_reason over 500 chars must be rejected at the schema level."""
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(
            client, refill.id,
            action="reject",
            rejection_reason="x" * 501,
        )
        assert resp.status_code == 422

    def test_rejected_by_too_long_is_rejected(self, client, db_session):
        """rejected_by over 200 chars must be rejected at the schema level."""
        _, refill = setup_refill(db_session, RxState.QV1)
        resp = advance(
            client, refill.id,
            action="reject",
            rejected_by="x" * 201,
        )
        assert resp.status_code == 422
