"""Admin-only endpoints: generate test data, view audit log, refill history."""

import random
from datetime import date as date_type, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import (
    AuditLog, Drug, Patient, Prescription, Prescriber, Priority,
    Refill, RefillHist, RxState, User,
)
from .. import schemas
from ..utils import _int

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Refill history (all users)
# ---------------------------------------------------------------------------

@router.get("/refill_hist", response_model=schemas.PaginatedResponse[schemas.RefillHistOut])
def get_refill_hist(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(RefillHist).count()
    items = db.query(RefillHist).order_by(desc(RefillHist.id)).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Audit log (admin-only)
# ---------------------------------------------------------------------------

@router.get("/audit_log", response_model=schemas.PaginatedResponse[schemas.AuditLogOut])
def get_audit_log(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    prescription_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Paginated audit log viewer. Admin-only."""
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if user_id is not None:
        q = q.filter(AuditLog.user_id == user_id)
    if username:
        q = q.filter(AuditLog.performed_by == username)
    if prescription_id is not None:
        q = q.filter(AuditLog.prescription_id == prescription_id)
    total = q.count()
    items = q.order_by(desc(AuditLog.timestamp)).offset(offset).limit(limit).all()

    # Serialize timestamp to ISO string for JSON compatibility
    result = []
    for entry in items:
        result.append(schemas.AuditLogOut(
            id=entry.id,
            timestamp=entry.timestamp.isoformat() if entry.timestamp else "",
            action=entry.action,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            prescription_id=entry.prescription_id,
            details=entry.details,
            performed_by=entry.performed_by,
        ))
    return {"items": result, "total": total, "limit": limit, "offset": offset}


# ---------------------------------------------------------------------------
# Test data generator (admin-only — destructive!)
# ---------------------------------------------------------------------------

@router.post("/commands/generate_test_prescriptions")
def generate_test_prescriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate 50 random test prescriptions.
    Removes ALL existing prescriptions and refills first.
    WARNING: destructive — admin-only, for development use.
    """
    db.query(Refill).delete()
    db.query(RefillHist).delete()
    db.query(Prescription).delete()
    db.commit()

    patients = db.query(Patient).all()
    prescribers = db.query(Prescriber).all()
    drugs = db.query(Drug).all()

    if not patients or not prescribers or not drugs:
        raise HTTPException(
            status_code=400,
            detail="Need patients, prescribers, and drugs in database first",
        )

    states_distribution = [
        (RxState.QT, 8),
        (RxState.QV1, 6),
        (RxState.QP, 10),
        (RxState.QV2, 7),
        (RxState.READY, 8),
        (RxState.HOLD, 3),
        (RxState.REJECTED, 2),
        (RxState.SOLD, 6),
    ]

    priorities = [Priority.low, Priority.normal, Priority.high, Priority.stat]

    instructions_pool = [
        "Take 1 tablet by mouth once daily in the morning",
        "Take 1 tablet by mouth twice daily with food",
        "Take 2 tablets by mouth every 4 to 6 hours as needed for pain",
        "Take 1 capsule by mouth three times daily until finished",
        "Take 1 tablet by mouth every 8 hours with food as needed for pain",
        "Take 1 tablet by mouth once daily for blood pressure",
        "Take 1 tablet by mouth daily for cardiovascular protection",
        "Take 1 tablet by mouth three times daily with meals",
        "Take 1 tablet by mouth daily, INR monitoring required",
        "Take 1 tablet by mouth once daily at bedtime",
        "Take 1 tablet by mouth every 12 hours",
        "Take 1 capsule by mouth once daily on an empty stomach",
        "Inject 10 units subcutaneously once daily before breakfast",
        "Apply 1 patch to skin once weekly, rotate sites",
        "Inhale 2 puffs by mouth every 4 to 6 hours as needed",
        "Take 1 tablet by mouth once daily at the same time each day",
        "Take 1 tablet by mouth twice daily, do not crush or chew",
        "Administer 1 vial by IV infusion every 4 weeks as directed",
        "Take 1 tablet by mouth once weekly on the same day each week",
    ]

    state_pool: list = []
    for state, count in states_distribution:
        state_pool.extend([state] * count)

    created_prescriptions = []
    created_refills = []
    created_refill_hists = []

    for _ in range(50):
        patient = random.choice(patients)
        prescriber = random.choice(prescribers)
        drug = random.choice(drugs)

        refill_quantity = random.choice([30, 60, 90])
        total_refills = random.randint(1, 12)
        days_supply = random.choice([7, 14, 30, 60, 90])
        daw_code = random.randint(0, 9)
        days_ago = random.randint(0, 90)
        date_received = date_type.today() - timedelta(days=days_ago)

        expiration_date = date_received.replace(year=date_received.year + 1)

        prescription = Prescription(
            drug_id=drug.id,
            daw_code=daw_code,
            original_quantity=refill_quantity * total_refills,
            remaining_quantity=refill_quantity * total_refills,
            date_received=date_received,
            expiration_date=expiration_date,
            patient_id=patient.id,
            prescriber_id=prescriber.id,
            instructions=random.choice(instructions_pool),
        )
        db.add(prescription)
        db.flush()
        created_prescriptions.append(prescription)

        state = random.choice(state_pool)
        priority = random.choice(priorities)
        quantity = random.choice([refill_quantity // 2, refill_quantity, refill_quantity * 2])
        quantity = min(max(quantity, 1), refill_quantity * total_refills)
        due_date = date_type.today() + timedelta(days=random.randint(-10, 30))
        total_cost = Decimal(str(drug.cost)) * quantity

        if state == RxState.SOLD:
            completed_days_ago = random.randint(5, 60)
            completed_date = date_type.today() - timedelta(days=completed_days_ago)
            sold_days_ago = random.randint(0, max(0, completed_days_ago - 1))
            sold_date = date_type.today() - timedelta(days=sold_days_ago)
            refill_hist = RefillHist(
                prescription_id=prescription.id,
                patient_id=patient.id,
                drug_id=drug.id,
                quantity=quantity,
                days_supply=days_supply,
                completed_date=completed_date,
                sold_date=sold_date,
                total_cost=total_cost,
            )
            db.add(refill_hist)
            created_refill_hists.append(refill_hist)
            prescription.remaining_quantity = max(0, _int(prescription.remaining_quantity) - quantity)  # type: ignore[assignment]
        else:
            refill = Refill(
                prescription_id=prescription.id,
                patient_id=patient.id,
                drug_id=drug.id,
                due_date=due_date,
                quantity=quantity,
                days_supply=days_supply,
                total_cost=total_cost,
                priority=priority,
                state=state,
                source=random.choice(["manual", "external"]),
            )
            if state == RxState.READY:
                refill.bin_number = random.randint(1, 100)  # type: ignore[assignment]
                refill.completed_date = date_type.today() - timedelta(days=random.randint(0, 5))  # type: ignore[assignment]
            elif state == RxState.REJECTED:
                refill.rejected_by = f"PharmD {random.choice(['Smith', 'Jones', 'Brown', 'Davis'])}"  # type: ignore[assignment]
                refill.rejection_reason = random.choice([  # type: ignore[assignment]
                    "Incorrect quantity — prescriber authorization needed",
                    "Patient allergy on file",
                    "Duplicate therapy detected",
                    "Insurance rejection — prior authorization required",
                    "Incorrect dosage form",
                ])
                refill.rejection_date = date_type.today() - timedelta(days=random.randint(0, 10))  # type: ignore[assignment]
            db.add(refill)
            created_refills.append(refill)
            if state != RxState.REJECTED:
                prescription.remaining_quantity = max(0, _int(prescription.remaining_quantity) - quantity)  # type: ignore[assignment]

    db.commit()

    return {
        "message": "Generated test prescriptions successfully",
        "prescriptions_created": len(created_prescriptions),
        "active_refills_created": len(created_refills),
        "refill_history_created": len(created_refill_hists),
        "state_distribution": {
            state.value: len([r for r in created_refills if r.state == state])
            for state, _ in states_distribution if state != RxState.SOLD
        },
        "sold_prescriptions": len(created_refill_hists),
    }
