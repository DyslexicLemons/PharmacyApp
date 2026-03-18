"""Billing calculation endpoint — standalone cost/copay preview."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Drug, Formulary, PatientInsurance, User
from .. import schemas

router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/calculate", response_model=schemas.BillingCalculateResponse)
def calculate_billing(
    data: schemas.BillingCalculateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Preview billing cost/copay for a drug + patient insurance combination."""
    drug = db.get(Drug, data.drug_id)
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found")

    cash_price = Decimal(str(drug.cost)) * data.quantity

    patient_ins = db.get(PatientInsurance, data.insurance_id)
    if not patient_ins:
        raise HTTPException(status_code=404, detail="Insurance not found")

    formulary_entry = db.query(Formulary).filter(
        Formulary.insurance_company_id == patient_ins.insurance_company_id,
        Formulary.drug_id == data.drug_id,
    ).first()

    plan_name = patient_ins.insurance_company.plan_name

    if not formulary_entry or bool(formulary_entry.not_covered):
        return schemas.BillingCalculateResponse(
            cash_price=cash_price,
            not_covered=True,
            plan_name=plan_name,
        )

    raw_copay = Decimal(str(formulary_entry.copay_per_30)) * data.days_supply / Decimal("30")
    copay_amount = min(raw_copay, cash_price)
    insurance_paid = max(Decimal("0.00"), cash_price - copay_amount)

    return schemas.BillingCalculateResponse(
        cash_price=cash_price,
        insurance_price=copay_amount,
        insurance_paid=insurance_paid,
        tier=formulary_entry.tier,
        not_covered=False,
        plan_name=plan_name,
    )
