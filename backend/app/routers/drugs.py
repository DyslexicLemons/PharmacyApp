"""Drug catalog and stock inventory endpoints."""

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from sqlalchemy import func
from ..models import Drug, InventoryShipment, InventoryShipmentItem, ReturnToStock, Stock, User
from ..utils import _write_audit
from .. import schemas

router = APIRouter(tags=["drugs"])


@router.get("/drugs", response_model=schemas.PaginatedResponse[schemas.DrugOut])
def get_drugs(
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Drug).count()
    items = db.query(Drug).offset(offset).limit(limit).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/stock", response_model=schemas.PaginatedResponse[schemas.StockOut])
def get_stock(
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(Stock).count()
    stock_items = db.query(Stock).offset(offset).limit(limit).all()

    # Aggregate RTS totals per drug for display in stock view
    rts_agg = (
        db.query(
            ReturnToStock.drug_id,
            func.count(ReturnToStock.id).label("rts_count"),
            func.sum(ReturnToStock.quantity).label("rts_quantity"),
        )
        .group_by(ReturnToStock.drug_id)
        .all()
    )
    rts_map = {
        row.drug_id: {"rts_count": row.rts_count, "rts_quantity": int(row.rts_quantity or 0)}
        for row in rts_agg
    }

    items = [
        schemas.StockOut(
            drug_id=s.drug_id,
            quantity=s.quantity,
            package_size=s.package_size,
            drug=schemas.DrugOut.model_validate(s.drug),
            rts_count=rts_map.get(s.drug_id, {}).get("rts_count", 0),
            rts_quantity=rts_map.get(s.drug_id, {}).get("rts_quantity", 0),
        )
        for s in stock_items
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/shipments", response_model=schemas.ShipmentOut, status_code=201)
def create_shipment(
    payload: schemas.ShipmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Record a new inventory shipment. Re-authenticates the submitting user before committing.
    Updates stock quantities for each drug received.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="Shipment must contain at least one item")

    # Re-verify credentials
    user = db.query(User).filter(User.username == payload.username, User.is_active == True).first()
    if not user or not _bcrypt.checkpw(payload.password.encode(), user.hashed_password.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials — shipment denied")

    shipment = InventoryShipment(
        performed_by=user.username,
        performed_by_user_id=user.id,
    )
    db.add(shipment)
    db.flush()

    total_bottles = 0
    for item_in in payload.items:
        drug = db.get(Drug, item_in.drug_id)
        if not drug:
            raise HTTPException(status_code=404, detail=f"Drug ID {item_in.drug_id} not found")

        db.add(InventoryShipmentItem(
            shipment_id=shipment.id,
            drug_id=item_in.drug_id,
            bottles_received=item_in.bottles_received,
            units_per_bottle=item_in.units_per_bottle,
        ))

        # Update or create stock entry
        stock = db.query(Stock).filter(Stock.drug_id == item_in.drug_id).first()
        if stock:
            stock.quantity += item_in.bottles_received * item_in.units_per_bottle
        else:
            db.add(Stock(
                drug_id=item_in.drug_id,
                quantity=item_in.bottles_received * item_in.units_per_bottle,
                package_size=item_in.units_per_bottle,
            ))

        total_bottles += item_in.bottles_received

    _write_audit(
        db,
        "INVENTORY_SHIPMENT",
        entity_type="shipment",
        entity_id=shipment.id,
        details=f"{len(payload.items)} drug(s), {total_bottles} total bottle(s) received",
        user_id=user.id,
        performed_by=user.username,
    )

    db.commit()
    db.refresh(shipment)
    return shipment


@router.get("/shipments", response_model=schemas.PaginatedResponse[schemas.ShipmentOut])
def get_shipments(
    limit: int = Query(20, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(InventoryShipment).count()
    items = (
        db.query(InventoryShipment)
        .order_by(InventoryShipment.performed_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}
