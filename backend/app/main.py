from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, timedelta
from .schemas import RefillOut, PrescriptionOut
from sqlalchemy import desc
from .database import Base, engine, get_db
from .models import Patient, Prescription, RxState, Drug, Prescriber, Priority, Refill, Stock, RefillHist
from . import schemas


Base.metadata.create_all(bind=engine)


app = FastAPI(title="Pharmacy API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# Utility: state transition map
TRANSITIONS = {
    RxState.QT: RxState.QV1,
    RxState.QV1: RxState.QP,
    RxState.QP: RxState.QV2,
    RxState.QV2: RxState.DONE,
}

# Root route
@app.get("/")
def read_root():
    return {"message": "Pharmacy API running. Visit /docs for Swagger UI."}


# ----- Prescriptions -----
@app.get("/prescriptions", response_model=List[PrescriptionOut])
def get_prescriptions(db: Session = Depends(get_db)):
    return db.query(Prescription).all()

# ----- Refills -----



@app.get("/refills", response_model=List[RefillOut])
def get_refills(state: Optional[RxState] = None, db: Session = Depends(get_db)):
    query = db.query(Refill)
    if state:
        query = query.filter(Refill.state == state)
    refills = query.all()

    # Ensure relationships are loaded (optional with selectinload)
    for r in refills:
        _ = r.patient
        _ = r.drug
        _ = r.prescription.prescriber

    return refills


@app.post("/refills/{rx_id}/advance", response_model=schemas.RefillOut)
def advance_refill(rx_id: int, payload: schemas.AdvanceRequest, db: Session = Depends(get_db)):
    rx = db.query(Refill).get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.state not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")
    rx.state = TRANSITIONS[rx.state]
    db.add(rx)
    db.commit()
    db.refresh(rx)
    return rx

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
    return db.query(Patient).all()

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
    # Try to get the latest active refill first
    refill = (
        db.query(Refill)
        .filter(Refill.prescription_id == prescription_id)
        .order_by(desc(Refill.completed_date))
        .first()
    )

    # Also check historical refills
    refill_latest = (
        db.query(RefillHist)
        .filter(RefillHist.prescription_id == prescription_id)
        .order_by(desc(RefillHist.completed_date))
        .first()
    )

    # If nothing exists at all
    if not refill and not refill_latest:
        return None

    # Prefer refill for quantity/days/state if it exists
    base_refill = refill or refill_latest

    quantity = getattr(base_refill, "quantity", 0) or 0
    days_supply = getattr(base_refill, "days_supply", 0) or 0
    state = getattr(refill, "state", None) if refill else None

    # Override dates with refill_latest if available
    sold_date = getattr(refill_latest, "sold_date", None) if refill_latest else getattr(refill, "sold_date", None)
    completed_date = getattr(refill_latest, "completed_date", None) if refill_latest else getattr(refill, "completed_date", None)

    # Only compute next pickup if active refill (not historical)
    next_pickup = sold_date + timedelta(days=days_supply) if sold_date and state is None else None

    return schemas.LatestRefillOut(
        quantity=quantity,
        days_supply=days_supply,
        sold_date=sold_date,
        completed_date=completed_date,
        state=state,
        next_pickup=next_pickup
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
                # Historical refill: calculate next_fill_date
                prescription.next_fill_date = latest_refill.sold_date + timedelta(days=latest_refill.days_supply)
            else:
                # Current or pending refill: show status instead of date
                prescription.next_fill_date = latest_refill.state  # e.g., "Pending" or "In Progress"

    return patient


# ----- Drugs -----


@app.get("/drugs", response_model=List[schemas.DrugOut])
def get_drugs(db: Session = Depends(get_db)):
    return db.query(Drug).all()

@app.get("/stock", response_model=List[schemas.StockOut])
def get_stock(db: Session = Depends(get_db)):
    return db.query(Stock).all()

# Healthcheck
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
