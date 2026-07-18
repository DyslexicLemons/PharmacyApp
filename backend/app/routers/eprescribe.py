"""External e-prescribing intake — OAuth2 client-credentials + NewRx submission.

Lets an external medical clinic submit a prescription electronically:
1. An admin provisions a clinic client (POST /eprescribe/clients) and hands
   the clinic its client_id/client_secret out of band.
2. The clinic exchanges those credentials for a short-lived JWT
   (POST /eprescribe/oauth/token).
3. The clinic submits a NewRx-shaped payload (POST /eprescribe/newrx), which
   lands directly in the QT queue for pharmacist triage — same trust level
   as the internal POST /refills/upload_json path, just reachable by an
   authenticated outside system instead of only by logged-in staff.
"""

import secrets
from datetime import datetime, timezone
from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import and_
from sqlalchemy.orm import Session

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..auth import CLIENT_TOKEN_EXPIRE_MINUTES, create_client_token, get_current_client, require_admin
from ..database import get_db
from ..models import Drug, ERxClient, Patient, Prescriber, Prescription, Refill, RxState, User
from .. import cache, schemas
from ..utils import _int, _parse_priority, _write_audit
from .auth import _hash_password, _verify_password

router = APIRouter(prefix="/eprescribe", tags=["eprescribe"])
limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# OAuth2 client-credentials token endpoint
# ---------------------------------------------------------------------------

@router.post("/oauth/token", response_model=schemas.ClientTokenResponse)
@limiter.limit("10/minute")
def issue_client_token(
    request: Request,
    body: schemas.ClientTokenRequest,
    db: Session = Depends(get_db),
):
    """Exchange a clinic's client_id/client_secret for a short-lived access token."""
    if body.grant_type != "client_credentials":
        raise HTTPException(status_code=400, detail="Unsupported grant_type")

    client = db.query(ERxClient).filter(ERxClient.client_id == body.client_id).first()
    if (
        not client
        or not client.is_active
        or not _verify_password(body.client_secret, client.hashed_client_secret)
    ):
        raise HTTPException(status_code=401, detail="Invalid client credentials")

    client.last_used_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.commit()

    return schemas.ClientTokenResponse(
        access_token=create_client_token(client),
        expires_in=CLIENT_TOKEN_EXPIRE_MINUTES * 60,
    )


# ---------------------------------------------------------------------------
# NewRx intake
# ---------------------------------------------------------------------------

@router.post("/newrx", response_model=schemas.NewRxResponse)
def submit_newrx(
    data: schemas.NewRxRequest,
    db: Session = Depends(get_db),
    client: ERxClient = Depends(get_current_client),
):
    """Accept an external NewRx submission and land it in the QT queue for triage."""
    patient = db.query(Patient).filter(
        and_(
            Patient.first_name.ilike(data.patient.first_name),
            Patient.last_name.ilike(data.patient.last_name),
            Patient.dob == data.patient.dob,
        )
    ).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found — must exist in system")

    prescriber = db.query(Prescriber).filter(Prescriber.npi == data.prescriber.npi).first()
    if not prescriber:
        prescriber = Prescriber(
            npi=data.prescriber.npi,
            first_name=data.prescriber.first_name,
            last_name=data.prescriber.last_name,
            address=data.prescriber.address,
            phone_number=data.prescriber.phone_number,
            specialty=data.prescriber.specialty,
        )
        db.add(prescriber)
        db.flush()
        _write_audit(
            db, "PRESCRIBER_CREATED",
            entity_type="prescriber", entity_id=_int(prescriber.id),
            details=f"npi={data.prescriber.npi} source=eRx clinic={client.clinic_name}",
            user_id=None,
            performed_by=f"eRx:{client.clinic_name}",
        )

    drug = db.query(Drug).filter(
        and_(
            Drug.drug_name.ilike(data.medication.drug_name),
            Drug.manufacturer.ilike(data.medication.manufacturer),
        )
    ).first()
    if not drug:
        raise HTTPException(status_code=404, detail="Drug not found — must exist in system")

    priority = _parse_priority(data.priority)

    original_qty = data.quantity * data.refills
    prescription = Prescription(
        drug_id=drug.id,
        original_quantity=original_qty,
        remaining_quantity=original_qty,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        date_received=data.written_date,
        instructions=data.sig.directions,
        daw_code=data.daw_code,
    )
    db.add(prescription)
    db.flush()

    refill = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        due_date=datetime(
            data.written_date.year, data.written_date.month, data.written_date.day,
            tzinfo=timezone.utc,
        ),
        quantity=data.quantity,
        days_supply=30,
        total_cost=Decimal(str(drug.cost)) * data.quantity,
        priority=priority,
        state=RxState.QT,
        source="external",
        triage_reason=f"external prescription via eRx (clinic={client.clinic_name}) — manual triage required",
    )
    db.add(refill)

    prescription.remaining_quantity = max(0, original_qty - data.quantity)  # type: ignore[assignment]

    db.flush()
    _write_audit(
        db, "FILL_CREATED",
        entity_type="refill", entity_id=_int(refill.id),
        prescription_id=_int(prescription.id),
        details=(
            f"source=external clinic={client.clinic_name} "
            f"prescription_id={prescription.id} state=QT qty={data.quantity}"
        ),
        user_id=None,
        performed_by=f"eRx:{client.clinic_name}",
    )
    client.last_used_at = datetime.now(timezone.utc)  # type: ignore[assignment]
    db.commit()
    cache.invalidate_queue_for_states({"QT"})
    db.refresh(refill)

    return schemas.NewRxResponse(
        message="Prescription received",
        refill_id=_int(refill.id),
        prescription_id=_int(prescription.id),
        state="QT",
    )


# ---------------------------------------------------------------------------
# Admin: clinic client management
# ---------------------------------------------------------------------------

@router.post("/clients", response_model=schemas.ERxClientCreated, status_code=201)
def create_erx_client(
    body: schemas.ERxClientCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Provision a new clinic API client. The plaintext secret is returned once."""
    client_id = "clinic_" + secrets.token_hex(8)
    client_secret = secrets.token_urlsafe(32)

    client = ERxClient(
        client_id=client_id,
        hashed_client_secret=_hash_password(client_secret),
        clinic_name=body.clinic_name,
        contact_email=body.contact_email,
        contact_phone=body.contact_phone,
    )
    db.add(client)
    db.flush()
    _write_audit(
        db, "ERX_CLIENT_CREATED",
        entity_type="eprescribe_client", entity_id=_int(client.id),
        details=f"clinic_name={body.clinic_name} client_id={client_id}",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
    db.refresh(client)

    return schemas.ERxClientCreated(
        id=_int(client.id),
        client_id=client.client_id,  # type: ignore[arg-type]
        client_secret=client_secret,
        clinic_name=client.clinic_name,  # type: ignore[arg-type]
    )


@router.get("/clients", response_model=List[schemas.ERxClientOut])
def list_erx_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return db.query(ERxClient).order_by(ERxClient.created_at.desc()).all()


@router.delete("/clients/{client_id}", status_code=204)
def deactivate_erx_client(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Soft-deactivate a clinic client — revokes future token issuance and use."""
    client = db.get(ERxClient, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.is_active = False  # type: ignore[assignment]
    _write_audit(
        db, "ERX_CLIENT_DEACTIVATED",
        entity_type="eprescribe_client", entity_id=client_id,
        details=f"clinic_name={client.clinic_name} client_id={client.client_id}",
        user_id=current_user.id,
        performed_by=current_user.username,
    )
    db.commit()
