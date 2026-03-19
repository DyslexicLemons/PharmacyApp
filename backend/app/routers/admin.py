"""Admin-only endpoints: generate test data, view audit log, refill history."""

import random
from datetime import date as date_type, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_admin
from ..database import get_db
from ..models import (
    AuditLog, Drug, Patient, Prescription, Prescriber, Priority,
    Refill, RefillHist, RxState, SystemConfig, User,
)
from .. import schemas
from ..utils import _int

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# System config (GET for all authenticated users, PUT admin-only)
# ---------------------------------------------------------------------------

def _get_or_create_config(db: Session) -> SystemConfig:
    cfg = db.query(SystemConfig).filter(SystemConfig.id == 1).first()
    if cfg is None:
        cfg = SystemConfig(id=1, bin_count=100)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("/config", response_model=schemas.SystemConfigOut)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return current system configuration."""
    return _get_or_create_config(db)


@router.put("/config", response_model=schemas.SystemConfigOut)
def update_config(
    body: schemas.SystemConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Update system configuration. Admin-only."""
    from ..utils import _write_audit
    cfg = _get_or_create_config(db)
    cfg.bin_count = body.bin_count
    _write_audit(
        db,
        action="CONFIG_UPDATED",
        entity_type="system_config",
        entity_id=1,
        details=f"bin_count set to {body.bin_count}",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(cfg)
    return cfg


# ---------------------------------------------------------------------------
# Refill history (all users)
# ---------------------------------------------------------------------------

@router.get("/refill_hist", response_model=schemas.PaginatedResponse[schemas.RefillHistOut])
def get_refill_hist(
    limit: int = Query(100, le=1000),
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
    limit: int = Query(100, le=1000),
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
# Queue summary (admin-only)
# ---------------------------------------------------------------------------

@router.get("/queue-summary", response_model=schemas.QueueSummaryOut)
def get_queue_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Live queue depth and operational signals. Admin-only."""
    from datetime import datetime, timezone

    # Refill counts by state — one GROUP BY query
    rows = (
        db.query(Refill.state, func.count(Refill.id))
        .group_by(Refill.state)
        .all()
    )
    state_counts = {state.value: count for state, count in rows}

    counts = schemas.QueueStateCounts(
        QT=state_counts.get("QT", 0),
        QV1=state_counts.get("QV1", 0),
        QP=state_counts.get("QP", 0),
        QV2=state_counts.get("QV2", 0),
        READY=state_counts.get("READY", 0),
        HOLD=state_counts.get("HOLD", 0),
        SCHEDULED=state_counts.get("SCHEDULED", 0),
        REJECTED=state_counts.get("REJECTED", 0),
    )

    total_active = counts.QT + counts.QV1 + counts.QP + counts.QV2 + counts.READY + counts.HOLD + counts.SCHEDULED

    today = date_type.today()

    overdue_scheduled = (
        db.query(func.count(Refill.id))
        .filter(Refill.state == RxState.SCHEDULED, Refill.due_date < today)
        .scalar() or 0
    )

    expiring_soon_30d = (
        db.query(func.count(Prescription.id))
        .filter(
            Prescription.is_inactive == False,  # noqa: E712
            Prescription.expiration_date >= today,
            Prescription.expiration_date <= today + timedelta(days=30),
        )
        .scalar() or 0
    )

    return schemas.QueueSummaryOut(
        generated_at=datetime.now(timezone.utc).isoformat(),
        refills_by_state=counts,
        total_active=total_active,
        overdue_scheduled=overdue_scheduled,
        expiring_soon_30d=expiring_soon_30d,
    )


# ---------------------------------------------------------------------------
# Test data generator helpers
# ---------------------------------------------------------------------------

_FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emily", "Frank", "Grace", "Henry",
    "Isabel", "James", "Karen", "Leo", "Maria", "Nathan", "Olivia", "Paul",
    "Quinn", "Rachel", "Samuel", "Teresa", "Ursula", "Victor", "Wendy",
    "Xander", "Yvonne", "Zachary", "Angela", "Brian", "Catherine", "Derek",
    "Elena", "Finn", "Georgia", "Harold", "Irene", "Julian",
]

_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Thompson", "Martinez", "Robinson", "Clark",
    "Rodriguez", "Lewis", "Lee", "Walker", "Hall", "Allen", "Young", "King",
    "Scott", "Green", "Adams", "Baker", "Nelson", "Carter", "Mitchell",
]

_STREETS = [
    "Elm St", "Oak Ave", "Pine Blvd", "Maple Dr", "Birch Ln", "Cedar Rd",
    "Spruce Ct", "Willow Way", "Aspen Pl", "Walnut St", "Hickory Ave",
    "Poplar Blvd", "Chestnut Dr", "Sycamore Ln", "Magnolia Rd",
]

_CITIES = ["Springfield", "Riverside", "Georgetown", "Lakewood", "Fairview",
           "Hillcrest", "Maplewood", "Oakdale", "Pinehurst", "Cedarville"]

_STATES_ABBR = ["AL", "AZ", "CA", "CO", "FL", "GA", "IL", "MI", "NY", "OH",
                "OR", "PA", "TX", "WA", "WI"]

_SPECIALTIES = [
    "Internal Medicine", "Family Medicine", "Cardiology", "Oncology",
    "Endocrinology", "Neurology", "Psychiatry", "Pediatrics", "Geriatrics",
    "Rheumatology",
]

_INSTRUCTIONS_POOL = [
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
]


def _rand_address() -> str:
    num = random.randint(100, 9999)
    street = random.choice(_STREETS)
    city = random.choice(_CITIES)
    state = random.choice(_STATES_ABBR)
    return f"{num} {street}, {city}, {state}"


def _rand_phone() -> str:
    return f"({random.randint(200,999)}) {random.randint(100,999)}-{random.randint(1000,9999)}"


def _unique_npi(db: Session) -> int:
    """Generate a random unique 9-digit NPI not already in the database."""
    for _ in range(50):
        npi = random.randint(100_000_000, 999_999_999)
        if not db.query(Prescriber).filter(Prescriber.npi == npi).first():
            return npi
    raise HTTPException(status_code=500, detail="Could not generate unique NPI")


# ---------------------------------------------------------------------------
# Admin console commands
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel


class _GenerateCountRequest(_BaseModel):
    count: int


class _GeneratePrescriptionsRequest(_BaseModel):
    count: int
    state: str  # any RxState value, or "RANDOM"


@router.post("/commands/generate_prescribers")
def generate_prescribers(
    body: _GenerateCountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Generate N random prescribers. Admin-only."""
    count = max(1, min(body.count, 100))
    created = []
    for _ in range(count):
        prescriber = Prescriber(
            npi=_unique_npi(db),
            first_name=random.choice(_FIRST_NAMES),
            last_name=random.choice(_LAST_NAMES),
            phone_number=_rand_phone(),
            address=_rand_address(),
            specialty=random.choice(_SPECIALTIES),
        )
        db.add(prescriber)
        created.append(prescriber)
    db.commit()
    return {"prescribers_created": len(created)}


@router.post("/commands/generate_patients")
def generate_patients(
    body: _GenerateCountRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Generate N random patients. Admin-only."""
    count = max(1, min(body.count, 200))
    from datetime import date as _date
    created = []
    for _ in range(count):
        year = random.randint(1940, 2005)
        month = random.randint(1, 12)
        day = random.randint(1, 28)
        patient = Patient(
            first_name=random.choice(_FIRST_NAMES),
            last_name=random.choice(_LAST_NAMES),
            dob=_date(year, month, day),
            address=_rand_address(),
        )
        db.add(patient)
        created.append(patient)
    db.commit()
    return {"patients_created": len(created)}


@router.post("/commands/generate_prescriptions")
def generate_prescriptions_command(
    body: _GeneratePrescriptionsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Generate N prescriptions, each with a refill in the requested state.
    state must be one of: QT, QV1, QP, QV2, READY, HOLD, SCHEDULED, REJECTED, SOLD, RANDOM.
    RANDOM distributes across all states proportionally.
    Admin-only.
    """
    valid_states = {s.value for s in RxState}
    state_arg = body.state.upper()
    if state_arg != "RANDOM" and state_arg not in valid_states:
        raise HTTPException(status_code=400, detail=f"Invalid state '{body.state}'. Valid: {sorted(valid_states)} or RANDOM")

    count = max(1, min(body.count, 500))

    patients = db.query(Patient).all()
    prescribers = db.query(Prescriber).all()
    drugs = db.query(Drug).all()

    if not patients or not prescribers or not drugs:
        raise HTTPException(status_code=400, detail="Need patients, prescribers, and drugs in database first")

    priorities = [Priority.low, Priority.normal, Priority.high, Priority.stat]
    random_state_pool = [
        RxState.QT, RxState.QT, RxState.QT,
        RxState.QV1, RxState.QV1,
        RxState.QP, RxState.QP, RxState.QP,
        RxState.QV2, RxState.QV2,
        RxState.READY, RxState.READY,
        RxState.HOLD,
        RxState.REJECTED,
        RxState.SOLD,
    ]

    created_prescriptions = 0
    created_refills = 0
    created_hists = 0

    for _ in range(count):
        patient = random.choice(patients)
        prescriber = random.choice(prescribers)
        drug = random.choice(drugs)

        refill_quantity = random.choice([30, 60, 90])
        total_refills = random.randint(1, 12)
        days_supply = random.choice([7, 14, 30, 60, 90])
        days_ago = random.randint(0, 90)
        date_received = date_type.today() - timedelta(days=days_ago)
        expiration_date = date_received.replace(year=date_received.year + 1)

        prescription = Prescription(
            drug_id=drug.id,
            daw_code=random.randint(0, 9),
            original_quantity=refill_quantity * total_refills,
            remaining_quantity=refill_quantity * total_refills,
            date_received=date_received,
            expiration_date=expiration_date,
            patient_id=patient.id,
            prescriber_id=prescriber.id,
            instructions=random.choice(_INSTRUCTIONS_POOL),
        )
        db.add(prescription)
        db.flush()
        created_prescriptions += 1

        if state_arg == "RANDOM":
            state = random.choice(random_state_pool)
        else:
            state = RxState(state_arg)

        quantity = random.choice([refill_quantity // 2, refill_quantity, refill_quantity * 2])
        quantity = min(max(quantity, 1), refill_quantity * total_refills)
        due_date = date_type.today() + timedelta(days=random.randint(-10, 30))
        total_cost = Decimal(str(drug.cost)) * quantity

        if state == RxState.SOLD:
            completed_days_ago = random.randint(5, 60)
            completed_date = date_type.today() - timedelta(days=completed_days_ago)
            sold_date = date_type.today() - timedelta(days=random.randint(0, max(0, completed_days_ago - 1)))
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
            created_hists += 1
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
                priority=random.choice(priorities),
                state=state,
                source=random.choice(["manual", "external"]),
            )
            if state == RxState.READY:
                from .refills import _assign_bin
                refill.bin_number = _assign_bin(db)  # type: ignore[assignment]
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
            created_refills += 1
            if state != RxState.REJECTED:
                prescription.remaining_quantity = max(0, _int(prescription.remaining_quantity) - quantity)  # type: ignore[assignment]

    db.commit()
    return {
        "prescriptions_created": created_prescriptions,
        "refills_created": created_refills,
        "refill_history_created": created_hists,
        "state": state_arg,
    }


@router.post("/commands/clear_prescriptions")
def clear_prescriptions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Delete ALL refills, refill history, and prescriptions. Admin-only. Destructive."""
    refill_count = db.query(Refill).count()
    hist_count = db.query(RefillHist).count()
    rx_count = db.query(Prescription).count()
    db.query(Refill).delete()
    db.query(RefillHist).delete()
    db.query(Prescription).delete()
    db.commit()
    return {
        "refills_deleted": refill_count,
        "refill_history_deleted": hist_count,
        "prescriptions_deleted": rx_count,
    }


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
                from .refills import _assign_bin
                refill.bin_number = _assign_bin(db)  # type: ignore[assignment]
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
