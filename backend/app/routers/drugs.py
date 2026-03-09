"""Drug catalog and stock inventory endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Drug, Stock, User
from .. import schemas

router = APIRouter(tags=["drugs"])


@router.get("/drugs", response_model=schemas.PaginatedResponse[schemas.DrugOut])
def get_drugs(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Drug).count()
    items = db.query(Drug).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stock", response_model=schemas.PaginatedResponse[schemas.StockOut])
def get_stock(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Stock).count()
    items = db.query(Stock).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}
