"""Refill workflow endpoints — advance, edit, upload, conflict check."""

import random
from datetime import date as date_type, timedelta
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session, joinedload, selectinload

from pydantic import TypeAdapter

from ..auth import get_current_user, require_pharmacist
from ..database import get_db
from ..models import (
    Drug, Patient, Prescription, Prescriber, Priority, Refill,
    RefillHist, RxState, PatientInsurance, SystemConfig, User,
)
from .. import cache, schemas
from ..utils import _int, _mask_patient_id, _parse_priority, _write_audit
import logging

logger = logging.getLogger("pharmacy.rx")

router = APIRouter(prefix="/refills", tags=["refills"])

# TypeAdapters are built once at import time — reused for every cache write.
_queue_ta: TypeAdapter = TypeAdapter(schemas.PaginatedResponse[schemas.RefillOut])  # type: ignore[type-arg]
_refill_ta: TypeAdapter = TypeAdapter(schemas.RefillOut)

# ---------------------------------------------------------------------------
# State machine constants
# ---------------------------------------------------------------------------

ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

# States that a pharmacist (RPh) must be the actor advancing *from*.
# QV1 and QV2 are pharmacist verification steps — a technician may not complete them.
PHARMACIST_REQUIRED_STATES = {RxState.QV1, RxState.QV2}

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


_QUEUE_CACHE_TTL = 30   # seconds — short because staff actively works the queue
_REFILL_CACHE_TTL = 60  # seconds


def _invalidate_queue_for_states(states: set[str]) -> None:
    """Invalidate queue cache keys only for the affected states (plus ALL).

    More targeted than nuking refills:queue:* — a QT→QV1 transition only
    affects pharmacists watching the QT or QV1 filtered views, not every
    cached page variant.
    """
    for state in states | {"ALL"}:
        cache.cache_delete_pattern(f"refills:queue:{state}:*")


@router.get("", response_model=schemas.PaginatedResponse[schemas.RefillOut])
def get_refills(
    state: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = f"refills:queue:{state or 'ALL'}:{limit}:{offset}"
    cached = cache.cache_get(cache_key)
    if cached is not None:
        return cached

    query = db.query(Refill)
    if state and state != "ALL":
        try:
            state_enum = RxState(state)
            query = query.filter(Refill.state == state_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
    total = query.count()
    items = (
        query
        .options(
            joinedload(Refill.prescription).joinedload(Prescription.patient),
            joinedload(Refill.prescription).joinedload(Prescription.drug),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = {"items": items, "total": total, "limit": limit, "offset": offset}
    cache.cache_set(
        cache_key,
        _queue_ta.validate_python(result, from_attributes=True).model_dump(mode="json"),
        _QUEUE_CACHE_TTL,
    )
    return result


@router.get("/{rx_id}", response_model=schemas.RefillOut)
def get_refill(
    rx_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cache_key = f"refills:id:{rx_id}"
    cached = cache.cache_get(cache_key)
    if cached is not None:
        return cached

    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber),
    ).filter(Refill.id == rx_id).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")
    cache.cache_set(
        cache_key,
        _refill_ta.validate_python(rx, from_attributes=True).model_dump(mode="json"),
        _REFILL_CACHE_TTL,
    )
    return rx


# ---------------------------------------------------------------------------
# advance_refill helpers
# ---------------------------------------------------------------------------

def _resolve_next_state(current_state: RxState, payload: schemas.AdvanceRequest) -> RxState:
    """Return the target state for this advance request, or raise 400."""
    valid_next = TRANSITIONS[current_state]

    if payload.action == "reject":
        if RxState.REJECTED not in valid_next:
            raise HTTPException(status_code=400, detail="Cannot reject from this state")
        return RxState.REJECTED

    if payload.action == "hold":
        if RxState.HOLD not in valid_next:
            raise HTTPException(status_code=400, detail="Cannot hold from this state")
        return RxState.HOLD

    # Default: advance to the first forward state in the transition list.
    return valid_next[0]


def _assign_bin(db: Session) -> int:
    """Pick a bin using weighted random selection that favours less-loaded bins.

    The bin range (1–N) is read from system_config.bin_count (default 100, range 60–300).
    Bins with fewer current READY refills receive proportionally higher weight, so
    load is spread across the shelf while still retaining randomness (not always
    picking the single emptiest bin).
    """
    cfg = db.query(SystemConfig).filter(SystemConfig.id == 1).first()
    bin_count = cfg.bin_count if cfg is not None else 100

    rows = (
        db.query(Refill.bin_number, func.count(Refill.id).label("cnt"))
        .filter(Refill.state == RxState.READY, Refill.bin_number.isnot(None))
        .group_by(Refill.bin_number)
        .all()
    )
    counts: dict[int, int] = {int(row.bin_number): row.cnt for row in rows}

    bins = list(range(1, bin_count + 1))
    max_count = max(counts.values(), default=0)
    # Weight = (max_count − occupancy + 1) so empty bins score max_count+1 and the
    # fullest bin scores 1 (never zero, so it can still be picked occasionally).
    weights = [max_count - counts.get(b, 0) + 1 for b in bins]

    return random.choices(bins, weights=weights, k=1)[0]


def _apply_state_entry_effects(
    db: Session,
    rx: Refill,
    new_state: RxState,
    payload: schemas.AdvanceRequest,
) -> None:
    """Mutate rx fields that are set as a side-effect of entering a given state."""
    if new_state == RxState.REJECTED:
        rx.rejected_by = payload.rejected_by or "Unknown"              # type: ignore[assignment]
        rx.rejection_reason = payload.rejection_reason or "No reason provided"  # type: ignore[assignment]
        rx.rejection_date = date_type.today()                          # type: ignore[assignment]
    elif new_state == RxState.READY:
        rx.completed_date = date_type.today()                          # type: ignore[assignment]
        rx.bin_number = _assign_bin(db)                                # type: ignore[assignment]


def _adjust_prescription_quantity(
    db: Session,
    rx: Refill,
    current_state: RxState,
    new_state: RxState,
    rx_quantity: int,
) -> None:
    """Reserve or release prescription quantity when a fill crosses the active/inactive boundary.

    SOLD is excluded: quantity was already reserved when the fill entered the active chain and
    is consumed (not returned) on sale.
    """
    was_active = current_state in ACTIVE_STATES
    will_be_active = new_state in ACTIVE_STATES

    if was_active == will_be_active or new_state == RxState.SOLD:
        return

    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == rx.prescription_id)
        .with_for_update()
        .first()
    )
    if not prescription:
        return

    remaining = _int(prescription.remaining_quantity)

    if not was_active and will_be_active:
        # Resuming from HOLD/SCHEDULED → re-reserve quantity.
        if remaining < rx_quantity:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Insufficient remaining quantity on prescription to resume this fill "
                    f"(remaining={remaining}, needed={rx_quantity})"
                ),
            )
        prescription.remaining_quantity = max(0, remaining - rx_quantity)  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{remaining} → {prescription.remaining_quantity} (resumed fill, state={new_state.value})"
        )
    else:
        # Moving from active → HOLD/REJECTED → release quantity back.
        prescription.remaining_quantity = remaining + rx_quantity  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{remaining} → {prescription.remaining_quantity} (fill paused/cancelled, state={new_state.value})"
        )


def _archive_to_sold(
    db: Session,
    rx: Refill,
    rx_quantity: int,
    rx_days_supply: int,
    schedule_next_fill: bool,
) -> None:
    """Write RefillHist and optionally create the next SCHEDULED fill."""
    hist = RefillHist(
        prescription_id=rx.prescription_id,
        patient_id=rx.patient_id,
        drug_id=rx.drug_id,
        quantity=rx_quantity,
        days_supply=rx_days_supply,
        completed_date=rx.completed_date or date_type.today(),
        sold_date=date_type.today(),
        total_cost=Decimal(str(rx.total_cost)),
        insurance_id=rx.insurance_id,
        copay_amount=Decimal(str(rx.copay_amount)) if rx.copay_amount is not None else None,
        insurance_paid=Decimal(str(rx.insurance_paid)) if rx.insurance_paid is not None else None,
    )
    db.add(hist)
    logger.info(f"[RX HIST] Refill #{rx.id}: archived to RefillHist (qty={rx_quantity}, drug_id={rx.drug_id})")

    if schedule_next_fill:
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


@router.post("/{rx_id}/advance", response_model=schemas.RefillOut)
def advance_refill(
    rx_id: int,
    payload: schemas.AdvanceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rx = (
        db.query(Refill)
        .options(
            selectinload(Refill.patient),
            selectinload(Refill.drug),
            selectinload(Refill.prescription).selectinload(Prescription.prescriber),
        )
        .filter(Refill.id == rx_id)
        .with_for_update(of=Refill)
        .first()
    )
    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")

    raw_state = rx.state
    current_state = raw_state if isinstance(raw_state, RxState) else RxState(str(raw_state))

    if current_state not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")

    new_state = _resolve_next_state(current_state, payload)

    # Pharmacist-only steps: QV1 and QV2 may only be advanced by an RPh or admin.
    if current_state in PHARMACIST_REQUIRED_STATES:
        user_role = getattr(current_user, "role", None) or ""
        if user_role not in ("pharmacist", "admin"):
            raise HTTPException(
                status_code=403,
                detail=f"Pharmacist verification required to advance from {current_state.value}",
            )

    _apply_state_entry_effects(db, rx, new_state, payload)

    rx_quantity = _int(rx.quantity)
    rx_days_supply = _int(rx.days_supply)

    _adjust_prescription_quantity(db, rx, current_state, new_state, rx_quantity)

    rx.state = new_state  # type: ignore[assignment]

    if new_state == RxState.SOLD:
        _archive_to_sold(db, rx, rx_quantity, rx_days_supply, bool(payload.schedule_next_fill))

    logger.info(
        f"[RX STATE] Refill #{rx_id} (Rx #{rx.prescription_id}, pt:{_mask_patient_id(_int(rx.patient_id))}): "
        f"{current_state.value} → {new_state.value}"
    )
    _write_audit(
        db, "STATE_TRANSITION",
        entity_type="refill", entity_id=rx_id,
        prescription_id=rx.prescription_id,
        details=(
            f"{current_state.value} → {new_state.value} "
            f"prescription_id={rx.prescription_id} patient_id={rx.patient_id}"
            + (f" rejected_by={rx.rejected_by}" if new_state == RxState.REJECTED else "")
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    cache.cache_delete(f"refills:id:{rx_id}")
    _invalidate_queue_for_states({current_state.value, new_state.value})
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

    rx = (
        db.query(Refill)
        .options(
            selectinload(Refill.patient),
            selectinload(Refill.drug),
            selectinload(Refill.prescription).selectinload(Prescription.prescriber),
        )
        .filter(Refill.id == rx_id)
        .with_for_update(of=Refill)
        .first()
    )

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
        if payload.daw_code is not None:
            prescription.daw_code = payload.daw_code  # type: ignore[assignment]

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
    cache.cache_delete(f"refills:id:{rx_id}")
    _invalidate_queue_for_states({old_state_str, new_state.value})
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
        daw_code=data.daw_code,
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
    _invalidate_queue_for_states({"QT"})
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
    date_received = data.date_received or date_type.today()
    expiration = data.expiration_date or (date_received + timedelta(days=365))

    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=data.quantity * data.total_refills,
        remaining_quantity=data.quantity * data.total_refills,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=date_received,
        expiration_date=expiration,
        daw_code=data.daw_code,
        instructions=data.instructions,
    )
    db.add(prescription)
    db.flush()

    state_map = {"QP": RxState.QP, "SCHEDULED": RxState.SCHEDULED, "HOLD": RxState.HOLD}
    initial_state = state_map[data.initial_state]

    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=(data.due_date.date() if hasattr(data.due_date, "date") else data.due_date) or date_type.today(),
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
    _invalidate_queue_for_states({initial_state.value})
    db.refresh(refill)
    return {"message": "Prescription created successfully", "RX#": prescription.id, "state": str(initial_state)}
