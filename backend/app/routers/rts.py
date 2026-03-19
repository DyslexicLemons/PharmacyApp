"""Return-to-stock endpoints.

Allows a prescription in the READY state to be returned to stock:
- Transitions the refill to RTS state
- Restores prescription.remaining_quantity (fill was never dispensed)
- Increases Stock.quantity for the drug
- Creates an immutable ReturnToStock audit record
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..database import get_db
from ..models import Drug, Prescription, Refill, ReturnToStock, RxState, Stock, User
from ..utils import _write_audit
from .. import schemas

logger = logging.getLogger("pharmacy.rts")

router = APIRouter(tags=["rts"])


@router.get("/rts/lookup/{refill_id}", response_model=schemas.RTSLookupOut)
def rts_lookup(
    refill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch a READY refill for RTS confirmation preview."""
    rx = db.get(Refill, refill_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Refill #{refill_id} not found")
    if rx.state != RxState.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Refill #{refill_id} is in state {rx.state.value}, not READY — only READY refills can be returned to stock",
        )
    patient = rx.patient
    return schemas.RTSLookupOut(
        refill_id=rx.id,
        drug_name=rx.drug.drug_name,
        ndc=rx.drug.ndc,
        quantity=rx.quantity,
        patient_name=f"{patient.last_name}, {patient.first_name}",
        bin_number=rx.bin_number,
        completed_date=rx.completed_date,
    )


@router.get("/rts/lookup/rx/{prescription_id}", response_model=schemas.RTSLookupOut)
def rts_lookup_by_rx(
    prescription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch the READY refill for a prescription (Rx #) for RTS confirmation preview."""
    rx = (
        db.query(Refill)
        .filter(Refill.prescription_id == prescription_id, Refill.state == RxState.READY)
        .first()
    )
    if not rx:
        prescription = db.get(Prescription, prescription_id)
        if not prescription:
            raise HTTPException(status_code=404, detail=f"Rx #{prescription_id} not found")
        raise HTTPException(
            status_code=400,
            detail=f"Rx #{prescription_id} has no READY refill — only READY refills can be returned to stock",
        )
    patient = rx.patient
    return schemas.RTSLookupOut(
        refill_id=rx.id,
        drug_name=rx.drug.drug_name,
        ndc=rx.drug.ndc,
        quantity=rx.quantity,
        patient_name=f"{patient.last_name}, {patient.first_name}",
        bin_number=rx.bin_number,
        completed_date=rx.completed_date,
    )


@router.post("/rts", response_model=schemas.ReturnToStockOut, status_code=201)
def process_rts(
    payload: schemas.RTSRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process a return-to-stock for a READY refill.

    Transitions the refill to RTS, restores the prescription quantity,
    increments stock, and records the event.
    """
    rx = (
        db.query(Refill)
        .options(selectinload(Refill.drug), selectinload(Refill.patient))
        .filter(Refill.id == payload.refill_id)
        .with_for_update(of=Refill)
        .first()
    )
    if not rx:
        raise HTTPException(status_code=404, detail=f"Refill #{payload.refill_id} not found")
    if rx.state != RxState.READY:
        raise HTTPException(
            status_code=400,
            detail=f"Refill #{payload.refill_id} must be in READY state to return to stock (current: {rx.state.value})",
        )

    quantity = rx.quantity
    drug_id = rx.drug_id

    # Transition refill to RTS (terminal state)
    rx.state = RxState.RTS

    # Restore prescription remaining quantity — the fill was never actually dispensed
    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == rx.prescription_id)
        .with_for_update()
        .first()
    )
    if prescription:
        prescription.remaining_quantity = (prescription.remaining_quantity or 0) + quantity
        logger.info(
            f"[RTS] Prescription #{prescription.id}: remaining_quantity restored by {quantity}"
        )

    # Return units to stock
    stock = db.query(Stock).filter(Stock.drug_id == drug_id).first()
    if stock:
        stock.quantity += quantity
    else:
        db.add(Stock(drug_id=drug_id, quantity=quantity))

    # Create immutable RTS record
    rts_record = ReturnToStock(
        refill_id=rx.id,
        drug_id=drug_id,
        quantity=quantity,
        returned_by=current_user.username,
        returned_by_user_id=current_user.id,
    )
    db.add(rts_record)

    _write_audit(
        db,
        "RETURN_TO_STOCK",
        entity_type="refill",
        entity_id=rx.id,
        details=f"Returned {quantity} units of drug_id={drug_id} to stock (bin #{rx.bin_number})",
        prescription_id=rx.prescription_id,
        user_id=current_user.id,
        performed_by=current_user.username,
    )

    db.commit()
    db.refresh(rts_record)
    logger.info(f"[RTS] Refill #{rx.id}: {quantity} units returned to stock by {current_user.username}")
    return rts_record


@router.get("/rts", response_model=schemas.PaginatedResponse[schemas.ReturnToStockOut])
def get_rts_history(
    limit: int = Query(20, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all return-to-stock records, newest first."""
    total = db.query(ReturnToStock).count()
    items = (
        db.query(ReturnToStock)
        .order_by(ReturnToStock.returned_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
