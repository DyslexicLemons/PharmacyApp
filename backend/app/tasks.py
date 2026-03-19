"""Celery tasks — replaces the asyncio background loops that ran inside the
FastAPI process.

Each task acquires a short-lived Redis lock (SET NX EX) before touching the
database so that a duplicate Beat invocation during a rolling deploy is a safe
no-op rather than a double-write.
"""

import logging
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import redis as _redis
from celery import shared_task

from datetime import timezone

from sqlalchemy import insert

from .database import SessionLocal
from .models import AuditLog, Drug, Formulary, PatientInsurance, Prescription, QuickCode, Refill, RxState, Stock
from .utils import _int, _write_audit

# If new pricing differs from stored billing by more than this fraction, route to QT.
_PRICE_CHANGE_THRESHOLD = Decimal("0.20")

logger = logging.getLogger("pharmacy.tasks")

_LOCK_TTL = 300  # seconds — well above any realistic task runtime

# ---------------------------------------------------------------------------
# Redis client
# Workers don't go through the FastAPI lifespan, so we manage a module-level
# connection here rather than reusing the cache module's _client.
# ---------------------------------------------------------------------------

_redis_client: "_redis.Redis[str] | None" = None


def _get_redis() -> "_redis.Redis[str]":
    global _redis_client
    if _redis_client is None:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        _redis_client = _redis.Redis.from_url(url, decode_responses=True)
    return _redis_client


def _acquire_lock(key: str) -> bool:
    """Atomic SET NX EX. Returns True if this call owns the lock."""
    return bool(_get_redis().set(key, "1", nx=True, ex=_LOCK_TTL))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@shared_task(name="app.tasks.expire_prescriptions", bind=True, max_retries=3)
def expire_prescriptions(self: Any) -> dict:  # type: ignore[type-arg]
    """Mark prescriptions whose expiration_date < today as inactive."""
    if not _acquire_lock("lock:expire_prescriptions"):
        logger.info("expire_prescriptions: lock held by another worker — skipping")
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            today = date.today()
            expired = (
                db.query(Prescription)
                .filter(
                    Prescription.is_inactive == False,  # noqa: E712
                    Prescription.expiration_date < today,
                )
                .all()
            )
            for rx in expired:
                rx.is_inactive = True  # type: ignore[assignment]
                _write_audit(
                    db,
                    "PRESCRIPTION_EXPIRED",
                    entity_type="prescription",
                    entity_id=_int(rx.id),
                    prescription_id=_int(rx.id),
                    details=f"auto-inactivated: expiration_date={rx.expiration_date}",
                )
            if expired:
                db.commit()
                logger.info("Auto-expired %d prescription(s)", len(expired))
            return {"expired": len(expired)}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in expire_prescriptions task")
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="app.tasks.promote_scheduled_refills", bind=True, max_retries=3)
def promote_scheduled_refills(self: Any) -> dict:  # type: ignore[type-arg]
    """Promote SCHEDULED refills whose due_date <= today.

    Attempts to re-validate billing against the stored insurance info:
    - Sufficient inventory + pricing unchanged + insurance still covers → QP (skip triage)
    - Insufficient physical stock, price changed significantly, or insurance rejects → QT
    - Prescription has no remaining authorized quantity → skipped (stays SCHEDULED)
    """
    if not _acquire_lock("lock:promote_scheduled_refills"):
        logger.info("promote_scheduled_refills: lock held by another worker — skipping")
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            today = date.today()
            due = (
                db.query(Refill)
                .filter(
                    Refill.state == RxState.SCHEDULED,
                    Refill.due_date <= today,
                )
                .with_for_update(of=Refill)
                .all()
            )
            if not due:
                return {"promoted": 0}

            # Bulk-fetch prescriptions, drugs, stock, and insurance in one pass each.
            prescription_ids = {r.prescription_id for r in due}
            prescription_map = {
                p.id: p
                for p in (
                    db.query(Prescription)
                    .filter(Prescription.id.in_(prescription_ids))
                    .with_for_update()
                    .all()
                )
            }

            drug_ids = {r.drug_id for r in due}
            drug_map = {d.id: d for d in db.query(Drug).filter(Drug.id.in_(drug_ids)).all()}
            stock_map = {s.drug_id: s for s in db.query(Stock).filter(Stock.drug_id.in_(drug_ids)).all()}

            insurance_ids = {r.insurance_id for r in due if r.insurance_id}
            patient_ins_map: dict[int, PatientInsurance] = {}
            formulary_map: dict[tuple[int, int], Formulary] = {}
            if insurance_ids:
                pi_list = (
                    db.query(PatientInsurance)
                    .filter(PatientInsurance.id.in_(insurance_ids))
                    .all()
                )
                patient_ins_map = {pi.id: pi for pi in pi_list}
                ins_company_ids = {pi.insurance_company_id for pi in pi_list}
                formulary_entries = (
                    db.query(Formulary)
                    .filter(
                        Formulary.insurance_company_id.in_(ins_company_ids),
                        Formulary.drug_id.in_(drug_ids),
                    )
                    .all()
                )
                formulary_map = {(f.insurance_company_id, f.drug_id): f for f in formulary_entries}

            promoted_qp = 0
            promoted_qt = 0
            now = datetime.now(timezone.utc)
            audit_rows: list[dict] = []

            for refill in due:
                prescription = prescription_map.get(refill.prescription_id)
                if prescription is None:
                    logger.warning(
                        "promote_scheduled_refills: prescription %d not found for refill %d — skipping",
                        refill.prescription_id,
                        refill.id,
                    )
                    continue

                rx_quantity = _int(refill.quantity)
                remaining = _int(prescription.remaining_quantity)
                if remaining < rx_quantity:
                    logger.warning(
                        "promote_scheduled_refills: refill %d skipped — insufficient authorized quantity "
                        "(remaining=%d, needed=%d)",
                        refill.id,
                        remaining,
                        rx_quantity,
                    )
                    continue

                days_supply = _int(refill.days_supply) or 30
                drug = drug_map.get(refill.drug_id)
                new_cash_price = Decimal(str(drug.cost)) * rx_quantity  # type: ignore[union-attr]

                # --- Determine target state and updated billing amounts ---
                target_state = RxState.QP  # optimistic: assume billing validates
                qt_reason: str | None = None
                new_copay: Decimal | None = None
                new_insurance_paid: Decimal | None = None

                # Check physical inventory first.
                stock = stock_map.get(refill.drug_id)
                stock_qty = _int(stock.quantity) if stock else 0
                if stock_qty < rx_quantity:
                    target_state = RxState.QT
                    qt_reason = f"insufficient stock (on_hand={stock_qty}, needed={rx_quantity})"

                if target_state == RxState.QP:
                    if refill.insurance_id:
                        patient_ins = patient_ins_map.get(refill.insurance_id)
                        if not patient_ins:
                            target_state = RxState.QT
                            qt_reason = "insurance record not found"
                        else:
                            formulary = formulary_map.get((patient_ins.insurance_company_id, refill.drug_id))
                            if not formulary or bool(formulary.not_covered):
                                target_state = RxState.QT
                                qt_reason = "insurance does not cover drug"
                            else:
                                raw_copay = (
                                    Decimal(str(formulary.copay_per_30)) * days_supply / Decimal("30")
                                )
                                new_copay = min(raw_copay, new_cash_price)
                                new_insurance_paid = max(Decimal("0.00"), new_cash_price - new_copay)

                                stored_copay = (
                                    Decimal(str(refill.copay_amount))
                                    if refill.copay_amount is not None
                                    else None
                                )
                                if stored_copay and stored_copay > Decimal("0.00"):
                                    change = abs(new_copay - stored_copay) / stored_copay
                                    if change > _PRICE_CHANGE_THRESHOLD:
                                        target_state = RxState.QT
                                        qt_reason = f"copay changed by {change:.0%}"
                    else:
                        # No insurance — compare cash price to what was stored at scheduling time.
                        stored_cost = (
                            Decimal(str(refill.total_cost)) if refill.total_cost is not None else None
                        )
                        if stored_cost and stored_cost > Decimal("0.00"):
                            change = abs(new_cash_price - stored_cost) / stored_cost
                            if change > _PRICE_CHANGE_THRESHOLD:
                                target_state = RxState.QT
                                qt_reason = f"cash price changed by {change:.0%}"

                # Commit the promotion: deduct authorized quantity and advance state.
                prescription.remaining_quantity = remaining - rx_quantity  # type: ignore[assignment]
                refill.state = target_state  # type: ignore[assignment]

                if target_state == RxState.QP:
                    # Update billing to current amounts now that we've validated them.
                    refill.total_cost = new_cash_price  # type: ignore[assignment]
                    if new_copay is not None:
                        refill.copay_amount = new_copay  # type: ignore[assignment]
                        refill.insurance_paid = new_insurance_paid  # type: ignore[assignment]
                    details = f"auto-promoted from SCHEDULED to QP: due_date={refill.due_date}"
                    promoted_qp += 1
                else:
                    details = (
                        f"auto-promoted from SCHEDULED to QT: due_date={refill.due_date}, "
                        f"reason={qt_reason}"
                    )
                    promoted_qt += 1

                audit_rows.append({
                    "timestamp": now,
                    "action": "REFILL_AUTO_QUEUED",
                    "entity_type": "refill",
                    "entity_id": _int(refill.id),
                    "prescription_id": _int(refill.prescription_id),
                    "details": details,
                    "user_id": None,
                    "performed_by": None,
                })

            if audit_rows:
                # Single INSERT for all audit rows instead of N individual db.add() calls.
                db.execute(insert(AuditLog), audit_rows)
            db.commit()
            total = promoted_qp + promoted_qt
            if total:
                logger.info(
                    "Auto-promoted %d scheduled refill(s): %d→QP, %d→QT",
                    total, promoted_qp, promoted_qt,
                )
            return {"promoted": total, "to_qp": promoted_qp, "to_qt": promoted_qt}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in promote_scheduled_refills task")
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="app.tasks.purge_expired_quick_codes", bind=True, max_retries=3)
def purge_expired_quick_codes(self: Any) -> dict:  # type: ignore[type-arg]
    """Delete QuickCode rows that expired more than one hour ago.

    The DB-backed quick-code path (Redis fallback) never deletes rows on its own,
    so without this task the quick_codes table grows unboundedly with stale rows.
    A one-hour grace window is kept so that any in-flight lookups at the moment
    of expiry are not affected.
    """
    if not _acquire_lock("lock:purge_expired_quick_codes"):
        logger.info("purge_expired_quick_codes: lock held by another worker — skipping")
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            # Use a bulk DELETE for efficiency — no need to load rows into memory.
            deleted = (
                db.query(QuickCode)
                .filter(QuickCode.expires_at < cutoff)
                .delete(synchronize_session=False)
            )
            if deleted:
                db.commit()
                logger.info("Purged %d expired quick code(s)", deleted)
            return {"deleted": deleted}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in purge_expired_quick_codes task")
        raise self.retry(exc=exc, countdown=60)
