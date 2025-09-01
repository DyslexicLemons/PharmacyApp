from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
from .schemas import RefillOut, PrescriptionOut
from sqlalchemy.orm import joinedload
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

@app.get("/patients/{pid}", response_model=schemas.PatientWithRxs)
def get_patient(pid: int, db: Session = Depends(get_db)):
    p = db.query(Patient).get(pid)
    if not p:
        raise HTTPException(status_code=404, detail="Patient not found")
    return p


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
