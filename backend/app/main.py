from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload, noload
from typing import List, Optional
from datetime import datetime, timedelta, date as date_type
from .schemas import RefillOut, PrescriptionOut, PrescriberOut
from sqlalchemy import desc, and_
from .database import Base, engine, get_db
from .models import Patient, Prescription, RxState, Drug, Prescriber, Priority, Refill, Stock, RefillHist, InsuranceCompany, Formulary, PatientInsurance
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# States where a fill is actively being worked on (quantity is reserved)
ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

# Utility: state transition map
# Maps current state to valid next states
TRANSITIONS = {
    RxState.QT: [RxState.QV1, RxState.HOLD],  # Triage proceeds to first verify or hold
    RxState.QV1: [RxState.QP, RxState.HOLD, RxState.REJECTED],  # Approve, hold, or reject
    RxState.QP: [RxState.QV2, RxState.HOLD],  # Prep proceeds to final verify or hold
    RxState.QV2: [RxState.READY, RxState.QP, RxState.HOLD],  # Pass→READY, fail→back to prep, or hold
    RxState.HOLD: [RxState.QP, RxState.REJECTED],  # Resume or reject from hold
    RxState.SCHEDULED: [RxState.QP, RxState.HOLD, RxState.REJECTED],  # Activate, hold, or reject
    RxState.READY: [RxState.SOLD],  # Pickup
}

# Root route
@app.get("/")
def read_root():
    return {"message": "Pharmacy API running. Visit /docs for Swagger UI."}


# ----- Prescriptions -----
@app.get("/prescriptions", response_model=List[PrescriptionOut])
def get_prescriptions(db: Session = Depends(get_db)):
    return db.query(Prescription).all()


@app.get("/prescriptions/{prescription_id}", response_model=schemas.PrescriptionDetailOut)
def get_prescription(prescription_id: int, db: Session = Depends(get_db)):
    prescription = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    prescription.latest_refill = get_latest_refill_for_prescription(db, prescription_id)
    prescription.refill_history = sorted(
        prescription.refill_history,
        key=lambda r: r.sold_date or r.completed_date or date_type.min,
        reverse=True,
    )
    return prescription


@app.post("/prescriptions", response_model=schemas.PrescriptionOut)
def create_prescription(p: schemas.PrescriptionCreate, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == p.patient_id).first()
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
        directions=p.directions,
        brand_required=bool(p.brand_required)
    )

    db.add(prescription)
    db.commit()
    db.refresh(prescription)
    return prescription

# ----- Refills -----



@app.post("/prescriptions/{prescription_id}/fill")
def fill_prescription(prescription_id: int, data: schemas.FillScriptRequest, db: Session = Depends(get_db)):
    """
    Create a new refill for an existing prescription.
    Use for both new fills (near end of days supply) and scheduled refills (early fill queued for later).
    Optionally provide insurance_id (PatientInsurance.id) to calculate and store billing info.
    """
    prescription = db.query(Prescription).options(
        joinedload(Prescription.drug)
    ).filter(Prescription.id == prescription_id).first()

    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Block if there is already an active fill in progress
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

    cash_price = prescription.drug.cost * data.quantity

    # Billing: calculate copay if insurance provided
    copay_amount = None
    insurance_paid = None
    insurance_id = None

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
                if not formulary_entry or bool(formulary_entry.not_covered):
                    # Drug not on formulary → reject to triage
                    initial_state = RxState.QT
                # else stays QV1 (or may be overridden to QP below)
            if formulary_entry and not formulary_entry.not_covered:
                raw_copay = formulary_entry.copay_per_30 * Decimal(str(data.days_supply)) / Decimal("30")
                copay_amount = min(raw_copay, cash_price)
                insurance_paid = cash_price - copay_amount
            insurance_id = patient_ins.id

    # If no insurance issue, check if this fill matches the last fill exactly → skip to QP
    if initial_state == RxState.QV1:
        matching_hist = db.query(RefillHist).filter(
            RefillHist.prescription_id == prescription_id,
            RefillHist.quantity == data.quantity,
            RefillHist.days_supply == data.days_supply,
            RefillHist.insurance_id == data.insurance_id,
        ).order_by(desc(RefillHist.completed_date)).first()
        if matching_hist:
            initial_state = RxState.QP

    refill = Refill(
        prescription_id=prescription_id,
        patient_id=prescription.patient_id,
        drug_id=prescription.drug_id,
        due_date=data.due_date or date_type.today(),
        quantity=data.quantity,
        days_supply=data.days_supply,
        total_cost=cash_price,
        priority=Priority[data.priority],
        state=initial_state,
        source="manual",
        insurance_id=insurance_id,
        copay_amount=copay_amount,
        insurance_paid=insurance_paid,
    )

    db.add(refill)

    # Decrement remaining quantity immediately when entering an active fill state
    if initial_state in ACTIVE_STATES:
        old_qty = prescription.remaining_quantity or 0
        prescription.remaining_quantity = max(0, old_qty - (data.quantity or 0))  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{old_qty} → {prescription.remaining_quantity} (fill started, state={initial_state.value})"
        )

    db.commit()
    db.refresh(refill)

    response = {"message": "Fill created successfully", "refill_id": refill.id, "state": str(initial_state)}
    if copay_amount is not None:
        response["cash_price"] = float(cash_price)
        response["copay_amount"] = float(copay_amount)
        response["insurance_paid"] = float(insurance_paid)
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
    refills = query.all()

    # Ensure relationships are loaded (optional with selectinload)
    for r in refills:
        _ = r.patient
        _ = r.drug
        _ = r.prescription.prescriber

    return refills

@app.post("/refills/{rx_id}/advance", response_model=schemas.RefillOut)
def advance_refill(rx_id: int, payload: schemas.AdvanceRequest, db: Session = Depends(get_db)):
    rx = db.query(Refill).options(
        joinedload(Refill.patient),
        joinedload(Refill.drug),
        joinedload(Refill.prescription).joinedload(Prescription.prescriber)
    ).filter(Refill.id == rx_id).first()

    if not rx:
        raise HTTPException(status_code=404, detail="Refill not found")

    # Get current state as RxState enum (handle both string and enum)
    if isinstance(rx.state, str):
        current_state_enum = RxState(rx.state)
    else:
        current_state_enum = rx.state  # type: ignore

    if current_state_enum not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")

    valid_next_states = TRANSITIONS[current_state_enum]  # type: ignore
    new_state = current_state_enum

    if payload.action == "reject":
        if RxState.REJECTED in valid_next_states:
            new_state = RxState.REJECTED
            rx.rejected_by = payload.rejected_by or "Unknown"
            rx.rejection_reason = payload.rejection_reason or "No reason provided"
            rx.rejection_date = date_type.today()
        else:
            raise HTTPException(status_code=400, detail="Cannot reject from this state")

    elif payload.action == "hold":
        if RxState.HOLD in valid_next_states:
            new_state = RxState.HOLD
        else:
            raise HTTPException(status_code=400, detail="Cannot hold from this state")

    else:
        # Default advance action
        if current_state_enum == RxState.QV1:  # type: ignore
            new_state = RxState.QP
        elif current_state_enum == RxState.QV2:  # type: ignore
            new_state = RxState.READY
            rx.bin_number = random.randint(1, 100)
        else:
            new_state = valid_next_states[0]

    # Set completed_date when reaching READY (drug has been filled/prepared)
    if new_state == RxState.READY:
        rx.completed_date = date_type.today()  # type: ignore[assignment]

    # Log the state transition
    logger.info(
        f"[RX STATE] Refill #{rx_id} (Rx #{rx.prescription_id}, patient #{rx.patient_id}): "
        f"{current_state_enum.value} → {new_state.value}"
    )

    # Adjust remaining_quantity based on workflow transitions
    # Decrement when entering active fill workflow; re-increment when leaving it (hold/rejected)
    if current_state_enum not in ACTIVE_STATES and new_state in ACTIVE_STATES:
        # Resuming from HOLD or SCHEDULED → entering active workflow
        prescription = db.query(Prescription).filter(Prescription.id == rx.prescription_id).first()
        if prescription:
            old_qty = prescription.remaining_quantity or 0
            prescription.remaining_quantity = max(0, old_qty - (rx.quantity or 0))  # type: ignore[assignment]
            logger.info(
                f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
                f"{old_qty} → {prescription.remaining_quantity} (resumed fill, state={new_state.value})"
            )
    elif current_state_enum in ACTIVE_STATES and new_state not in ACTIVE_STATES and new_state != RxState.SOLD:
        # Going to HOLD or REJECTED from active state → return quantity
        prescription = db.query(Prescription).filter(Prescription.id == rx.prescription_id).first()
        if prescription:
            old_qty = prescription.remaining_quantity or 0
            prescription.remaining_quantity = old_qty + (rx.quantity or 0)  # type: ignore[assignment]
            logger.info(
                f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
                f"{old_qty} → {prescription.remaining_quantity} (fill paused/cancelled, state={new_state.value})"
            )

    # Assign the new state (use .value or the enum directly depending on your Column definition)
    rx.state = new_state  # type: ignore

    # When selling: archive to RefillHist (quantity was already decremented at fill start)
    if new_state == RxState.SOLD:
        hist = RefillHist(
            prescription_id=rx.prescription_id,
            patient_id=rx.patient_id,
            drug_id=rx.drug_id,
            quantity=rx.quantity,
            days_supply=rx.days_supply,
            completed_date=rx.completed_date or date_type.today(),
            sold_date=date_type.today(),
            total_cost=rx.total_cost,
            insurance_id=rx.insurance_id,
            copay_amount=rx.copay_amount,
            insurance_paid=rx.insurance_paid,
        )
        db.add(hist)
        logger.info(
            f"[RX HIST] Refill #{rx_id}: archived to RefillHist "
            f"(qty={rx.quantity}, drug_id={rx.drug_id})"
        )

        if payload.schedule_next_fill:
            next_due = date_type.today() + timedelta(days=rx.days_supply)  # type: ignore[arg-type]
            scheduled = Refill(
                prescription_id=rx.prescription_id,
                patient_id=rx.patient_id,
                drug_id=rx.drug_id,
                due_date=next_due,
                quantity=rx.quantity,
                days_supply=rx.days_supply,
                total_cost=rx.total_cost,
                priority=rx.priority,
                state=RxState.SCHEDULED,
                source="auto_schedule",
                insurance_id=rx.insurance_id,
                copay_amount=rx.copay_amount,
                insurance_paid=rx.insurance_paid,
            )
            db.add(scheduled)
            logger.info(
                f"[RX SCHED] Prescription #{rx.prescription_id}: next fill scheduled for {next_due}"
            )

    db.commit()
    db.refresh(rx)

    # Ensure relationships are loaded for response
    _ = rx.patient
    _ = rx.drug
    _ = rx.prescription.prescriber

    return rx


@app.post("/refills/upload_json")
def upload_json_prescription(data: schemas.JSONPrescriptionUpload, db: Session = Depends(get_db)):
    """
    Upload external JSON prescription - goes to QT queue for triage
    """
    # Find or validate patient
    patient = db.query(Patient).filter(
        and_(
            Patient.first_name.ilike(data.patient["first_name"]),
            Patient.last_name.ilike(data.patient["last_name"]),
            Patient.dob == data.patient.get("dob")
        )
    ).first()

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found - must exist in system")

    # Find or validate prescriber
    prescriber = db.query(Prescriber).filter(Prescriber.npi == data.prescriber["npi"]).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found - must exist in system")

    # Find drug by name and manufacturer
    drug = db.query(Drug).filter(
        and_(
            Drug.drug_name.ilike(data.drug["name"]),
            Drug.manufacturer.ilike(data.drug["manufacturer"])
        )
    ).first()

    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found - must exist in system")

    # Create prescription
    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=data.refill_quantity * data.total_refills,
        remaining_quantity=data.refill_quantity * data.total_refills,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=data.date,
        brand_required=data.brand_required
    )

    db.add(prescription)
    db.flush()  # Get prescription.id without committing

    # Create refill in QT state with external source
    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=data.date,  # Can be adjusted based on business logic
        quantity=data.refill_quantity,
        days_supply=30,  # Default, should come from JSON if available
        total_cost=drug.cost * data.refill_quantity,
        priority=Priority[data.priority],
        state=RxState.QT,  # External prescriptions start at QT
        source="external"
    )

    db.add(refill)

    # QT is an active state — decrement remaining quantity immediately
    old_qty = prescription.remaining_quantity or 0
    prescription.remaining_quantity = max(0, old_qty - data.refill_quantity)  # type: ignore[assignment]
    logger.info(
        f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
        f"{old_qty} → {prescription.remaining_quantity} (fill started, state=QT)"
    )

    db.commit()
    db.refresh(refill)

    return {"message": "Prescription uploaded successfully", "refill_id": refill.id, "state": "QT"}


@app.post("/refills/create_manual")
def create_manual_prescription(data: schemas.ManualPrescriptionCreate, db: Session = Depends(get_db)):
    """
    Create manual prescription - goes to QP or HOLD based on input
    """
    # Validate patient, drug, prescriber exist
    patient = db.query(Patient).filter(Patient.id == data.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    drug = db.query(Drug).filter(Drug.id == data.drug_id).first()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    prescriber = db.query(Prescriber).filter(Prescriber.id == data.prescriber_id).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found")

    # Create prescription
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

    # Determine initial state
    if data.initial_state == "QP":
        initial_state = RxState.QP
    elif data.initial_state == "SCHEDULED":
        initial_state = RxState.SCHEDULED
    else:
        initial_state = RxState.HOLD

    # Create refill with manual source
    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=data.due_date or date_type.today(),
        quantity=data.quantity,
        days_supply=data.days_supply,
        total_cost=drug.cost * data.quantity,
        priority=Priority[data.priority],
        state=initial_state,
        source="manual"
    )

    db.add(refill)

    # Decrement remaining quantity immediately when entering an active fill state
    if initial_state in ACTIVE_STATES:
        old_qty = prescription.remaining_quantity or 0
        prescription.remaining_quantity = max(0, old_qty - (data.quantity or 0))  # type: ignore[assignment]
        logger.info(
            f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
            f"{old_qty} → {prescription.remaining_quantity} (fill started, state={initial_state.value})"
        )

    db.commit()
    db.refresh(refill)

    return {"message": "Prescription created successfully", "refill_id": refill.id, "state": str(initial_state)}


@app.get("/refills/check_conflict", response_model=schemas.ConflictCheckResponse)
def check_refill_conflict(patient_id: int, drug_id: int, db: Session = Depends(get_db)):
    """
    Check for duplicate or conflicting refills before creating new prescription
    """
    # Check for active refills (not SOLD)
    active_refills = db.query(Refill).filter(
        and_(
            Refill.patient_id == patient_id,
            Refill.drug_id == drug_id,
            Refill.state != RxState.SOLD
        )
    ).all()

    # Check recent sold refills (last 90 days)
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
        {
            "id": r.id,
            "state": str(r.state),
            "due_date": str(r.due_date),
            "quantity": r.quantity
        }
        for r in active_refills
    ]

    recent_data = [
        {
            "id": r.id,
            "sold_date": str(r.sold_date),
            "days_supply": r.days_supply,
            "quantity": r.quantity
        }
        for r in recent_fills
    ]

    message = None
    if has_conflict:
        message = f"Patient already has {len(active_refills)} active refill(s) for this drug"
    elif recent_fills:
        latest = recent_fills[0]
        days = latest.days_supply if isinstance(latest.days_supply, int) else 30
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
    query = db.query(RefillHist)
    refill_hists = query.all()

    # Ensure relationships are loaded (optional with selectinload)
    for r in refill_hists:
        _ = r.patient
        _ = r.drug

    return refill_hists


# ----- Patients -----

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
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

@app.get("/patients/search", response_model=List[schemas.PatientOut])
def search_patient(name: str, db: Session = Depends(get_db)):
    """
    name format: "lastname,firstname"
    supports prefix (e.g., "smi,jo")
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
    # Active (non-SOLD) refill — ordered by id DESC so newest is always first
    active_refill = (
        db.query(Refill)
        .filter(
            Refill.prescription_id == prescription_id,
            Refill.state != RxState.SOLD,
        )
        .order_by(desc(Refill.id))
        .first()
    )

    # Latest completed (sold) refill from history
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
            quantity=int(active_refill.quantity or 0),  # type: ignore[arg-type]
            days_supply=int(active_refill.days_supply or 0),  # type: ignore[arg-type]
            total_cost=Decimal(str(active_refill.total_cost or "0.00")),
            sold_date=None,
            completed_date=active_refill.completed_date,  # type: ignore[arg-type]
            state=state_val,
            next_pickup=None,
        )

    # No active refill — show last history entry
    assert latest_hist is not None
    days_supply = int(latest_hist.days_supply or 0)  # type: ignore[arg-type]
    sold_date: Optional[date_type] = latest_hist.sold_date  # type: ignore[assignment]
    next_pickup: Optional[date_type] = (
        sold_date + timedelta(days=days_supply)
        if sold_date and days_supply
        else None
    )
    return schemas.LatestRefillOut(
        quantity=int(latest_hist.quantity or 0),  # type: ignore[arg-type]
        days_supply=days_supply,
        total_cost=Decimal(str(latest_hist.total_cost or "0.00")),
        sold_date=sold_date,
        completed_date=latest_hist.completed_date,  # type: ignore[arg-type]
        state=None,
        next_pickup=next_pickup,
    )


@app.get("/patients/{pid}", response_model=schemas.PatientWithRxs)
def get_patient(pid: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).get(pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for prescription in patient.prescriptions:
        # Get latest refill from RefillHist first
        latest_refill = get_latest_refill_for_prescription(db, prescription.id)
        if latest_refill:
            prescription.latest_refill = latest_refill

            if hasattr(latest_refill, "sold_date") and latest_refill.sold_date:
                # Historical refill: calculate next_pickup
                prescription.next_pickup = latest_refill.sold_date + timedelta(latest_refill.days_supply)
            else:
                # Current or pending refill: show status instead of date
                prescription.next_pickup = latest_refill.state  # e.g., "Pending" or "In Progress"

        # Sort refill history most recent first
        prescription.refill_history = sorted(
            prescription.refill_history,
            key=lambda r: r.sold_date or r.completed_date or date_type.min,
            reverse=True
        )

    return patient


# ----- Drugs -----


@app.get("/drugs", response_model=List[schemas.DrugOut])
def get_drugs(db: Session = Depends(get_db)):
    return db.query(Drug).all()

@app.get("/stock", response_model=List[schemas.StockOut])
def get_stock(db: Session = Depends(get_db)):
    return db.query(Stock).all()

# ----- Prescribers -----

@app.get("/prescribers", response_model=List[schemas.PrescriberOut])
def get_prescribers(db: Session = Depends(get_db)):
    return db.query(Prescriber).all()

@app.get("/prescribers/{npi}", response_model=List[schemas.PrescriberOut])
def get_prescriber(npi: int, db: Session = Depends(get_db)):
    prescriber = db.query(Prescriber).get(npi)
    if not prescriber:
        raise HTTPException(status_code=404, detail="Patient not found")

    return prescriber


# ----- Insurance -----

@app.get("/insurance_companies", response_model=List[schemas.InsuranceCompanyOut])
def get_insurance_companies(db: Session = Depends(get_db)):
    return db.query(InsuranceCompany).all()


@app.get("/insurance_companies/{company_id}/formulary", response_model=List[schemas.FormularyOut])
def get_formulary(company_id: int, db: Session = Depends(get_db)):
    company = db.query(InsuranceCompany).get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")
    entries = db.query(Formulary).filter(Formulary.insurance_company_id == company_id).all()
    for e in entries:
        _ = e.drug
    return entries


@app.get("/patients/{pid}/insurance", response_model=List[schemas.PatientInsuranceOut])
def get_patient_insurance(pid: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).get(pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.query(PatientInsurance).filter(PatientInsurance.patient_id == pid).all()


@app.post("/patients/{pid}/insurance", response_model=schemas.PatientInsuranceOut)
def add_patient_insurance(pid: int, data: schemas.PatientInsuranceCreate, db: Session = Depends(get_db)):
    patient = db.query(Patient).get(pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    company = db.query(InsuranceCompany).get(data.insurance_company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")

    # Check for duplicate active plan
    existing = db.query(PatientInsurance).filter(
        PatientInsurance.patient_id == pid,
        PatientInsurance.insurance_company_id == data.insurance_company_id,
        PatientInsurance.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Patient already has an active plan with this insurance company")

    # If setting as primary, demote existing primary
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
    db.commit()
    db.refresh(ins)
    _ = ins.insurance_company
    return ins


@app.post("/billing/calculate", response_model=schemas.BillingCalculateResponse)
def calculate_billing(data: schemas.BillingCalculateRequest, db: Session = Depends(get_db)):
    drug = db.query(Drug).get(data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    patient_ins = db.query(PatientInsurance).get(data.insurance_id)
    if not patient_ins:
        raise HTTPException(status_code=404, detail="Patient insurance not found")

    cash_price = drug.cost * data.quantity

    formulary_entry = db.query(Formulary).filter(
        Formulary.insurance_company_id == patient_ins.insurance_company_id,
        Formulary.drug_id == data.drug_id
    ).first()

    plan_name = patient_ins.insurance_company.plan_name

    if not formulary_entry or formulary_entry.not_covered:
        return schemas.BillingCalculateResponse(
            cash_price=cash_price,
            not_covered=True,
            plan_name=plan_name,
        )

    raw_copay = formulary_entry.copay_per_30 * Decimal(str(data.days_supply)) / Decimal("30")
    copay_amount = min(raw_copay, cash_price)
    insurance_paid = cash_price - copay_amount

    return schemas.BillingCalculateResponse(
        cash_price=cash_price,
        insurance_price=copay_amount,
        insurance_paid=insurance_paid,
        tier=formulary_entry.tier,
        not_covered=False,
        plan_name=plan_name,
    )


# Healthcheck
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


# ----- Commands -----

@app.post("/commands/generate_test_prescriptions")
def generate_test_prescriptions(db: Session = Depends(get_db)):
    """
    Generate 50 random test prescriptions with a mixture of statuses.
    Removes all previous prescriptions and refills.
    Uses existing patients, prescribers, and drugs.
    """
    # Delete all existing refills, refill_hist, and prescriptions
    db.query(Refill).delete()
    db.query(RefillHist).delete()
    db.query(Prescription).delete()
    db.commit()

    # Get all existing patients, prescribers, and drugs
    patients = db.query(Patient).all()
    prescribers = db.query(Prescriber).all()
    drugs = db.query(Drug).all()

    if not patients or not prescribers or not drugs:
        raise HTTPException(status_code=400, detail="Need patients, prescribers, and drugs in database first")

    # Define possible states and their probabilities
    states_distribution = [
        (RxState.QT, 8),      # 8 in triage
        (RxState.QV1, 6),     # 6 in first verify
        (RxState.QP, 10),     # 10 in prep/fill
        (RxState.QV2, 7),     # 7 in final verify
        (RxState.READY, 8),   # 8 ready for pickup
        (RxState.HOLD, 3),    # 3 on hold
        (RxState.REJECTED, 2), # 2 rejected
        (RxState.SOLD, 6),    # 6 sold (will create refill_hist entries)
    ]

    priorities = [Priority.low, Priority.normal, Priority.high, Priority.stat]

    created_prescriptions = []
    created_refills = []
    created_refill_hists = []

    instructions_pool = [
        "Take 1 tablet by mouth once daily in the morning",
        "Take 1 tablet by mouth twice daily with food",
        "Take 2 tablets by mouth every 4 to 6 hours as needed for pain, not to exceed 8 tablets per day",
        "Take 1 capsule by mouth three times daily until finished",
        "Take 1 tablet by mouth every 8 hours with food as needed for pain",
        "Take 1 tablet by mouth once daily for blood pressure",
        "Take 1 tablet by mouth daily for cardiovascular protection",
        "Take 1 tablet by mouth three times daily with meals",
        "Take 2 tablets by mouth twice daily with meals",
        "Take 1 tablet by mouth daily, INR monitoring required",
        "Take 1 tablet by mouth once daily at bedtime",
        "Take 1 tablet by mouth every 12 hours",
        "Take 1 capsule by mouth once daily on an empty stomach",
        "Inject 10 units subcutaneously once daily before breakfast",
        "Apply 1 patch to skin once weekly, rotate sites",
        "Inhale 2 puffs by mouth every 4 to 6 hours as needed for shortness of breath",
        "Take 1 tablet by mouth once daily, take at the same time each day",
        "Take 1 tablet by mouth twice daily, do not crush or chew",
        "Administer 1 vial by intravenous infusion every 4 weeks as directed by oncologist",
        "Take 1 tablet by mouth once weekly on the same day each week",
    ]

    # Generate 50 prescriptions
    for _ in range(50):
        # Random selections
        patient = random.choice(patients)
        prescriber = random.choice(prescribers)
        drug = random.choice(drugs)

        # Random prescription details
        refill_quantity = random.choice([30, 60, 90])
        total_refills = random.randint(1, 12)
        days_supply = random.choice([7, 14, 30, 60, 90])
        brand_required = random.choice([True, False])

        # Random date within last 90 days
        days_ago = random.randint(0, 90)
        date_received = date_type.today() - timedelta(days=days_ago)

        # Create prescription
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
        db.flush()  # Get prescription.id
        created_prescriptions.append(prescription)

        # Determine state for this prescription (weighted distribution)
        state_pool = []
        for state, count in states_distribution:
            state_pool.extend([state] * count)

        state = random.choice(state_pool)
        priority = random.choice(priorities)

        # Calculate due date and quantity
        quantity = random.choice([refill_quantity // 2, refill_quantity, refill_quantity * 2])
        quantity = min(quantity, prescription.remaining_quantity)

        due_date_offset = random.randint(-10, 30)
        due_date = date_type.today() + timedelta(days=due_date_offset)

        total_cost = drug.cost * quantity

        # If state is SOLD, create a RefillHist entry instead of a Refill
        if state == RxState.SOLD:
            # Random completion and sold dates in the past
            completed_days_ago = random.randint(5, 60)
            completed_date = date_type.today() - timedelta(days=completed_days_ago)
            sold_days_ago = random.randint(0, completed_days_ago - 1)
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

            # Update prescription remaining quantity
            prescription.remaining_quantity -= quantity

        else:
            # Create active refill
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

            # Add special fields based on state
            if state == RxState.READY:
                refill.bin_number = random.randint(1, 100)
                refill.completed_date = date_type.today() - timedelta(days=random.randint(0, 5))
            elif state == RxState.REJECTED:
                refill.rejected_by = f"PharmD {random.choice(['Smith', 'Jones', 'Brown', 'Davis'])}"
                refill.rejection_reason = random.choice([
                    "Incorrect quantity - prescriber authorization needed",
                    "Patient allergy on file",
                    "Duplicate therapy detected",
                    "Insurance rejection - prior authorization required",
                    "Incorrect dosage form"
                ])
                refill.rejection_date = date_type.today() - timedelta(days=random.randint(0, 10))
            elif state == RxState.HOLD:
                # No special fields for HOLD
                pass

            db.add(refill)
            created_refills.append(refill)

            # Decrement remaining quantity for active (non-rejected) fills
            if state != RxState.REJECTED:
                prescription.remaining_quantity -= quantity

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
