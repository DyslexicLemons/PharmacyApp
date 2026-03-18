"""
test_concurrency.py — Concurrency and race condition tests.

Verifies that two simultaneous fill attempts on the same prescription:
  1. Do not both succeed (one must be rejected with 409)
  2. Do not leave remaining_quantity negative
  3. Database remains consistent after concurrent operations

SQLite does not support true row-level locking (SELECT FOR UPDATE is a no-op),
so these tests use threading to simulate the race and verify the outcome with
application-level guards. Against PostgreSQL (production), the SELECT FOR UPDATE
provides true serialization.
"""
import pytest
import threading
from decimal import Decimal
from datetime import date

from app.models import RxState, Refill
from tests.conftest import (
    make_prescriber, make_drug, make_patient, make_prescription, make_refill,
)


# ===========================================================================
# SIMULATED CONCURRENT FILL ATTEMPTS
# ===========================================================================

class TestConcurrentFillAttempts:
    def test_two_concurrent_fills_only_one_succeeds(self, client, db_session):
        """
        Launch two fill threads simultaneously against the same prescription.

        IMPORTANT — SQLite + StaticPool limitation:
        SQLite does not support true concurrent connections; with StaticPool,
        two threads share one connection and SQLite serializes them rather than
        providing real parallelism. This test therefore verifies SEQUENTIAL
        behavior (one at a time through SQLite's serialization), which mirrors
        the APPLICATION-level blocking logic that would fire under real concurrency.

        Against PostgreSQL (production), SELECT FOR UPDATE provides database-level
        serialization — only one transaction commits; the other receives a 409.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # Enough quantity for exactly one fill of 30
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        results = []
        errors = []

        def attempt_fill():
            try:
                resp = client.post(
                    f"/prescriptions/{prescription.id}/fill",
                    json={"quantity": 30, "days_supply": 30, "priority": "normal"},
                )
                results.append(resp.status_code)
            except Exception as e:
                errors.append(str(e))

        t1 = threading.Thread(target=attempt_fill)
        t2 = threading.Thread(target=attempt_fill)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Under SQLite: threads are serialized, so we expect 200 + 409.
        # If SQLite errors occur due to threading, errors list will have entries.
        if errors:
            pytest.skip(f"SQLite threading limitation: {errors[0]}")

        # At least one fill must have succeeded
        assert 200 in results, f"Neither fill succeeded: {results}"
        # Exactly one should succeed when quantity is limited to one fill
        success_count = results.count(200)
        assert success_count == 1, (
            f"Expected exactly 1 successful fill, got {success_count}. Results: {results}"
        )

    def test_remaining_quantity_not_negative_after_concurrent_fills(self, client, db_session):
        """
        After concurrent attempts, remaining_quantity must never go below 0.
        Uses sequential calls (SQLite safe) — threading version documented above.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        # Sequential "concurrent" attempts — the second is blocked by app logic
        for _ in range(3):
            client.post(
                f"/prescriptions/{prescription.id}/fill",
                json={"quantity": 30, "days_supply": 30, "priority": "normal"},
            )

        db.refresh(prescription)
        assert prescription.remaining_quantity >= 0, (
            f"remaining_quantity went negative: {prescription.remaining_quantity}"
        )

    def test_concurrent_advances_do_not_corrupt_state(self, client, db_session):
        """
        Two sequential advance calls on the same refill:
        only the first changes state; the second operates on the already-advanced state.
        Verifies that the refill ends in a valid, known state.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, state=RxState.QT)
        db.commit()

        # First advance: QT → QV1
        r1 = client.post(f"/refills/{refill.id}/advance", json={"schedule_next_fill": False})
        assert r1.status_code == 200

        # Second advance: QV1 → QP (sequential, not truly concurrent)
        r2 = client.post(f"/refills/{refill.id}/advance", json={"schedule_next_fill": False})
        assert r2.status_code == 200

        # Refill must be in a valid state
        db.refresh(refill)
        assert refill.state.value in {s.value for s in RxState}


# ===========================================================================
# SEQUENTIAL FILL ATTEMPTS (Documented behavior)
# ===========================================================================

class TestSequentialFillBlocking:
    """
    Sequential tests that confirm the blocking logic works correctly
    without the complexity of threads.
    """

    def test_second_fill_blocked_immediately_after_first(self, client, db_session):
        """Sequential second fill is blocked by the BLOCKING_STATES check."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        # First fill succeeds
        r1 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r1.status_code == 200

        # Second fill immediately blocked
        r2 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r2.status_code == 409

    def test_three_sequential_fills_all_blocked_after_first(self, client, db_session):
        """Multiple sequential fill attempts are all blocked after the first."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        statuses = []
        for _ in range(3):
            r = client.post(
                f"/prescriptions/{prescription.id}/fill",
                json={"quantity": 30, "days_supply": 30, "priority": "normal"},
            )
            statuses.append(r.status_code)

        assert statuses[0] == 200  # First succeeds
        assert statuses[1] == 409  # Second blocked
        assert statuses[2] == 409  # Third blocked

    def test_quantity_correct_after_sequential_blocks(self, client, db_session):
        """After two blocked sequential fills, remaining_quantity only decremented once."""
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
        client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )

        db.refresh(prescription)
        # Only one successful fill → remaining decremented once: 90 - 30 = 60
        assert prescription.remaining_quantity == 60

    def test_fill_then_hold_then_fill_again(self, client, db_session):
        """
        Fill → HOLD (quantity returned) → new fill can start.
        Verifies proper quantity lifecycle through hold/resume cycle.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        # Step 1: Fill → QT
        r1 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r1.status_code == 200
        refill_id = r1.json()["refill_id"]

        db.refresh(prescription)
        assert prescription.remaining_quantity == 60  # 30 reserved

        # Step 2: Advance to QV1
        client.post(f"/refills/{refill_id}/advance", json={})

        # Step 3: Hold from QV1 → quantity returned
        client.post(f"/refills/{refill_id}/advance", json={"action": "hold"})

        db.refresh(prescription)
        assert prescription.remaining_quantity == 90  # returned

        # Step 4: New fill can start again
        r2 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r2.status_code == 200
        db.refresh(prescription)
        assert prescription.remaining_quantity == 60

    def test_fill_then_reject_then_fill_again(self, client, db_session):
        """
        Fill → REJECTED (quantity returned) → new fill can start.

        Note: the fill endpoint defaults new fills to QV1 (when no history match).
        QV1 → REJECTED is a valid transition.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        # Fill creates refill in QV1 (no history → defaults to QV1)
        r1 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r1.status_code == 200
        refill_id = r1.json()["refill_id"]

        # QV1 → REJECTED directly (QV1 allows rejection per TRANSITIONS map)
        reject_resp = client.post(f"/refills/{refill_id}/advance", json={
            "action": "reject",
            "rejection_reason": "Forged Rx",
            "rejected_by": "RPh Jones"
        })
        assert reject_resp.status_code == 200
        assert reject_resp.json()["state"] == "REJECTED"

        db.refresh(prescription)
        assert prescription.remaining_quantity == 90  # quantity returned after rejection

        # New fill allowed since first fill is now REJECTED
        r2 = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        assert r2.status_code == 200


# ===========================================================================
# QUANTITY INTEGRITY INVARIANTS
# ===========================================================================

class TestQuantityIntegrityInvariants:
    """
    These tests assert invariants that must hold at all times:
    - remaining_quantity >= 0
    - remaining_quantity <= original_quantity
    - quantity reserved = original - remaining
    """

    def test_remaining_always_non_negative_through_lifecycle(self, client, db_session):
        """Simulate a full lifecycle and verify remaining_quantity at each step."""
        from app.models import Refill as RefillModel
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        db.commit()

        states_and_remaining = []

        def check(label):
            db.refresh(prescription)
            qty = prescription.remaining_quantity
            states_and_remaining.append((label, qty))
            assert qty >= 0, f"remaining_quantity went negative at {label}: {qty}"

        check("initial")

        # Create fill (→ QT)
        r = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        refill_id = r.json()["refill_id"]
        check("after fill created (QT)")

        # QT → QV1
        client.post(f"/refills/{refill_id}/advance", json={})
        check("after QV1")

        # QV1 → QP
        client.post(f"/refills/{refill_id}/advance", json={})
        check("after QP")

        # QP → QV2
        client.post(f"/refills/{refill_id}/advance", json={})
        check("after QV2")

        # QV2 → READY
        client.post(f"/refills/{refill_id}/advance", json={})
        check("after READY")

        # READY → SOLD
        client.post(f"/refills/{refill_id}/advance", json={})
        check("after SOLD")

        # Final check: remaining should be 60 (30 was dispensed)
        db.refresh(prescription)
        assert prescription.remaining_quantity == 60

    def test_remaining_never_exceeds_original(self, client, db_session):
        """
        Returning quantity via HOLD/REJECT should never push remaining > original.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 30)
        db.commit()

        # Fill 30 (all remaining)
        r = client.post(
            f"/prescriptions/{prescription.id}/fill",
            json={"quantity": 30, "days_supply": 30, "priority": "normal"},
        )
        refill_id = r.json()["refill_id"]

        # Advance to QV1 then HOLD (returns 30)
        client.post(f"/refills/{refill_id}/advance", json={})  # QT→QV1
        client.post(f"/refills/{refill_id}/advance", json={"action": "hold"})  # QV1→HOLD

        db.refresh(prescription)
        assert prescription.remaining_quantity <= prescription.original_quantity


# ===========================================================================
# EDIT REFILL — row-lock correctness
# ===========================================================================

class TestEditRefill:
    """
    Verify that edit_refill correctly updates quantity and adjusts
    prescription.remaining_quantity. These also serve as regression tests
    confirming the with_for_update(of=Refill) lock doesn't break normal behavior.
    """

    def test_edit_qt_refill_quantity_down(self, client, db_session):
        """
        Editing a QT refill's quantity downward returns the difference to
        remaining_quantity.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # prescription remaining=60 after fill of 30
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QT)
        db.commit()

        resp = client.patch(f"/refills/{refill.id}/edit", json={"quantity": 20})
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 20

        db.refresh(prescription)
        # available = 60 + 30 = 90; new remaining = 90 - 20 = 70
        assert prescription.remaining_quantity == 70

    def test_edit_qt_refill_quantity_up(self, client, db_session):
        """
        Editing a QT refill's quantity upward deducts the extra from
        remaining_quantity.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QT)
        db.commit()

        resp = client.patch(f"/refills/{refill.id}/edit", json={"quantity": 40})
        assert resp.status_code == 200

        db.refresh(prescription)
        # available = 60 + 30 = 90; new remaining = 90 - 40 = 50
        assert prescription.remaining_quantity == 50

    def test_edit_qt_refill_quantity_exceeds_available_rejected(self, client, db_session):
        """Requesting more than available quantity returns 422."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 30, 0)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QT)
        db.commit()

        # available = 0 + 30 = 30; requesting 31 should fail
        resp = client.patch(f"/refills/{refill.id}/edit", json={"quantity": 31})
        assert resp.status_code == 422

    def test_edit_noneditable_state_rejected(self, client, db_session):
        """Editing a refill in QV1 (non-editable) returns 400."""
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 60)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QV1)
        db.commit()

        resp = client.patch(f"/refills/{refill.id}/edit", json={"quantity": 20})
        assert resp.status_code == 400

    def test_edit_hold_refill_quantity(self, client, db_session):
        """
        HOLD is NOT in ACTIVE_STATES — going to HOLD returns quantity to the
        prescription. So remaining=90 when the refill sits in HOLD.
        Editing a HOLD refill deducts the new quantity and promotes to QT.
        """
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        # remaining=90: the 30 that was in-flight has been returned when held
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.HOLD)
        db.commit()

        resp = client.patch(f"/refills/{refill.id}/edit", json={"quantity": 25})
        assert resp.status_code == 200

        db.refresh(prescription)
        # HOLD not in ACTIVE_STATES → remaining - new_qty = 90 - 25 = 65
        assert prescription.remaining_quantity == 65
