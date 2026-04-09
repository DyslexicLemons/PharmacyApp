"""LocalInsuranceGateway — default InsuranceAdjudicationGateway backed by the local DB.

Wraps the Formulary and PatientInsurance queries that previously lived inline
in routers/insurance.py and routers/refills.py (_triage_for_new_fill).

This is a simulation-grade implementation: it computes copay amounts from
the local Formulary table but does not connect to a real adjudication network.
Register a third-party implementation (e.g. ClaimLogic, Change Healthcare)
via ProviderRegistry to enable live adjudication.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Drug, Formulary, InsuranceCompany, PatientInsurance
from .base import (
    ClaimSubmissionResult,
    EligibilityResult,
    InsuranceAdjudicationGateway,
)


class LocalInsuranceGateway(InsuranceAdjudicationGateway):
    """Reads InsuranceCompany, Formulary, and PatientInsurance from the local DB.

    claim_id values are synthetic (f"local-{member_id}-{ndc}") since there is
    no external claims network.  reverse_claim is a no-op — there is nothing to
    reverse in the local model.

    If you pass a db session at construction (useful for tests), it is reused
    instead of opening a new one.
    """

    def __init__(self, db: Optional[Session] = None) -> None:
        self._db = db

    def _session(self) -> tuple[Session, bool]:
        if self._db is not None:
            return self._db, False
        return SessionLocal(), True

    async def verify_eligibility(
        self,
        member_id: str,
        group_id: str,
        bin_number: str,
        pcn: str,
        ndc: str,
        quantity: int,
        days_supply: int,
    ) -> EligibilityResult:
        db, should_close = self._session()
        try:
            company = _find_company(db, bin_number, pcn)
            if not company:
                return EligibilityResult(
                    is_eligible=False,
                    member_id=member_id,
                    group_id=group_id,
                    plan_name="Unknown",
                    rejection_code="PLAN_NOT_FOUND",
                    rejection_reason="No matching insurance plan found for BIN/PCN",
                )

            drug = db.query(Drug).filter(Drug.ndc == ndc).first()
            if not drug:
                return EligibilityResult(
                    is_eligible=False,
                    member_id=member_id,
                    group_id=group_id,
                    plan_name=company.plan_name or "",
                    rejection_code="DRUG_NOT_FOUND",
                    rejection_reason=f"NDC {ndc} not found in local catalog",
                )

            formulary = _find_formulary(db, company.id, drug.id)
            if not formulary or bool(formulary.not_covered):
                return EligibilityResult(
                    is_eligible=False,
                    member_id=member_id,
                    group_id=group_id,
                    plan_name=company.plan_name or "",
                    rejection_code="NOT_COVERED",
                    rejection_reason="Drug is not covered under this plan",
                )

            copay = _calculate_copay(formulary, quantity, days_supply, drug)
            return EligibilityResult(
                is_eligible=True,
                member_id=member_id,
                group_id=group_id,
                plan_name=company.plan_name or "",
                copay_amount=copay,
                coverage_tier=int(formulary.tier) if formulary.tier else None,
            )
        finally:
            if should_close:
                db.close()

    async def submit_claim(
        self,
        member_id: str,
        group_id: str,
        bin_number: str,
        pcn: str,
        ndc: str,
        quantity: int,
        days_supply: int,
        prescriber_npi: str,
        unit_cost: Decimal,
    ) -> ClaimSubmissionResult:
        db, should_close = self._session()
        try:
            company = _find_company(db, bin_number, pcn)
            if not company:
                return ClaimSubmissionResult(
                    approved=False,
                    amount_due=unit_cost * quantity,
                    amount_paid=Decimal("0"),
                    rejection_code="PLAN_NOT_FOUND",
                    rejection_reason="No matching insurance plan found for BIN/PCN",
                )

            drug = db.query(Drug).filter(Drug.ndc == ndc).first()
            formulary = _find_formulary(db, company.id, drug.id) if drug else None

            if not formulary or bool(formulary.not_covered):
                cash_price = unit_cost * quantity
                return ClaimSubmissionResult(
                    approved=False,
                    amount_due=cash_price,
                    amount_paid=Decimal("0"),
                    rejection_code="NOT_COVERED",
                    rejection_reason="Drug not covered under this plan",
                )

            cash_price = unit_cost * quantity
            copay = _calculate_copay(formulary, quantity, days_supply, drug)
            insurance_paid = cash_price - copay

            claim_id = f"local-{member_id}-{ndc}-{days_supply}"
            return ClaimSubmissionResult(
                approved=True,
                claim_id=claim_id,
                amount_due=copay,
                amount_paid=insurance_paid,
            )
        finally:
            if should_close:
                db.close()

    async def reverse_claim(self, claim_id: str) -> bool:
        # Local simulation: no external network to reverse against.
        # A real implementation would POST a reversal transaction to the switch.
        return True


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _find_company(db: Session, bin_number: str, pcn: str) -> Optional[InsuranceCompany]:
    return (
        db.query(InsuranceCompany)
        .filter(
            InsuranceCompany.bin_number == bin_number,
            InsuranceCompany.pcn == pcn,
        )
        .first()
    )


def _find_formulary(db: Session, company_id: int, drug_id: int) -> Optional[Formulary]:
    return (
        db.query(Formulary)
        .filter(
            Formulary.insurance_company_id == company_id,
            Formulary.drug_id == drug_id,
        )
        .first()
    )


def _calculate_copay(
    formulary: Formulary,
    quantity: int,
    days_supply: int,
    drug: Drug,
) -> Decimal:
    """Pro-rate the per-30-day copay to the actual days supply, capped at cash price."""
    cash_price = Decimal(str(drug.cost)) * quantity
    raw_copay = Decimal(str(formulary.copay_per_30)) * days_supply / Decimal("30")
    return min(raw_copay, cash_price)
