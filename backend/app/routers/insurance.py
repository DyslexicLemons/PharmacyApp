"""Insurance companies, formulary, and billing endpoints."""

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Drug, Formulary, InsuranceCompany, PatientInsurance, User
from .. import schemas
from ..utils import _int

router = APIRouter(tags=["insurance"])


@router.get("/insurance_companies", response_model=List[schemas.InsuranceCompanyOut])
def get_insurance_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(InsuranceCompany).all()


@router.get("/insurance_companies/{company_id}/formulary", response_model=List[schemas.FormularyOut])
def get_formulary(
    company_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    company = db.get(InsuranceCompany, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Insurance company not found")
    entries = db.query(Formulary).filter(Formulary.insurance_company_id == company_id).all()
    for e in entries:
        _ = e.drug
    return entries


@router.post("/billing/calculate", response_model=schemas.BillingCalculateResponse)
def calculate_billing(
    data: schemas.BillingCalculateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    drug = db.get(Drug, data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    patient_ins = db.get(PatientInsurance, data.insurance_id)
    if not patient_ins:
        raise HTTPException(status_code=404, detail="Patient insurance not found")

    cash_price = Decimal(str(drug.cost)) * data.quantity

    formulary_entry = db.query(Formulary).filter(
        Formulary.insurance_company_id == patient_ins.insurance_company_id,
        Formulary.drug_id == data.drug_id,
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
