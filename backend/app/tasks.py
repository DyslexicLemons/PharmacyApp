"""Celery tasks — replaces the asyncio background loops that ran inside the
FastAPI process.

Each task acquires a short-lived Redis lock (SET NX EX) before touching the
database so that a duplicate Beat invocation during a rolling deploy is a safe
no-op rather than a double-write.
"""

import logging
import os
from datetime import date
from typing import Any

import redis as _redis
from celery import shared_task

from .database import SessionLocal
from .models import Prescription, Refill, RxState
from .utils import _int, _write_audit

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
    """Promote SCHEDULED refills whose due_date <= today into QT."""
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
            promoted = 0
            for refill in due:
                prescription = (
                    db.query(Prescription)
                    .filter(Prescription.id == refill.prescription_id)
                    .with_for_update()
                    .first()
                )
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
                        "promote_scheduled_refills: refill %d skipped — insufficient quantity "
                        "(remaining=%d, needed=%d)",
                        refill.id,
                        remaining,
                        rx_quantity,
                    )
                    continue

                prescription.remaining_quantity = remaining - rx_quantity  # type: ignore[assignment]
                refill.state = RxState.QT  # type: ignore[assignment]
                _write_audit(
                    db,
                    "REFILL_AUTO_QUEUED",
                    entity_type="refill",
                    entity_id=_int(refill.id),
                    prescription_id=_int(refill.prescription_id),
                    details=f"auto-promoted from SCHEDULED to QT: due_date={refill.due_date}",
                )
                promoted += 1
            if due:
                db.commit()
                if promoted:
                    logger.info("Auto-queued %d scheduled refill(s) into QT", promoted)
            return {"promoted": promoted}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in promote_scheduled_refills task")
        raise self.retry(exc=exc, countdown=60)
