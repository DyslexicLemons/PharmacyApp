"""Dashboard analytics endpoint — aggregates pharmacy metrics for reporting."""

from datetime import date, datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import cast, func, case
from sqlalchemy import DateTime as SADateTime
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Drug, Patient, Prescription, Refill, RefillHist, RxState

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class StateSummary(BaseModel):
    state: str
    count: int


class DailyThroughput(BaseModel):
    date: str
    count: int
    revenue: float


class TopDrug(BaseModel):
    drug_name: str
    dispense_count: int
    total_revenue: float


class PriorityBreakdown(BaseModel):
    priority: str
    count: int


class InsuranceSplit(BaseModel):
    insured: int
    uninsured: int
    insured_revenue: float
    uninsured_revenue: float


class DashboardStats(BaseModel):
    total_patients: int
    total_active_prescriptions: int
    total_active_refills: int
    total_fills_completed: int
    queue_states: List[StateSummary]
    daily_throughput: List[DailyThroughput]
    top_drugs: List[TopDrug]
    priority_breakdown: List[PriorityBreakdown]
    total_revenue: float
    total_insurance_paid: float
    total_copay_collected: float
    insurance_split: InsuranceSplit
    total_rejected: int
    rejection_rate_pct: float
    overdue_active_refills: int
    late_fills_in_range: int
    fills_with_due_date_in_range: int
    late_fill_rate_pct: float


_ACTIVE_STATES = [
    RxState.QT, RxState.QV1, RxState.QP, RxState.QV2,
    RxState.READY, RxState.HOLD, RxState.SCHEDULED,
]


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    today = date.today()
    thirty_days_ago = today - timedelta(days=30)

    # --- Volume totals ---
    total_patients = db.query(func.count(Patient.id)).scalar() or 0
    total_active_prescriptions = (
        db.query(func.count(Prescription.id))
        .filter(Prescription.is_inactive == False)  # noqa: E712
        .scalar() or 0
    )
    total_active_refills = (
        db.query(func.count(Refill.id))
        .filter(Refill.state.in_(_ACTIVE_STATES))
        .scalar() or 0
    )
    total_fills_completed = db.query(func.count(RefillHist.id)).scalar() or 0

    # --- Queue state distribution (all states, not just active) ---
    state_rows = (
        db.query(Refill.state, func.count(Refill.id))
        .group_by(Refill.state)
        .all()
    )
    queue_states = [
        StateSummary(
            state=row[0].value if hasattr(row[0], "value") else str(row[0]),
            count=row[1],
        )
        for row in state_rows
    ]

    # --- Daily throughput (last 30 days from refill_hist sold_date) ---
    throughput_rows = (
        db.query(
            RefillHist.sold_date,
            func.count(RefillHist.id),
            func.coalesce(func.sum(RefillHist.total_cost), 0),
        )
        .filter(RefillHist.sold_date >= thirty_days_ago)
        .group_by(RefillHist.sold_date)
        .order_by(RefillHist.sold_date)
        .all()
    )
    daily_throughput = [
        DailyThroughput(date=str(row[0]), count=row[1], revenue=float(row[2]))
        for row in throughput_rows
        if row[0] is not None
    ]

    # --- Top 10 drugs by dispense volume ---
    top_drug_rows = (
        db.query(
            Drug.drug_name,
            func.count(RefillHist.id),
            func.coalesce(func.sum(RefillHist.total_cost), 0),
        )
        .join(RefillHist, RefillHist.drug_id == Drug.id)
        .group_by(Drug.id, Drug.drug_name)
        .order_by(func.count(RefillHist.id).desc())
        .limit(10)
        .all()
    )
    top_drugs = [
        TopDrug(drug_name=row[0], dispense_count=row[1], total_revenue=float(row[2]))
        for row in top_drug_rows
    ]

    # --- Priority breakdown (active refills only) ---
    priority_rows = (
        db.query(Refill.priority, func.count(Refill.id))
        .filter(Refill.state.in_(_ACTIVE_STATES))
        .group_by(Refill.priority)
        .all()
    )
    priority_breakdown = [
        PriorityBreakdown(
            priority=row[0].value if hasattr(row[0], "value") else str(row[0]),
            count=row[1],
        )
        for row in priority_rows
    ]

    # --- Revenue aggregates (all-time from refill_hist) ---
    rev_row = db.query(
        func.coalesce(func.sum(RefillHist.total_cost), 0),
        func.coalesce(func.sum(RefillHist.insurance_paid), 0),
        func.coalesce(func.sum(RefillHist.copay_amount), 0),
    ).first()
    total_revenue = float(rev_row[0]) if rev_row else 0.0
    total_insurance_paid = float(rev_row[1]) if rev_row else 0.0
    total_copay_collected = float(rev_row[2]) if rev_row else 0.0

    # --- Insurance split ---
    insured_count = (
        db.query(func.count(RefillHist.id))
        .filter(RefillHist.insurance_id.isnot(None))
        .scalar() or 0
    )
    uninsured_count = (
        db.query(func.count(RefillHist.id))
        .filter(RefillHist.insurance_id.is_(None))
        .scalar() or 0
    )
    ins_rev_row = db.query(
        func.coalesce(
            func.sum(case((RefillHist.insurance_id.isnot(None), RefillHist.total_cost), else_=0)), 0
        ),
        func.coalesce(
            func.sum(case((RefillHist.insurance_id.is_(None), RefillHist.total_cost), else_=0)), 0
        ),
    ).first()
    insured_revenue = float(ins_rev_row[0]) if ins_rev_row else 0.0
    uninsured_revenue = float(ins_rev_row[1]) if ins_rev_row else 0.0

    insurance_split = InsuranceSplit(
        insured=insured_count,
        uninsured=uninsured_count,
        insured_revenue=insured_revenue,
        uninsured_revenue=uninsured_revenue,
    )

    # --- Rejection rate ---
    total_rejected = (
        db.query(func.count(Refill.id))
        .filter(Refill.state == RxState.REJECTED)
        .scalar() or 0
    )
    total_processed = total_fills_completed + total_rejected
    rejection_rate_pct = (
        round(total_rejected / total_processed * 100, 1) if total_processed > 0 else 0.0
    )

    # --- Overdue in-queue: active refills whose due_date has already passed ---
    now_utc = datetime.now(timezone.utc)
    overdue_active_refills = (
        db.query(func.count(Refill.id))
        .filter(
            Refill.state.in_(_ACTIVE_STATES),
            Refill.due_date.isnot(None),
            Refill.due_date < now_utc,
        )
        .scalar() or 0
    )

    # --- Late fills in range: SOLD refills completed after their due_date within the 30-day window ---
    fills_with_due_date_in_range = (
        db.query(func.count(Refill.id))
        .filter(
            Refill.state == RxState.SOLD,
            Refill.due_date.isnot(None),
            Refill.completed_date.isnot(None),
            Refill.completed_date >= thirty_days_ago,
        )
        .scalar() or 0
    )
    late_fills_in_range = (
        db.query(func.count(Refill.id))
        .filter(
            Refill.state == RxState.SOLD,
            Refill.due_date.isnot(None),
            Refill.completed_date.isnot(None),
            Refill.completed_date >= thirty_days_ago,
            Refill.due_date < cast(Refill.completed_date, SADateTime),
        )
        .scalar() or 0
    )
    late_fill_rate_pct = (
        round(late_fills_in_range / fills_with_due_date_in_range * 100, 1)
        if fills_with_due_date_in_range > 0 else 0.0
    )

    return DashboardStats(
        total_patients=total_patients,
        total_active_prescriptions=total_active_prescriptions,
        total_active_refills=total_active_refills,
        total_fills_completed=total_fills_completed,
        queue_states=queue_states,
        daily_throughput=daily_throughput,
        top_drugs=top_drugs,
        priority_breakdown=priority_breakdown,
        total_revenue=total_revenue,
        total_insurance_paid=total_insurance_paid,
        total_copay_collected=total_copay_collected,
        insurance_split=insurance_split,
        total_rejected=total_rejected,
        rejection_rate_pct=rejection_rate_pct,
        overdue_active_refills=overdue_active_refills,
        late_fills_in_range=late_fills_in_range,
        fills_with_due_date_in_range=fills_with_due_date_in_range,
        late_fill_rate_pct=late_fill_rate_pct,
    )
