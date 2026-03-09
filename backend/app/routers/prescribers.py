"""Prescriber endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Prescriber, User
from .. import schemas

router = APIRouter(prefix="/prescribers", tags=["prescribers"])


@router.get("", response_model=schemas.PaginatedResponse[schemas.PrescriberOut])
def get_prescribers(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Prescriber).count()
    items = db.query(Prescriber).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{npi}", response_model=schemas.PrescriberOut)
def get_prescriber(
    npi: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prescriber = db.query(Prescriber).filter(Prescriber.npi == npi).first()
    if not prescriber:
        raise HTTPException(status_code=404, detail="Prescriber not found")
    return prescriber
