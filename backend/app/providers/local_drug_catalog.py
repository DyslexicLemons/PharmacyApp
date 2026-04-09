"""LocalDrugCatalogProvider — default DrugCatalogProvider backed by the local DB.

This wraps the Drug and Stock SQLAlchemy models that previously were queried
inline in routers/drugs.py.  No schema or data changes — only a structural
shift so the core app can call the interface instead of querying directly.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Drug, Stock
from .base import DrugCatalogProvider, DrugPricingResult, DrugSearchResult, InteractionWarning


class LocalDrugCatalogProvider(DrugCatalogProvider):
    """Reads Drug/Stock tables in the local PostgreSQL database.

    A new SessionLocal() is opened per-call so that this provider can be
    used both inside FastAPI (where the session comes from get_db) and from
    Celery tasks that run outside the request lifecycle.

    If you pass a db session at construction (useful for tests), it is reused
    instead of opening a new one.
    """

    def __init__(self, db: Optional[Session] = None) -> None:
        self._db = db

    def _session(self) -> tuple[Session, bool]:
        """Return (session, should_close).  Callers must close when should_close=True."""
        if self._db is not None:
            return self._db, False
        return SessionLocal(), True

    async def search(self, query: str, limit: int = 20) -> list[DrugSearchResult]:
        db, should_close = self._session()
        try:
            drugs = (
                db.query(Drug)
                .filter(Drug.drug_name.ilike(f"%{query}%"))
                .limit(limit)
                .all()
            )
            return [_drug_to_result(d) for d in drugs]
        finally:
            if should_close:
                db.close()

    async def get_pricing(self, ndc: str) -> DrugPricingResult:
        db, should_close = self._session()
        try:
            drug = db.query(Drug).filter(Drug.ndc == ndc).first()
            cost = Decimal(str(drug.cost)) if drug and drug.cost else Decimal("0")
            return DrugPricingResult(
                ndc=ndc,
                unit_cost=cost,
                awp=None,        # local DB doesn't carry AWP
                source="local_db",
            )
        finally:
            if should_close:
                db.close()

    async def check_availability(self, ndc: str, quantity: int) -> bool:
        db, should_close = self._session()
        try:
            drug = db.query(Drug).filter(Drug.ndc == ndc).first()
            if not drug:
                return False
            stock = db.query(Stock).filter(Stock.drug_id == drug.id).first()
            if not stock:
                return False
            return int(stock.quantity or 0) >= quantity
        finally:
            if should_close:
                db.close()

    async def check_interactions(self, ndcs: list[str]) -> list[InteractionWarning]:
        # The local database does not carry interaction data.
        # Register a third-party provider (e.g. FDB DrugInfo) to enable this.
        return []


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _drug_to_result(drug: Drug) -> DrugSearchResult:
    stock: Optional[Stock] = drug.stock  # type: ignore[assignment]
    return DrugSearchResult(
        drug_id=drug.id,
        ndc=drug.ndc or "",
        name=drug.drug_name or "",
        form=drug.drug_form.value if drug.drug_form else "",
        strength="",                         # not stored in current schema
        manufacturer=drug.manufacturer or "",
        unit_cost=Decimal(str(drug.cost)) if drug.cost else Decimal("0"),
        in_stock=bool(stock and int(stock.quantity or 0) > 0),
        quantity_on_hand=int(stock.quantity) if stock else None,
    )
