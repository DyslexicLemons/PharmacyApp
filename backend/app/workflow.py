"""Shared refill state-machine side-effects.

Both the `/refills/{id}/advance` endpoint (refills.py) and the Celery
simulation tasks (tasks.py) move refills through the same RxState transitions
(QT/QV1/QP/QV2/READY/SOLD) and must apply the same side effects — stock
depletion, prescription quantity reservation, bin assignment, and rejection
bookkeeping — when they do. These live here so both call sites share one
implementation instead of drifting apart.
"""

import random
from datetime import date as date_type, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Prescription, Refill, RxState, Stock, SystemConfig
from .utils import _int

import logging

logger = logging.getLogger("pharmacy.rx")

ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}


def assign_bin(db: Session) -> int:
    """Pick a bin using weighted random selection that favours less-loaded bins.

    The bin range (1–N) is read from system_config.bin_count (default 100, range 60–300).
    Bins with fewer current READY refills receive proportionally higher weight, so
    load is spread across the shelf while still retaining randomness (not always
    picking the single emptiest bin).
    """
    cfg = db.query(SystemConfig).filter(SystemConfig.id == 1).first()
    bin_count = cfg.bin_count if cfg is not None else 100

    rows = (
        db.query(Refill.bin_number, func.count(Refill.id).label("cnt"))
        .filter(Refill.state == RxState.READY, Refill.bin_number.isnot(None))
        .group_by(Refill.bin_number)
        .all()
    )
    counts: dict[int, int] = {int(row.bin_number): row.cnt for row in rows}

    bins = list(range(1, bin_count + 1))
    max_count = max(counts.values(), default=0)
    # Weight = (max_count − occupancy + 1) so empty bins score max_count+1 and the
    # fullest bin scores 1 (never zero, so it can still be picked occasionally).
    weights = [max_count - counts.get(b, 0) + 1 for b in bins]

    return random.choices(bins, weights=weights, k=1)[0]


def apply_ready_entry(db: Session, rx: Refill) -> None:
    """Set the fields that are populated as a side-effect of entering READY."""
    rx.completed_date = datetime.now(timezone.utc)  # type: ignore[assignment]
    rx.bin_number = assign_bin(db)  # type: ignore[assignment]


def apply_rejection(rx: Refill, reason: str, rejected_by: str) -> None:
    """Set the fields that are populated as a side-effect of a QV1 rejection back to QT."""
    rx.triage_reason = f"Pharmacist rejected: {reason}"  # type: ignore[assignment]
    rx.rejected_by = rejected_by  # type: ignore[assignment]
    rx.rejection_reason = reason  # type: ignore[assignment]
    rx.rejection_date = date_type.today()  # type: ignore[assignment]


def adjust_prescription_reservation(
    prescription: Prescription,
    old_reserved: int,
    new_reserved: int,
) -> None:
    """Adjust prescription.remaining_quantity by the change in reserved quantity.

    old_reserved: units this fill currently holds against the prescription (0 if inactive).
    new_reserved: units it will hold after the change (0 if it becomes inactive).
    Raises 409 if the prescription doesn't have enough remaining to cover an increase.
    """
    delta = new_reserved - old_reserved
    remaining = _int(prescription.remaining_quantity)
    if delta > 0 and remaining < delta:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Insufficient remaining quantity on prescription "
                f"(remaining={remaining}, needed={delta})"
            ),
        )
    prescription.remaining_quantity = remaining - delta


def adjust_prescription_quantity(
    db: Session,
    rx: Refill,
    current_state: RxState,
    new_state: RxState,
    rx_quantity: int,
) -> None:
    """Reserve or release prescription quantity when a fill crosses the active/inactive boundary.

    SOLD is excluded: quantity was already reserved when the fill entered the active chain and
    is consumed (not returned) on sale.
    """
    was_active = current_state in ACTIVE_STATES
    will_be_active = new_state in ACTIVE_STATES

    if was_active == will_be_active or new_state == RxState.SOLD:
        return

    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == rx.prescription_id)
        .with_for_update()
        .first()
    )
    if not prescription:
        return

    remaining_before = _int(prescription.remaining_quantity)
    adjust_prescription_reservation(
        prescription,
        old_reserved=rx_quantity if was_active else 0,
        new_reserved=rx_quantity if will_be_active else 0,
    )
    logger.info(
        f"[RX QTY] Prescription #{prescription.id}: remaining_quantity "
        f"{remaining_before} → {prescription.remaining_quantity} "
        f"(state {current_state.value} → {new_state.value}, qty={rx_quantity})"
    )


def adjust_stock(
    db: Session,
    rx: Refill,
    current_state: RxState,
    new_state: RxState,
    rx_quantity: int,
) -> None:
    """Decrement stock when a fill crosses into QV2 (QP → QV2), or return it on reversal (QV2 → QP).

    Stock is committed at the QP→QV2 boundary — the moment physical preparation begins.
    If the pharmacist sends the fill back to QP from QV2 the units are returned to stock.
    """
    going_to_qv2 = current_state == RxState.QP and new_state == RxState.QV2
    returning_from_qv2 = current_state == RxState.QV2 and new_state == RxState.QP

    if not (going_to_qv2 or returning_from_qv2):
        return

    stock = (
        db.query(Stock)
        .filter(Stock.drug_id == rx.drug_id)
        .with_for_update(of=Stock)
        .first()
    )
    if not stock:
        logger.warning(f"[STOCK] No stock record for drug_id={rx.drug_id}; skipping adjustment")
        return

    stock_before = _int(stock.quantity)
    if going_to_qv2:
        stock.quantity = max(0, stock_before - rx_quantity)  # type: ignore[assignment]
    else:
        stock.quantity = stock_before + rx_quantity  # type: ignore[assignment]

    logger.info(
        f"[STOCK] Drug #{rx.drug_id}: quantity {stock_before} → {stock.quantity} "
        f"(state {current_state.value} → {new_state.value}, qty={rx_quantity})"
    )
