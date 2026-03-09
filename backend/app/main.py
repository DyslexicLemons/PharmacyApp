from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload, noload
from typing import List, Optional
from datetime import datetime, timedelta, date as date_type, timezone
from .schemas import RefillOut, PrescriptionOut, PrescriberOut
from sqlalchemy import desc, and_
from .database import Base, engine, get_db
from .models import (
    Patient, Prescription, RxState, Drug, Prescriber, Priority,
    Refill, Stock, RefillHist, InsuranceCompany, Formulary, PatientInsurance, AuditLog
)
from . import schemas
from decimal import Decimal
import random
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pharmacy.rx")


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Pharmacy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"]
)

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

# States where a fill is actively in-flight (quantity is reserved)
ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

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
# Helpers
# ---------------------------------------------------------------------------

def _parse_priority(priority_str: str) -> Priority:
    """Convert a validated priority string to Priority enum. Raises 400 on bad value."""
    try:
        return Priority[priority_str.lower()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority '{priority_str}'. Must be one of: low, normal, high, stat"
        )


def _write_audit(
    db: Session,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
) -> None:
    """Append a row to the audit_log table inside the current transaction (no commit)."""
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)


def _int(val) -> int:  # type: ignore[no-untyped-def]
    """Safely coerce a possibly-Column SQLAlchemy value to a plain Python int."""
    return int(val) if val is not None else 0


# ---------------------------------------------------------------------------
# Root / health
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"message": "Pharmacy API running. Visit /docs for Swagger UI."}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Prescriptions
# ---------------------------------------------------------------------------

@app.get("/prescriptions", response_model=List[PrescriptionOut])
def get_prescriptions(db: Session = Depends(get_db)):
    return db.query(Prescription).all()


@app.get("/prescriptions/{prescription_id}", response_model=schemas.PrescriptionDetailOut)
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    prescription.latest_refill = get_latest_refill_for_prescription(db, prescription_id)  # type: ignore[attr-defined]
    prescription.refill_history = sorted(  # type: ignore[assignment]
        prescription.refill_history,
        key=lambda r: r.sold_date or r.completed_date or date_type.min,
        reverse=True,
    )
    return prescription


@app.post("/prescriptions", response_model=schemas.PrescriptionOut)
def create_prescription(p: schemas.PrescriptionCreate, db: Session = Depends(get_db)):
    patient = db.get(Patient, p.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    prescriber = db.query(Prescriber).filter(Prescriber.npi == p.npi).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Unable to find prescriber")

    prescription = Prescription(
        drug_id=p.drug_id,
        original_quantity=p.refill_quantity * p.total_refills,
        remaining_quantity=p.refill_quantity * p.total_refills,
        patient_id=p.patient_id,
        prescriber_id=prescriber.id,
        date_received=p.date,
        instructions=p.directions,   # PrescriptionCreate uses "directions"; model column is "instructions"
        brand_required=bool(p.brand_required)
    )

    db.add(prescription)
    db.flush()
    _write_audit(
        db, "PRESCRIPTION_CREATED",
        entity_type="prescription", entity_id=_int(prescription.id),
        details=f"patient_id={p.patient_id} drug_id={p.drug_id} qty={p.refill_quantity}×{p.total_refills}"
    )
    db.commit()
    db.refresh(prescription)
    return prescription


# ---------------------------------------------------------------------------
# Refills
# ---------------------------------------------------------------------------

@app.post("/prescriptions/{prescription_id}/fill")
def fill_prescription(
    prescription_id: int,
    data: schemas.FillScriptRequest,
    db: Session = Depends(get_db)
):
    """
    Create a new refill for an existing prescription.
    Uses SELECT FOR UPDATE to prevent concurrent double-fills.
    """
    # Lock the prescription row for the duration of this transaction.
    # FOR UPDATE cannot be used with LEFT OUTER JOIN (joinedload), so lock first,
    # then let SQLAlchemy lazy-load the drug relationship as needed.
    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == prescription_id)
        .with_for_update()
        .first()
    )

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Block if a fill is already actively in-progress
    BLOCKING_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}
    existing = db.query(Refill).filter(
        Refill.prescription_id == prescription_id,
        Refill.state.in_(BLOCKING_STATES)
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Prescription already has an active fill in state {existing.state.value}"
        )

    # Guard: prescription must have remaining quantity
    remaining_qty = _int(prescription.remaining_quantity)
    if remaining_qty <= 0:
        raise HTTPException(
            status_code=409,
            detail="No remaining authorized quantity on this prescription"
        )

    # Guard: requested quantity must not exceed what remains
    if data.quantity > remaining_qty:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Requested quantity ({data.quantity}) exceeds remaining authorized "
                f"quantity ({remaining_qty})"
            )
        )

    cash_price = Decimal(str(prescription.drug.cost)) * data.quantity

    # Billing: calculate copay if insurance provided
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance_id: Optional[int] = None

    if data.scheduled:
        initial_state = RxState.SCHEDULED
    else:
        initial_state = RxState.QV1  # default

    if data.insurance_id:
        patient_ins = db.query(PatientInsurance).filter(
            PatientInsurance.id == data.insurance_id,
            PatientInsurance.patient_id == prescription.patient_id
        ).first()
        if patient_ins:
            formulary_entry = db.query(Formulary).filter(
                Formulary.insurance_company_id == patient_ins.insurance_company_id,
                Formulary.drug_id == prescription.drug_id
            ).first()
            if not data.scheduled:
                not_covered = bool(formulary_entry.not_covered) if formulary_entry else True
                if not formulary_entry or not_covered:
                    initial_state = RxState.QT
            if formulary_entry and not bool(formulary_entry.not_covered):
                raw_copay = Decimal(str(formulary_entry.copay_per_30)) * data.days_supply / Decimal("30")
                copay_amount = min(raw_copay, cash_price)
                insurance_paid = cash_price - copay_amount
            insurance_id = _int(patient_ins.id)

    # If no insurance issue, check if this fill matches the last fill → skip to QP
    if initial_state == RxState.QV1:
        matching_hist = db.query(RefillHist).filter(
            RefillHist.prescription_id == prescription_id,
            RefillHist.quantity == data.quantity,
            RefillHist.days_supply == data.days_supply,
            RefillHist.insurance_id == data.insurance_id,
        ).order_by(desc(RefillHist.completed_date)).first()
        if matching_hist:
            initial_state = RxState.QP

    priority = _parse_priority(data.priority)

    refill = Refill(
        prescription_id=prescription_id,
        patient_id=prescription.patient_id,
        drug_id=prescription.drug_id,
        due_date=data.due_date or date_type.today(),
        quantity=data.quantity,
        days_supply=data.days_supply,
        total_cost=cash_price,
        priority=priority,
        state=initial_state,
        source="manual",
        insurance_id=insurance_id,
        copay_amount=copay_amount,
        insurance_paid=insurance_paid,
    )

    db.add(refill)

    # Decrement remaining quantity when entering an active fill state
    if initial_state in ACTIVE_STATES:
        old_qty = remaining_qty
        prescription.remaining_quantity = max(0, old_qty - data.quantity)  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{old_qty} → {prescription.remaining_quantity} (fill started, state={initial_state.value})"
        )

    db.flush()  # obtain refill.id for the audit log
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        details=(
            f"prescription_id={prescription_id} state={initial_state.value} "
            f"qty={data.quantity} days={data.days_supply} priority={priority.value}"
        )
    )
    db.commit()
    db.refresh(refill)

    response: dict = {
        "message": "Fill created successfully",
        "refill_id": refill.id,
        "state": str(initial_state)
    }
    if copay_amount is not None:
        response["cash_price"] = float(cash_price)
        response["copay_amount"] = float(copay_amount)
        response["insurance_paid"] = float(insurance_paid or 0)
    return response


@app.get("/refills", response_model=List[RefillOut])
def get_refills(state: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Refill)
    if state and state != "ALL":
        try:
            state_enum = RxState(state)
            query = query.filter(Refill.state == state_enum)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
    return query.all()


@app.get("/refills/check_conflict", response_model=schemas.ConflictCheckResponse)
def check_refill_conflict_early(patient_id: int, drug_id: int, db: Session = Depends(get_db)):
    """
    Check for duplicate or conflicting refills before creating a new prescription.
    NOTE: This route must be declared BEFORE /refills/{rx_id} so FastAPI doesn't
    try to coerce the literal string 'check_conflict' into an integer rx_id.
    """
    from sqlalchemy import and_
    active_refills = db.query(Refill).filter(
        and_(
            Refill.patient_id == patient_id,
            Refill.drug_id == drug_id,
            Refill.state != RxState.SOLD
        )
    ).all()

    ninety_days_ago = date_type.today() - timedelta(days=90)
    recent_fills = db.query(RefillHist).filter(
        and_(
            RefillHist.patient_id == patient_id,
            RefillHist.drug_id == drug_id,
            RefillHist.sold_date >= ninety_days_ago
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
        message=message
    )


@app.get("/refills/{rx_id}", response_model=RefillOut)
def get_refill(rx_id: int, db: Session = Depends(get_db)):
    """Fetch a single refill by ID (used by RefillDetailView)."""
    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber)
    ).filter(Refill.id == rx_id).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")
    return rx


@app.post("/refills/{rx_id}/advance", response_model=schemas.RefillOut)
def advance_refill(rx_id: int, payload: schemas.AdvanceRequest, db: Session = Depends(get_db)):
    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber)
    ).filter(Refill.id == rx_id).first()

    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")

    # Force-convert to RxState enum regardless of whether ORM returns str or enum.
    # Use .value when available (Python 3.11+ changed str() for str-subclass enums
    # to return "ClassName.member" instead of the value, breaking RxState(str(...))).
    raw_state = rx.state
    current_state_enum = raw_state if isinstance(raw_state, RxState) else RxState(str(raw_state))

    if current_state_enum not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")

    valid_next_states = TRANSITIONS[current_state_enum]
    new_state = current_state_enum

    if payload.action == "reject":
        if RxState.REJECTED in valid_next_states:
            new_state = RxState.REJECTED
            rx.rejected_by = payload.rejected_by or "Unknown"           # type: ignore[assignment]
            rx.rejection_reason = payload.rejection_reason or "No reason provided"  # type: ignore[assignment]
            rx.rejection_date = date_type.today()                        # type: ignore[assignment]
        else:
            raise HTTPException(status_code=400, detail="Cannot reject from this state")

    elif payload.action == "hold":
        if RxState.HOLD in valid_next_states:
            new_state = RxState.HOLD
        else:
            raise HTTPException(status_code=400, detail="Cannot hold from this state")

    else:
        # Default advance
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

    # Extract plain ints from Column values once to use safely throughout
    rx_quantity = _int(rx.quantity)
    rx_days_supply = _int(rx.days_supply)

    # Adjust remaining_quantity based on state transition direction
    if current_state_enum not in ACTIVE_STATES and new_state in ACTIVE_STATES:
        # Resuming from HOLD or SCHEDULED → decrement quantity
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
                    )
                )
            prescription.remaining_quantity = max(0, rx_remaining - rx_quantity)  # type: ignore[assignment]
            logger.info(
                f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
                f"{rx_remaining} → {prescription.remaining_quantity} (resumed fill, state={new_state.value})"
            )

    elif current_state_enum in ACTIVE_STATES and new_state not in ACTIVE_STATES and new_state != RxState.SOLD:
        # Going to HOLD or REJECTED from active state → return quantity
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

    # When selling: archive to RefillHist
    if new_state == RxState.SOLD:
        rx_completed: Optional[date_type] = rx.completed_date  # type: ignore[assignment]
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
        logger.info(
            f"[RX HIST] Refill #{rx_id}: archived to RefillHist "
            f"(qty={rx_quantity}, drug_id={rx.drug_id})"
        )

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
            logger.info(
                f"[RX SCHED] Prescription #{rx.prescription_id}: next fill scheduled for {next_due}"
            )

    _write_audit(
        db, "STATE_TRANSITION",
        entity_type="refill", entity_id=rx_id,
        details=(
            f"{current_state_enum.value} → {new_state.value} "
            f"prescription_id={rx.prescription_id} patient_id={rx.patient_id}"
            + (f" rejected_by={rx.rejected_by}" if new_state == RxState.REJECTED else "")
        )
    )
    db.commit()
    db.refresh(rx)

    return rx


@app.post("/refills/upload_json")
def upload_json_prescription(data: schemas.JSONPrescriptionUpload, db: Session = Depends(get_db)):
    """Upload external JSON prescription — goes to QT queue for triage."""

    # Validate required keys exist in the untyped dicts
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
            Patient.dob == data.patient.get("dob")
        )
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found — must exist in system")

    prescriber = db.query(Prescriber).filter(Prescriber.npi == data.prescriber["npi"]).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found — must exist in system")

    drug = db.query(Drug).filter(
        and_(
            Drug.drug_name.ilike(data.drug["name"]),
            Drug.manufacturer.ilike(data.drug["manufacturer"])
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
        brand_required=data.brand_required
    )
    db.add(prescription)
    db.flush()

    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=data.date,
        quantity=data.refill_quantity,
        days_supply=30,  # default; caller should include days_supply in JSON if known
        total_cost=Decimal(str(drug.cost)) * data.refill_quantity,
        priority=priority,
        state=RxState.QT,
        source="external"
    )
    db.add(refill)

    # QT is an active state — decrement remaining quantity
    old_qty = data.refill_quantity * data.total_refills
    prescription.remaining_quantity = max(0, old_qty - data.refill_quantity)  # type: ignore[assignment]
    logger.info(
        f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
        f"{old_qty} → {prescription.remaining_quantity} (fill started, state=QT)"
    )

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        details=f"source=external prescription_id={prescription.id} state=QT qty={data.refill_quantity}"
    )
    db.commit()
    db.refresh(refill)

    return {"message": "Prescription uploaded successfully", "refill_id": refill.id, "state": "QT"}


@app.post("/refills/create_manual")
def create_manual_prescription(data: schemas.ManualPrescriptionCreate, db: Session = Depends(get_db)):
    """Create manual prescription — goes to QP, HOLD, or SCHEDULED based on input."""
    patient = db.get(Patient, data.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    drug = db.get(Drug, data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    prescriber = db.get(Prescriber, data.prescriber_id)
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found")

    priority = _parse_priority(data.priority)

    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=data.quantity * data.total_refills,
        remaining_quantity=data.quantity * data.total_refills,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=date_type.today(),
        brand_required=data.brand_required,
        instructions=data.instructions
    )
    db.add(prescription)
    db.flush()

    # Determine initial state (validated by schema)
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
        source="manual"
    )
    db.add(refill)

    if initial_state in ACTIVE_STATES:
        old_qty = data.quantity * data.total_refills
        prescription.remaining_quantity = max(0, old_qty - data.quantity)  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{old_qty} → {prescription.remaining_quantity} (fill started, state={initial_state.value})"
        )

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        details=(
            f"source=manual prescription_id={prescription.id} state={initial_state.value} "
            f"qty={data.quantity} days={data.days_supply}"
        )
    )
    db.commit()
    db.refresh(refill)

    return {
        "message": "Prescription created successfully",
        "refill_id": refill.id,
        "state": str(initial_state)
    }


@app.get("/refills/check_conflict", response_model=schemas.ConflictCheckResponse)
def check_refill_conflict(patient_id: int, drug_id: int, db: Session = Depends(get_db)):
    """Check for duplicate or conflicting refills before creating a new prescription."""
    active_refills = db.query(Refill).filter(
        and_(
            Refill.patient_id == patient_id,
            Refill.drug_id == drug_id,
            Refill.state != RxState.SOLD
        )
    ).all()

    ninety_days_ago = date_type.today() - timedelta(days=90)
    recent_fills = db.query(RefillHist).filter(
        and_(
            RefillHist.patient_id == patient_id,
            RefillHist.drug_id == drug_id,
            RefillHist.sold_date >= ninety_days_ago
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
        message=message
    )


@app.get("/refill_hist", response_model=List[schemas.RefillHistOut])
def get_refill_hist(db: Session = Depends(get_db)):
    return db.query(RefillHist).all()


# ---------------------------------------------------------------------------
# Patients
# ---------------------------------------------------------------------------

@app.get("/patients", response_model=List[schemas.PatientOut])
def get_patients(db: Session = Depends(get_db)):
    return db.query(Patient).options(noload("*")).all()


@app.post("/patients", response_model=schemas.PatientOut)
def create_patient(p: schemas.PatientCreate, db: Session = Depends(get_db)):
    patient = Patient(
        first_name=p.first_name,
        last_name=p.last_name,
        dob=p.dob,
        address=p.address,
        city=p.city,
        state=p.state,
    )
    db.add(patient)
    db.flush()
    _write_audit(
        db, "PATIENT_CREATED",
        entity_type="patient", entity_id=_int(patient.id),
        details=f"{p.last_name}, {p.first_name} DOB={p.dob}"
    )
    db.commit()
    db.refresh(patient)
    return patient


@app.patch("/patients/{pid}", response_model=schemas.PatientOut)
def update_patient(pid: int, p: schemas.PatientCreate, db: Session = Depends(get_db)):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    patient.first_name = p.first_name  # type: ignore[assignment]
    patient.last_name = p.last_name    # type: ignore[assignment]
    patient.dob = p.dob                # type: ignore[assignment]
    patient.address = p.address        # type: ignore[assignment]
    patient.city = p.city              # type: ignore[assignment]
    patient.state = p.state            # type: ignore[assignment]
    db.commit()
    db.refresh(patient)
    return patient


@app.get("/patients/search", response_model=List[schemas.PatientOut])
def search_patient(name: str, db: Session = Depends(get_db)):
    """
    Search patients. name format: "lastname,firstname" (prefix match on each part).
    """
    if "," not in name:
        raise HTTPException(status_code=400, detail="Name must be 'lastname,firstname'")
    last, first = [s.strip() for s in name.split(",", 1)]
    q = db.query(Patient)
    if last:
        q = q.filter(Patient.last_name.ilike(f"{last}%"))
    if first:
        q = q.filter(Patient.first_name.ilike(f"{first}%"))
    return q.order_by(Patient.last_name.asc(), Patient.first_name.asc()).all()


def get_latest_refill_for_prescription(
    db: Session, prescription_id: int
) -> Optional[schemas.LatestRefillOut]:
    active_refill = (
        db.query(Refill)
        .filter(Refill.prescription_id == prescription_id, Refill.state != RxState.SOLD)
        .order_by(desc(Refill.id))
        .first()
    )
    latest_hist = (
        db.query(RefillHist)
        .filter(RefillHist.prescription_id == prescription_id)
        .order_by(desc(RefillHist.id))
        .first()
    )

    if not active_refill and not latest_hist:
        return None

    if active_refill:
        state_val = active_refill.state.value if hasattr(active_refill.state, "value") else str(active_refill.state)
        return schemas.LatestRefillOut(
            quantity=_int(active_refill.quantity),
            days_supply=_int(active_refill.days_supply),
            total_cost=Decimal(str(active_refill.total_cost or "0.00")),
            sold_date=None,
            completed_date=active_refill.completed_date,  # type: ignore[arg-type]
            state=state_val,
            next_pickup=None,
        )

    assert latest_hist is not None
    days_supply = _int(latest_hist.days_supply)
    sold_date: Optional[date_type] = latest_hist.sold_date  # type: ignore[assignment]
    next_pickup: Optional[date_type] = (
        sold_date + timedelta(days=days_supply) if sold_date and days_supply else None
    )
    return schemas.LatestRefillOut(
        quantity=_int(latest_hist.quantity),
        days_supply=days_supply,
        total_cost=Decimal(str(latest_hist.total_cost or "0.00")),
        sold_date=sold_date,
        completed_date=latest_hist.completed_date,  # type: ignore[arg-type]
        state=None,
        next_pickup=next_pickup,
    )


@app.get("/patients/{pid}", response_model=schemas.PatientWithRxs)
def get_patient(pid: int, db: Session = Depends(get_db)):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for prescription in patient.prescriptions:
        latest_refill = get_latest_refill_for_prescription(db, prescription.id)  # type: ignore[arg-type]
        if latest_refill:
            prescription.latest_refill = latest_refill  # type: ignore[attr-defined]
            if hasattr(latest_refill, "sold_date") and latest_refill.sold_date:
                prescription.next_pickup = latest_refill.sold_date + timedelta(latest_refill.days_supply)  # type: ignore[attr-defined]
            else:
                prescription.next_pickup = latest_refill.state  # type: ignore[attr-defined]

        prescription.refill_history = sorted(  # type: ignore[assignment]
            prescription.refill_history,
            key=lambda r: r.sold_date or r.completed_date or date_type.min,
            reverse=True
        )

    return patient


# ---------------------------------------------------------------------------
# Drugs & Stock
# ---------------------------------------------------------------------------

@app.get("/drugs", response_model=List[schemas.DrugOut])
def get_drugs(db: Session = Depends(get_db)):
    return db.query(Drug).all()


@app.get("/stock", response_model=List[schemas.StockOut])
def get_stock(db: Session = Depends(get_db)):
    return db.query(Stock).all()


# ---------------------------------------------------------------------------
# Prescribers
# ---------------------------------------------------------------------------

@app.get("/prescribers", response_model=List[schemas.PrescriberOut])
def get_prescribers(db: Session = Depends(get_db)):
    return db.query(Prescriber).all()


@app.get("/prescribers/{npi}", response_model=List[schemas.PrescriberOut])
def get_prescriber(npi: int, db: Session = Depends(get_db)):
    prescriber = db.get(Prescriber, npi)
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found")
    return prescriber


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------

@app.get("/insurance_companies", response_model=List[schemas.InsuranceCompanyOut])
def get_insurance_companies(db: Session = Depends(get_db)):
    return db.query(InsuranceCompany).all()


@app.get("/insurance_companies/{company_id}/formulary", response_model=List[schemas.FormularyOut])
def get_formulary(company_id: int, db: Session = Depends(get_db)):
    company = db.get(InsuranceCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")
    entries = db.query(Formulary).filter(Formulary.insurance_company_id == company_id).all()
    for e in entries:
        _ = e.drug
    return entries


@app.get("/patients/{pid}/insurance", response_model=List[schemas.PatientInsuranceOut])
def get_patient_insurance(pid: int, db: Session = Depends(get_db)):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.query(PatientInsurance).filter(PatientInsurance.patient_id == pid).all()


@app.post("/patients/{pid}/insurance", response_model=schemas.PatientInsuranceOut)
def add_patient_insurance(pid: int, data: schemas.PatientInsuranceCreate, db: Session = Depends(get_db)):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    company = db.get(InsuranceCompany, data.insurance_company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")

    existing = db.query(PatientInsurance).filter(
        PatientInsurance.patient_id == pid,
        PatientInsurance.insurance_company_id == data.insurance_company_id,
        PatientInsurance.is_active == True
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Patient already has an active plan with this insurance company"
        )

    if data.is_primary:
        db.query(PatientInsurance).filter(
            PatientInsurance.patient_id == pid,
            PatientInsurance.is_primary == True
        ).update({"is_primary": False})

    ins = PatientInsurance(
        patient_id=pid,
        insurance_company_id=data.insurance_company_id,
        member_id=data.member_id,
        group_number=data.group_number,
        is_primary=data.is_primary,
        is_active=True,
    )
    db.add(ins)
    db.flush()
    _write_audit(
        db, "INSURANCE_ADDED",
        entity_type="patient", entity_id=pid,
        details=f"plan={company.plan_name} member_id={data.member_id} primary={data.is_primary}"
    )
    db.commit()
    db.refresh(ins)
    _ = ins.insurance_company
    return ins


@app.post("/billing/calculate", response_model=schemas.BillingCalculateResponse)
def calculate_billing(data: schemas.BillingCalculateRequest, db: Session = Depends(get_db)):
    drug = db.get(Drug, data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    patient_ins = db.get(PatientInsurance, data.insurance_id)
    if not patient_ins:
        raise HTTPException(status_code=404, detail="Patient insurance not found")

    cash_price = Decimal(str(drug.cost)) * data.quantity

    formulary_entry = db.query(Formulary).filter(
        Formulary.insurance_company_id == patient_ins.insurance_company_id,
        Formulary.drug_id == data.drug_id
    ).first()

    plan_name: str = patient_ins.insurance_company.plan_name  # type: ignore[assignment]

    if not formulary_entry or bool(formulary_entry.not_covered):
        return schemas.BillingCalculateResponse(
            cash_price=cash_price,
            not_covered=True,
            plan_name=plan_name,
        )

    raw_copay = Decimal(str(formulary_entry.copay_per_30)) * data.days_supply / Decimal("30")
    copay_amount = min(raw_copay, cash_price)
    insurance_paid = cash_price - copay_amount

    return schemas.BillingCalculateResponse(
        cash_price=cash_price,
        insurance_price=copay_amount,
        insurance_paid=insurance_paid,
        tier=_int(formulary_entry.tier) or None,  # type: ignore[arg-type]
        not_covered=False,
        plan_name=plan_name,
    )


# ---------------------------------------------------------------------------
# Commands (dev/admin only — no auth; exclude from production deployments)
# ---------------------------------------------------------------------------

@app.post("/commands/generate_test_prescriptions")
def generate_test_prescriptions(db: Session = Depends(get_db)):
    """
    Generate 50 random test prescriptions.
    Removes ALL existing prescriptions and refills first.
    WARNING: destructive — for development use only.
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
            detail="Need patients, prescribers, and drugs in database first"
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
        brand_required = random.choice([True, False])

        days_ago = random.randint(0, 90)
        date_received = date_type.today() - timedelta(days=days_ago)

        prescription = Prescription(
            drug_id=drug.id,
            brand_required=brand_required,
            original_quantity=refill_quantity * total_refills,
            remaining_quantity=refill_quantity * total_refills,
            date_received=date_received,
            patient_id=patient.id,
            prescriber_id=prescriber.id,
            instructions=random.choice(instructions_pool)
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
                total_cost=total_cost
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
                source=random.choice(["manual", "external"])
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
                    "Incorrect dosage form"
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
        "sold_prescriptions": len(created_refill_hists)
    }
