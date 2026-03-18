"""Patient CRUD, search, and insurance endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, noload

from ..auth import get_current_user
from ..database import get_db
from ..models import InsuranceCompany, Patient, PatientInsurance, User
from .. import schemas
from ..utils import _write_audit, _int

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", response_model=schemas.PaginatedResponse[schemas.PatientOut])
def get_patients(
    limit: int = Query(50, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List patients with server-side pagination."""
    total = db.query(Patient).count()
    items = db.query(Patient).options(noload("*")).order_by(Patient.last_name, Patient.first_name).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=schemas.PatientOut)
def create_patient(
    p: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
        details=f"{p.last_name}, {p.first_name} DOB={p.dob}",
    )
    db.commit()
    db.refresh(patient)
    return patient


@router.get("/search", response_model=List[schemas.PatientOut])
def search_patient(
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search patients by 'lastname,firstname' or 'firstname,lastname'.
    Requires at least 3 characters for each part. Returns exact prefix matches
    first, then near-matches (2-char prefix) not already in exact results."""
    if "," not in name:
        raise HTTPException(status_code=400, detail="Name must be 'lastname,firstname' or 'firstname,lastname'")
    a, b = [s.strip() for s in name.split(",", 1)]

    if len(a) < 3 or len(b) < 3:
        raise HTTPException(status_code=400, detail="At least 3 characters required for both first and last name")

    seen_ids: set = set()

    def run_query(last: str, first: str):
        q = db.query(Patient)
        if last:
            q = q.filter(Patient.last_name.ilike(f"{last}%"))
        if first:
            q = q.filter(Patient.first_name.ilike(f"{first}%"))
        group = []
        for p in q.order_by(Patient.last_name.asc(), Patient.first_name.asc()).all():
            if p.id not in seen_ids:
                seen_ids.add(p.id)
                group.append(p)
        return group

    # Exact prefix matches (both orderings)
    primary = run_query(last=a, first=b)
    secondary = run_query(last=b, first=a)

    # Near-matches: first 2 chars of each part (patients not already in exact results)
    a2, b2 = a[:2], b[:2]
    near_primary = run_query(last=a2, first=b2)
    near_secondary = run_query(last=b2, first=a2)

    return primary + secondary + near_primary + near_secondary


@router.get("/{pid}", response_model=schemas.PatientWithRxs)
def get_patient(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import date as date_type, timedelta
    from sqlalchemy import desc
    from ..models import Refill, RefillHist, RxState
    from decimal import Decimal

    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    for prescription in patient.prescriptions:
        latest_refill = _get_latest_refill_for_prescription(db, prescription.id)  # type: ignore[arg-type]
        if latest_refill:
            prescription.latest_refill = latest_refill  # type: ignore[attr-defined]
            if hasattr(latest_refill, "sold_date") and latest_refill.sold_date:
                prescription.next_pickup = latest_refill.sold_date + timedelta(latest_refill.days_supply)  # type: ignore[attr-defined]
            else:
                prescription.next_pickup = latest_refill.state  # type: ignore[attr-defined]

        prescription.refill_history = sorted(  # type: ignore[assignment]
            prescription.refill_history,
            key=lambda r: r.sold_date or r.completed_date or date_type.min,
            reverse=True,
        )

    return patient


@router.patch("/{pid}", response_model=schemas.PatientOut)
def update_patient(
    pid: int,
    p: schemas.PatientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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


@router.get("/{pid}/insurance", response_model=List[schemas.PatientInsuranceOut])
def get_patient_insurance(
    pid: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return db.query(PatientInsurance).filter(PatientInsurance.patient_id == pid).all()


@router.post("/{pid}/insurance", response_model=schemas.PatientInsuranceOut)
def add_patient_insurance(
    pid: int,
    data: schemas.PatientInsuranceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.get(Patient, pid)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    company = db.get(InsuranceCompany, data.insurance_company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")

    existing = db.query(PatientInsurance).filter(
        PatientInsurance.patient_id == pid,
        PatientInsurance.insurance_company_id == data.insurance_company_id,
        PatientInsurance.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail="Patient already has an active plan with this insurance company",
        )

    if data.is_primary:
        db.query(PatientInsurance).filter(
            PatientInsurance.patient_id == pid,
            PatientInsurance.is_primary == True,
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
        details=f"plan={company.plan_name} member_id={data.member_id} primary={data.is_primary}",
    )
    db.commit()
    db.refresh(ins)
    _ = ins.insurance_company
    return ins


# ---------------------------------------------------------------------------
# Shared helper — also used by prescriptions router
# ---------------------------------------------------------------------------

def _get_latest_refill_for_prescription(db: Session, prescription_id: int):
    from datetime import timedelta
    from decimal import Decimal
    from sqlalchemy import desc
    from ..models import Refill, RefillHist, RxState

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
    from datetime import date as date_type
    days_supply = _int(latest_hist.days_supply)
    sold_date = latest_hist.sold_date
    next_pickup = sold_date + timedelta(days=days_supply) if sold_date and days_supply else None
    return schemas.LatestRefillOut(
        quantity=_int(latest_hist.quantity),
        days_supply=days_supply,
        total_cost=Decimal(str(latest_hist.total_cost or "0.00")),
        sold_date=sold_date,
        completed_date=latest_hist.completed_date,  # type: ignore[arg-type]
        state=None,
        next_pickup=next_pickup,
    )
