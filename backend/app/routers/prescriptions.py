"""Prescription CRUD and image upload endpoints."""

import mimetypes
import os
import uuid
from datetime import date as date_type, timedelta
from decimal import Decimal
from typing import List, Optional

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    Drug, Formulary, Patient, PatientInsurance, Prescription,
    Prescriber, Refill, RefillHist, RxState, User,
)
from .. import cache, schemas
from ..utils import _int, _parse_priority, _write_audit
from .patients import _get_latest_refill_for_prescription

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])

# Upload directory — set via env var, defaults relative to this file
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.normpath(os.path.join(_BASE_DIR, "..", "..", "..", "uploads")),
)
PRESCRIPTIONS_UPLOAD_DIR = os.path.join(UPLOAD_DIR, "prescriptions")


def _build_picture_url(request: Request, picture_path: Optional[str]) -> Optional[str]:
    """Build absolute URL for a stored prescription image (requires auth)."""
    if not picture_path:
        return None
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/v1/prescriptions/uploads/{picture_path}"


@router.get("/uploads/{file_path:path}")
def serve_upload(
    file_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve an uploaded prescription image. Requires a valid JWT."""
    # Prevent path traversal
    safe_path = os.path.normpath(file_path).lstrip("/\\")
    if ".." in safe_path.split(os.sep):
        raise HTTPException(status_code=400, detail="Invalid path")

    full_path = os.path.join(UPLOAD_DIR, safe_path)
    if not os.path.isfile(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type, _ = mimetypes.guess_type(full_path)
    return FileResponse(full_path, media_type=media_type or "application/octet-stream")


@router.get("", response_model=schemas.PaginatedResponse[schemas.PrescriptionOut])
def get_prescriptions(
    limit: int = Query(50, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Prescription).count()
    items = db.query(Prescription).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{prescription_id}", response_model=schemas.PrescriptionDetailOut)
def get_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    prescription.latest_refill = _get_latest_refill_for_prescription(db, prescription_id)  # type: ignore[attr-defined]
    prescription.refill_history = sorted(  # type: ignore[assignment]
        prescription.refill_history,
        key=lambda r: r.sold_date or r.completed_date or date_type.min,
        reverse=True,
    )
    prescription.picture_url = _build_picture_url(request, prescription.picture_path)  # type: ignore[attr-defined]
    return prescription


@router.post("", response_model=schemas.PrescriptionOut)
def create_prescription(
    p: schemas.PrescriptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    patient = db.get(Patient, p.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    prescriber = db.query(Prescriber).filter(Prescriber.npi == p.npi).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Unable to find prescriber")

    date_received = p.date
    expiration_date = date_received + timedelta(days=365)

    prescription = Prescription(
        drug_id=p.drug_id,
        original_quantity=p.refill_quantity * p.total_refills,
        remaining_quantity=p.refill_quantity * p.total_refills,
        patient_id=p.patient_id,
        prescriber_id=prescriber.id,
        date_received=date_received,
        expiration_date=expiration_date,
        instructions=p.directions,
        daw_code=p.daw_code,
    )
    db.add(prescription)
    db.flush()
    _write_audit(
        db, "PRESCRIPTION_CREATED",
        entity_type="prescription", entity_id=_int(prescription.id),
        prescription_id=_int(prescription.id),
        details=f"patient_id={p.patient_id} drug_id={p.drug_id} qty={p.refill_quantity}×{p.total_refills}",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(prescription)
    return prescription


@router.patch("/{prescription_id}", response_model=schemas.PrescriptionOut)
def update_prescription(
    prescription_id: int,
    payload: schemas.PrescriptionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update editable fields on a prescription (expiration_date, instructions)."""
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    locked_by = cache.check_prescription_locked_by_other(prescription_id, _int(current_user.id))
    if locked_by:
        raise HTTPException(status_code=423, detail=f"Prescription is currently open by {locked_by}")
    changed_fields = []
    if payload.expiration_date is not None:
        date_received = prescription.date_received
        max_expiration = date_received + timedelta(days=365)
        if payload.expiration_date < date_received:
            raise HTTPException(status_code=422, detail="Expiration date cannot be before the date received")
        if payload.expiration_date > max_expiration:
            raise HTTPException(status_code=422, detail="Expiration date cannot be more than 1 year after the date received")
        prescription.expiration_date = payload.expiration_date
        changed_fields.append(f"expiration_date={payload.expiration_date}")
    if payload.instructions is not None:
        prescription.instructions = payload.instructions
        changed_fields.append("instructions=updated")
    if changed_fields:
        _write_audit(
            db, "PRESCRIPTION_UPDATED",
            entity_type="prescription", entity_id=prescription_id,
            prescription_id=prescription_id,
            details=" ".join(changed_fields),
            user_id=current_user.id,
            performed_by=current_user.username,
        )
    db.commit()
    db.refresh(prescription)
    return prescription


@router.post("/{prescription_id}/picture", response_model=schemas.PrescriptionOut)
async def update_prescription_picture(
    prescription_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload or replace a prescription image. Saves to local filesystem."""
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    locked_by = cache.check_prescription_locked_by_other(prescription_id, _int(current_user.id))
    if locked_by:
        raise HTTPException(status_code=423, detail=f"Prescription is currently open by {locked_by}")

    # Delete old file if one exists
    if prescription.picture_path:
        old_full_path = os.path.join(UPLOAD_DIR, prescription.picture_path)
        if os.path.exists(old_full_path):
            os.remove(old_full_path)

    # Save new file
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    rel_path = f"prescriptions/{filename}"
    full_path = os.path.join(PRESCRIPTIONS_UPLOAD_DIR, filename)

    os.makedirs(PRESCRIPTIONS_UPLOAD_DIR, exist_ok=True)
    content = await file.read()
    with open(full_path, "wb") as f:
        f.write(content)

    prescription.picture_path = rel_path  # type: ignore[assignment]
    db.commit()
    db.refresh(prescription)
    prescription.picture_url = _build_picture_url(request, rel_path)  # type: ignore[attr-defined]
    return prescription


@router.post("/{prescription_id}/fill")
def fill_prescription(
    prescription_id: int,
    data: schemas.FillScriptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new refill for an existing prescription.
    Uses SELECT FOR UPDATE to prevent concurrent double-fills.
    """
    locked_by = cache.check_prescription_locked_by_other(prescription_id, _int(current_user.id))
    if locked_by:
        raise HTTPException(status_code=423, detail=f"Prescription is currently open by {locked_by}")

    prescription = (
        db.query(Prescription)
        .filter(Prescription.id == prescription_id)
        .with_for_update()
        .first()
    )
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if prescription.expiration_date and prescription.expiration_date < date_type.today():
        raise HTTPException(status_code=409, detail="Prescription has expired and cannot be filled")

    BLOCKING_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}
    ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

    existing = db.query(Refill).filter(
        Refill.prescription_id == prescription_id,
        Refill.state.in_(BLOCKING_STATES),
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Prescription already has an active fill in state {existing.state.value}",
        )

    remaining_qty = _int(prescription.remaining_quantity)
    if remaining_qty <= 0:
        raise HTTPException(status_code=409, detail="No remaining authorized quantity on this prescription")

    if data.quantity > remaining_qty:
        raise HTTPException(
            status_code=422,
            detail=f"Requested quantity ({data.quantity}) exceeds remaining authorized quantity ({remaining_qty})",
        )

    cash_price = Decimal(str(prescription.drug.cost)) * data.quantity

    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance_id: Optional[int] = None

    initial_state = RxState.SCHEDULED if data.scheduled else RxState.QV1
    fill_triage_reason: Optional[str] = None

    if data.insurance_id:
        patient_ins = db.query(PatientInsurance).filter(
            PatientInsurance.id == data.insurance_id,
            PatientInsurance.patient_id == prescription.patient_id,
        ).first()
        if patient_ins:
            formulary_entry = db.query(Formulary).filter(
                Formulary.insurance_company_id == patient_ins.insurance_company_id,
                Formulary.drug_id == prescription.drug_id,
            ).first()
            if not data.scheduled:
                not_covered = bool(formulary_entry.not_covered) if formulary_entry else True
                if not formulary_entry or not_covered:
                    initial_state = RxState.QT
                    fill_triage_reason = "insurance does not cover drug"
            if formulary_entry and not bool(formulary_entry.not_covered):
                raw_copay = Decimal(str(formulary_entry.copay_per_30)) * data.days_supply / Decimal("30")
                copay_amount = min(raw_copay, cash_price)
                insurance_paid = cash_price - copay_amount
            insurance_id = _int(patient_ins.id)

    if initial_state == RxState.QV1:
        matching_hist = db.query(RefillHist).filter(
            RefillHist.prescription_id == prescription_id,
            RefillHist.quantity == data.quantity,
            RefillHist.days_supply == data.days_supply,
            RefillHist.insurance_id == data.insurance_id,
        ).order_by(desc(RefillHist.completed_date)).first()
        if matching_hist:
            initial_state = RxState.QP

    priority = _parse_priority(data.priority)

    refill = Refill(
        prescription_id=prescription_id,
        patient_id=prescription.patient_id,
        drug_id=prescription.drug_id,
        due_date=data.due_date or date_type.today(),
        quantity=data.quantity,
        days_supply=data.days_supply,
        total_cost=cash_price,
        priority=priority,
        state=initial_state,
        source="manual",
        insurance_id=insurance_id,
        copay_amount=copay_amount,
        insurance_paid=insurance_paid,
        triage_reason=fill_triage_reason,
    )
    db.add(refill)

    if initial_state in ACTIVE_STATES:
        old_qty = remaining_qty
        prescription.remaining_quantity = max(0, old_qty - data.quantity)  # type: ignore[assignment]

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        prescription_id=prescription_id,
        details=(
            f"prescription_id={prescription_id} state={initial_state.value} "
            f"qty={data.quantity} days={data.days_supply} priority={priority.value}"
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(refill)

    response: dict = {
        "message": "Fill created successfully",
        "refill_id": refill.id,
        "state": str(initial_state),
    }
    if copay_amount is not None:
        response["cash_price"] = float(cash_price)
        response["copay_amount"] = float(copay_amount)
        response["insurance_paid"] = float(insurance_paid or 0)
    return response


@router.post("/{prescription_id}/hold", response_model=schemas.PrescriptionDetailOut)
def hold_prescription(
    prescription_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Place the active refill for this prescription on hold.
    Valid from states: QT, QV1, QP, QV2, SCHEDULED.
    """
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    locked_by = cache.check_prescription_locked_by_other(prescription_id, _int(current_user.id))
    if locked_by:
        raise HTTPException(status_code=423, detail=f"Prescription is currently open by {locked_by}")

    if prescription.is_inactive:
        raise HTTPException(status_code=409, detail="Prescription is inactive")

    HOLDABLE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.SCHEDULED}
    ACTIVE_STATES = {RxState.QT, RxState.QV1, RxState.QP, RxState.QV2, RxState.READY}

    refill = (
        db.query(Refill)
        .filter(
            Refill.prescription_id == prescription_id,
            Refill.state.in_(HOLDABLE_STATES),
        )
        .order_by(desc(Refill.id))
        .first()
    )

    if not refill:
        raise HTTPException(status_code=409, detail="No active refill that can be placed on hold")

    current_state = refill.state if isinstance(refill.state, RxState) else RxState(str(refill.state))

    # Return quantity to prescription when moving out of an active state
    if current_state in ACTIVE_STATES:
        rx_quantity = _int(refill.quantity)
        old_qty = _int(prescription.remaining_quantity)
        prescription.remaining_quantity = old_qty + rx_quantity  # type: ignore[assignment]

    refill.state = RxState.HOLD  # type: ignore[assignment]

    _write_audit(
        db, "STATE_TRANSITION",
        entity_type="refill", entity_id=_int(refill.id),
        prescription_id=prescription_id,
        details=(
            f"{current_state.value} → HOLD "
            f"prescription_id={prescription_id} patient_id={prescription.patient_id}"
        ),
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(prescription)

    prescription.latest_refill = _get_latest_refill_for_prescription(db, prescription_id)  # type: ignore[attr-defined]
    prescription.refill_history = sorted(  # type: ignore[assignment]
        prescription.refill_history,
        key=lambda r: r.sold_date or r.completed_date or date_type.min,
        reverse=True,
    )
    prescription.picture_url = _build_picture_url(request, prescription.picture_path)  # type: ignore[attr-defined]
    return prescription


@router.post("/{prescription_id}/inactivate", response_model=schemas.PrescriptionDetailOut)
def inactivate_prescription(
    prescription_id: int,
    payload: schemas.InactivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Inactivate a prescription. Requires the user to re-verify their credentials.
    Once inactivated, the prescription cannot be filled and shows as INACTIVATED.
    """
    # Re-verify credentials
    user = db.query(User).filter(User.username == payload.username, User.is_active == True).first()
    if not user or not _bcrypt.checkpw(payload.password.encode(), user.hashed_password.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials — inactivation denied")

    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    locked_by = cache.check_prescription_locked_by_other(prescription_id, _int(current_user.id))
    if locked_by:
        raise HTTPException(status_code=423, detail=f"Prescription is currently open by {locked_by}")

    if prescription.is_inactive:
        raise HTTPException(status_code=409, detail="Prescription is already inactive")

    prescription.is_inactive = True  # type: ignore[assignment]
    _write_audit(
        db, "PRESCRIPTION_INACTIVATED",
        entity_type="prescription", entity_id=prescription_id,
        prescription_id=prescription_id,
        details=f"inactivated by {current_user.username} (verified as {payload.username})",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(prescription)

    prescription.latest_refill = _get_latest_refill_for_prescription(db, prescription_id)  # type: ignore[attr-defined]
    prescription.refill_history = sorted(  # type: ignore[assignment]
        prescription.refill_history,
        key=lambda r: r.sold_date or r.completed_date or date_type.min,
        reverse=True,
    )
    prescription.picture_url = _build_picture_url(request, prescription.picture_path)  # type: ignore[attr-defined]
    return prescription


# ---------------------------------------------------------------------------
# View locks — prevent concurrent access to the same prescription
# ---------------------------------------------------------------------------

@router.post("/{prescription_id}/lock", status_code=200)
def acquire_lock(
    prescription_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Acquire a view lock on a prescription for the calling user.

    - 200: lock acquired (or already owned — TTL refreshed).
    - 423: locked by another user; detail message names them.
    - 404: prescription not found.
    """
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    acquired, locked_by = cache.acquire_prescription_lock(
        prescription_id, _int(current_user.id), current_user.username
    )
    if not acquired:
        raise HTTPException(
            status_code=423,
            detail=f"Prescription is currently open by {locked_by}",
        )
    return {"locked": True, "prescription_id": prescription_id}


@router.delete("/{prescription_id}/lock", status_code=204)
def release_lock(
    prescription_id: int,
    current_user: User = Depends(get_current_user),
):
    """Release a view lock. No-op if the lock belongs to someone else or doesn't exist."""
    cache.release_prescription_lock(prescription_id, _int(current_user.id))


@router.get("/{prescription_id}/lock")
def get_lock_status(
    prescription_id: int,
    current_user: User = Depends(get_current_user),
):
    """Return who (if anyone) currently holds the view lock on this prescription."""
    data = cache.get_prescription_lock(prescription_id)
    if data:
        return {"locked": True, "locked_by": data.get("username")}
    return {"locked": False, "locked_by": None}
