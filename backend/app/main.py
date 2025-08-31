from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime


from .database import Base, engine, get_db
from .models import Patient, Prescription, RxState, Drug, Prescriber, Priority
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
@app.get("/prescriptions")
def get_prescriptions(state: Optional[RxState] = None, db: Session = Depends(get_db)):
    query = db.query(Prescription)
    if state:
        query = query.filter(Prescription.state == state)
    return query.all()


@app.post("/prescriptions/{rx_id}/advance", response_model=schemas.PrescriptionOut)
def advance_prescription(rx_id: int, payload: schemas.AdvanceRequest, db: Session = Depends(get_db)):
    rx = db.query(Prescription).get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.state not in TRANSITIONS:
        raise HTTPException(status_code=400, detail="No further transition available")
    rx.state = TRANSITIONS[rx.state]
    db.add(rx)
    db.commit()
    db.refresh(rx)
    return rx


# ----- Patients -----

@app.get("/patients")
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

# Healthcheck
@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
