"""Refill workflow endpoints — advance, edit, upload, conflict check."""

import random
from datetime import date as date_type, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, desc
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Drug, Patient, Prescription, Prescriber, Priority, Refill,
    RefillHist, RxState, PatientInsurance, User,
)
from .. import schemas
from ..utils import _int, _parse_priority, _write_audit
import logging

logger = logging.getLogger("pharmacy.rx")

router = APIRouter(prefix="/refills", tags=["refills"])

# ---------------------------------------------------------------------------
# State machine constants
# ---------------------------------------------------------------------------

ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}
BLOCKING_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

TRANSITIONS = {
    RxState.QT:        [RxState.QV1, RxState.HOLD],
    RxState.QV1:       [RxState.QP, RxState.HOLD, RxState.REJECTED],
    RxState.QP:        [RxState.QV2, RxState.HOLD],
    RxState.QV2:       [RxState.READY, RxState.QP, RxState.HOLD],
    RxState.HOLD:      [RxState.QP, RxState.REJECTED],
    RxState.SCHEDULED: [RxState.QP, RxState.HOLD, RxState.REJECTED],
    RxState.READY:     [RxState.SOLD],
}

# ---------------------------------------------------------------------------
# IMPORTANT: /check_conflict MUST be declared before /{rx_id}
# so FastAPI doesn't try to coerce the literal string into an integer.
# ---------------------------------------------------------------------------

@router.get("/check_conflict", response_model=schemas.ConflictCheckResponse)
def check_refill_conflict(
    patient_id: int,
    drug_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check for duplicate or conflicting refills before creating a new prescription."""
    active_refills = db.query(Refill).filter(
        and_(
            Refill.patient_id == patient_id,
            Refill.drug_id == drug_id,
            Refill.state != RxState.SOLD,
        )
    ).all()

    ninety_days_ago = date_type.today() - timedelta(days=90)
    recent_fills = db.query(RefillHist).filter(
        and_(
            RefillHist.patient_id == patient_id,
            RefillHist.drug_id == drug_id,
            RefillHist.sold_date >= ninety_days_ago,
        )
    ).all()

    has_conflict = len(active_refills) > 0

    active_data = [
        {"id": r.id, "state": str(r.state), "due_date": str(r.due_date), "quantity": r.quantity}
        for r in active_refills
    ]
    recent_data = [
        {"id": r.id, "sold_date": str(r.sold_date), "days_supply": r.days_supply, "quantity": r.quantity}
        for r in recent_fills
    ]

    message = None
    if has_conflict:
        message = f"Patient already has {len(active_refills)} active refill(s) for this drug"
    elif recent_fills:
        latest = recent_fills[0]
        days = _int(latest.days_supply) or 30
        next_due = latest.sold_date + timedelta(days=days)
        message = f"Recent fill on {latest.sold_date}. Next due: {next_due}"

    return schemas.ConflictCheckResponse(
        has_conflict=has_conflict,
        active_refills=active_data,
        recent_fills=recent_data,
        message=message,
    )


@router.get("", response_model=schemas.PaginatedResponse[schemas.RefillOut])
def get_refills(
    state: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Refill)
    if state and state != "ALL":
        try:
            state_enum = RxState(state)
            query = query.filter(Refill.state == state_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{rx_id}", response_model=schemas.RefillOut)
def get_refill(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber),
    ).filter(Refill.id == rx_id).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")
    return rx


@router.post("/{rx_id}/advance", response_model=schemas.RefillOut)
def advance_refill(
    rx_id: int,
    payload: schemas.AdvanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber),
    ).filter(Refill.id == rx_id).first()

    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")

    raw_state = rx.state
    current_state_enum = raw_state if isinstance(raw_state, RxState) else RxState(str(raw_state))

    if current_state_enum not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")

    valid_next_states = TRANSITIONS[current_state_enum]
    new_state = current_state_enum

    if payload.action == "reject":
        if RxState.REJECTED in valid_next_states:
            new_state = RxState.REJECTED
            rx.rejected_by = payload.rejected_by or "Unknown"          # type: ignore[assignment]
            rx.rejection_reason = payload.rejection_reason or "No reason provided"  # type: ignore[assignment]
            rx.rejection_date = date_type.today()                      # type: ignore[assignment]
        else:
            raise HTTPException(status_code=400, detail="Cannot reject from this state")

    elif payload.action == "hold":
        if RxState.HOLD in valid_next_states:
            new_state = RxState.HOLD
        else:
            raise HTTPException(status_code=400, detail="Cannot hold from this state")

    else:
        if current_state_enum == RxState.QV1:
            new_state = RxState.QP
        elif current_state_enum == RxState.QV2:
            new_state = RxState.READY
            rx.bin_number = random.randint(1, 100)  # type: ignore[assignment]
        else:
            new_state = valid_next_states[0]

    if new_state == RxState.READY:
        rx.completed_date = date_type.today()  # type: ignore[assignment]

    logger.info(
        f"[RX STATE] Refill #{rx_id} (Rx #{rx.prescription_id}, patient #{rx.patient_id}): "
        f"{current_state_enum.value} → {new_state.value}"
    )

    rx_quantity = _int(rx.quantity)
    rx_days_supply = _int(rx.days_supply)

    if current_state_enum not in ACTIVE_STATES and new_state in ACTIVE_STATES:
        prescription = (
            db.query(Prescription)
            .filter(Prescription.id == rx.prescription_id)
            .with_for_update()
            .first()
        )
        if prescription:
            rx_remaining = _int(prescription.remaining_quantity)
            if rx_remaining < rx_quantity:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Insufficient remaining quantity on prescription to resume this fill "
                        f"(remaining={rx_remaining}, needed={rx_quantity})"
                    ),
                )
            prescription.remaining_quantity = max(0, rx_remaining - rx_quantity)  # type: ignore[assignment]
            logger.info(
                f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
                f"{rx_remaining} → {prescription.remaining_quantity} (resumed fill, state={new_state.value})"
            )

    elif current_state_enum in ACTIVE_STATES and new_state not in ACTIVE_STATES and new_state != RxState.SOLD:
        prescription = (
            db.query(Prescription)
            .filter(Prescription.id == rx.prescription_id)
            .with_for_update()
            .first()
        )
        if prescription:
            old_qty = _int(prescription.remaining_quantity)
            prescription.remaining_quantity = old_qty + rx_quantity  # type: ignore[assignment]
            logger.info(
                f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
                f"{old_qty} → {prescription.remaining_quantity} (fill paused/cancelled, state={new_state.value})"
            )

    rx.state = new_state  # type: ignore[assignment]

    if new_state == RxState.SOLD:
        rx_completed = rx.completed_date
        hist = RefillHist(
            prescription_id=rx.prescription_id,
            patient_id=rx.patient_id,
            drug_id=rx.drug_id,
            quantity=rx_quantity,
            days_supply=rx_days_supply,
            completed_date=rx_completed or date_type.today(),
            sold_date=date_type.today(),
            total_cost=Decimal(str(rx.total_cost)),
            insurance_id=rx.insurance_id,
            copay_amount=Decimal(str(rx.copay_amount)) if rx.copay_amount is not None else None,
            insurance_paid=Decimal(str(rx.insurance_paid)) if rx.insurance_paid is not None else None,
        )
        db.add(hist)
        logger.info(f"[RX HIST] Refill #{rx_id}: archived to RefillHist (qty={rx_quantity}, drug_id={rx.drug_id})")

        if payload.schedule_next_fill:
            next_due = date_type.today() + timedelta(days=rx_days_supply)
            scheduled = Refill(
                prescription_id=rx.prescription_id,
                patient_id=rx.patient_id,
                drug_id=rx.drug_id,
                due_date=next_due,
                quantity=rx_quantity,
                days_supply=rx_days_supply,
                total_cost=Decimal(str(rx.total_cost)),
                priority=rx.priority,
                state=RxState.SCHEDULED,
                source="auto_schedule",
                insurance_id=rx.insurance_id,
                copay_amount=Decimal(str(rx.copay_amount)) if rx.copay_amount is not None else None,
                insurance_paid=Decimal(str(rx.insurance_paid)) if rx.insurance_paid is not None else None,
            )
            db.add(scheduled)
            logger.info(f"[RX SCHED] Prescription #{rx.prescription_id}: next fill scheduled for {next_due}")

    _write_audit(
        db, "STATE_TRANSITION",
        entity_type="refill", entity_id=rx_id,
        prescription_id=rx.prescription_id,
        details=(
            f"{current_state_enum.value} → {new_state.value} "
            f"prescription_id={rx.prescription_id} patient_id={rx.patient_id}"
            + (f" rejected_by={rx.rejected_by}" if new_state == RxState.REJECTED else "")
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(rx)
    return rx


@router.patch("/{rx_id}/edit", response_model=schemas.RefillOut)
def edit_refill(
    rx_id: int,
    payload: schemas.RefillEditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit a refill in QT, QP, or HOLD state."""
    EDITABLE_STATES = {RxState.QT, RxState.QP, RxState.HOLD}

    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber),
    ).filter(Refill.id == rx_id).first()

    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")

    raw_state = rx.state
    current_state = raw_state if isinstance(raw_state, RxState) else RxState(str(raw_state))

    if current_state not in EDITABLE_STATES:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot edit a refill in state {current_state.value}. Only QT, QP, and HOLD are editable.",
        )

    old_quantity = _int(rx.quantity)
    new_quantity = payload.quantity if payload.quantity is not None else old_quantity

    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == rx.prescription_id)
        .with_for_update()
        .first()
    )

    if prescription:
        remaining = _int(prescription.remaining_quantity)
        if current_state in ACTIVE_STATES:
            available = remaining + old_quantity
            if new_quantity > available:
                raise HTTPException(
                    status_code=422,
                    detail=f"Requested quantity ({new_quantity}) exceeds authorized remaining ({available})",
                )
            prescription.remaining_quantity = available - new_quantity  # type: ignore[assignment]
        else:
            if new_quantity > remaining:
                raise HTTPException(
                    status_code=422,
                    detail=f"Requested quantity ({new_quantity}) exceeds remaining authorized quantity ({remaining})",
                )
            prescription.remaining_quantity = remaining - new_quantity  # type: ignore[assignment]

        if payload.instructions is not None:
            prescription.instructions = payload.instructions  # type: ignore[assignment]
        if payload.brand_required is not None:
            prescription.brand_required = payload.brand_required  # type: ignore[assignment]

    if payload.quantity is not None:
        rx.quantity = payload.quantity  # type: ignore[assignment]
        drug = rx.drug
        rx.total_cost = Decimal(str(drug.cost)) * payload.quantity  # type: ignore[assignment]
    if payload.days_supply is not None:
        rx.days_supply = payload.days_supply  # type: ignore[assignment]
    if payload.priority is not None:
        rx.priority = _parse_priority(payload.priority)  # type: ignore[assignment]
    if payload.due_date is not None:
        rx.due_date = payload.due_date  # type: ignore[assignment]

    if current_state == RxState.QT:
        new_state = RxState.QT
    elif current_state == RxState.QP:
        new_state = RxState.QV1
    else:
        new_state = RxState.QT

    old_state_str = current_state.value
    rx.state = new_state  # type: ignore[assignment]

    logger.info(
        f"[RX EDIT] Refill #{rx_id}: edited {old_state_str} → {new_state.value} "
        f"qty={_int(rx.quantity)} days={_int(rx.days_supply)}"
    )
    _write_audit(
        db, "REFILL_EDITED",
        entity_type="refill", entity_id=rx_id,
        prescription_id=rx.prescription_id,
        details=(
            f"prior_state={old_state_str} new_state={new_state.value} "
            f"qty={_int(rx.quantity)} days_supply={_int(rx.days_supply)} "
            f"prescription_id={rx.prescription_id} patient_id={rx.patient_id}"
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(rx)
    return rx


@router.post("/upload_json")
def upload_json_prescription(
    data: schemas.JSONPrescriptionUpload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload external JSON prescription — goes to QT queue for triage."""
    for key in ("first_name", "last_name", "dob"):
        if key not in data.patient:
            raise HTTPException(status_code=422, detail=f"patient.{key} is required")
    if "npi" not in data.prescriber:
        raise HTTPException(status_code=422, detail="prescriber.npi is required")
    for key in ("name", "manufacturer"):
        if key not in data.drug:
            raise HTTPException(status_code=422, detail=f"drug.{key} is required")

    patient = db.query(Patient).filter(
        and_(
            Patient.first_name.ilike(data.patient["first_name"]),
            Patient.last_name.ilike(data.patient["last_name"]),
            Patient.dob == data.patient.get("dob"),
        )
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found — must exist in system")

    prescriber = db.query(Prescriber).filter(Prescriber.npi == data.prescriber["npi"]).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found — must exist in system")

    from ..models import Drug as DrugModel
    drug = db.query(DrugModel).filter(
        and_(
            DrugModel.drug_name.ilike(data.drug["name"]),
            DrugModel.manufacturer.ilike(data.drug["manufacturer"]),
        )
    ).first()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found — must exist in system")

    priority = _parse_priority(data.priority)

    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=data.refill_quantity * data.total_refills,
        remaining_quantity=data.refill_quantity * data.total_refills,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=data.date,
        instructions=data.directions,
        brand_required=data.brand_required,
    )
    db.add(prescription)
    db.flush()

    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=data.date,
        quantity=data.refill_quantity,
        days_supply=30,
        total_cost=Decimal(str(drug.cost)) * data.refill_quantity,
        priority=priority,
        state=RxState.QT,
        source="external",
    )
    db.add(refill)

    old_qty = data.refill_quantity * data.total_refills
    prescription.remaining_quantity = max(0, old_qty - data.refill_quantity)  # type: ignore[assignment]

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        prescription_id=_int(prescription.id),
        details=f"source=external prescription_id={prescription.id} state=QT qty={data.refill_quantity}",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(refill)
    return {"message": "Prescription uploaded successfully", "refill_id": refill.id, "state": "QT"}


@router.post("/create_manual")
def create_manual_prescription(
    data: schemas.ManualPrescriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create manual prescription — goes to QP, HOLD, or SCHEDULED based on input."""
    patient = db.get(Patient, data.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    from ..models import Drug as DrugModel
    drug = db.get(DrugModel, data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    prescriber = db.get(Prescriber, data.prescriber_id)
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found")

    priority = _parse_priority(data.priority)
    expiration = data.expiration_date or (date_type.today() + timedelta(days=365))

    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=data.quantity * data.total_refills,
        remaining_quantity=data.quantity * data.total_refills,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=data.date_received or date_type.today(),
        expiration_date=expiration,
        brand_required=data.brand_required,
        instructions=data.instructions,
        picture=data.picture,
    )
    db.add(prescription)
    db.flush()

    state_map = {"QP": RxState.QP, "SCHEDULED": RxState.SCHEDULED, "HOLD": RxState.HOLD}
    initial_state = state_map[data.initial_state]

    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=data.due_date or date_type.today(),
        quantity=data.quantity,
        days_supply=data.days_supply,
        total_cost=Decimal(str(drug.cost)) * data.quantity,
        priority=priority,
        state=initial_state,
        source="manual",
    )
    db.add(refill)

    if initial_state in ACTIVE_STATES:
        old_qty = data.quantity * data.total_refills
        prescription.remaining_quantity = max(0, old_qty - data.quantity)  # type: ignore[assignment]

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        prescription_id=_int(prescription.id),
        details=(
            f"source=manual prescription_id={prescription.id} state={initial_state.value} "
            f"qty={data.quantity} days={data.days_supply}"
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(refill)
    return {"message": "Prescription created successfully", "refill_id": refill.id, "state": str(initial_state)}
