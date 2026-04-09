"""Celery tasks — replaces the asyncio background loops that ran inside the
FastAPI process.

Each task acquires a short-lived Redis lock (SET NX EX) before touching the
database so that a duplicate Beat invocation during a rolling deploy is a safe
no-op rather than a double-write.
"""

import logging
import os
import random
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import redis as _redis
from celery import shared_task

from datetime import timezone

from sqlalchemy import func, insert

from .database import SessionLocal
from .models import (
    AuditLog, Drug, Formulary, Patient, PatientInsurance,
    Prescription, Prescriber, Priority, QuickCode,
    Refill, RefillHist, RxState, SimWorker, SimWorkerRole, StationName, Stock, SystemConfig,
)
from .utils import _int, _write_audit

# If new pricing differs from stored billing by more than this fraction, route to QT.
_PRICE_CHANGE_THRESHOLD = Decimal("0.20")

logger = logging.getLogger("pharmacy.tasks")

_LOCK_TTL = 30  # seconds — crash-recovery window; sim tasks fire every 10–30s

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


def _release_lock(key: str) -> None:
    """Delete the lock key so the next scheduled run can acquire it immediately."""
    _get_redis().delete(key)


def _invalidate_queue_cache() -> None:
    """Delete all refills:queue:* keys after a bulk state change.

    The queue list endpoint caches results with a 30s TTL.  Background tasks
    that mutate refill states bypass the router layer and never call
    _invalidate_queue_for_states, so without this the UI can show stale queue
    counts and items for up to 30 seconds after a Celery task runs.
    """
    try:
        r = _get_redis()
        keys = r.keys("refills:queue:*")
        if keys:
            r.delete(*keys)
    except Exception as exc:
        logger.warning("_invalidate_queue_cache failed: %s", exc)


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
            _due_ids = [r[0] for r in (
                db.query(Refill.id)
                .filter(
                    Refill.state == RxState.SCHEDULED,
                    Refill.due_date <= today,
                )
                .with_for_update()
                .all()
            )]
            due = db.query(Refill).filter(Refill.id.in_(_due_ids)).all() if _due_ids else []
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
                if target_state == RxState.QT:
                    refill.triage_reason = qt_reason  # type: ignore[assignment]

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
                _invalidate_queue_cache()
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


# ---------------------------------------------------------------------------
# Simulation helpers
# ---------------------------------------------------------------------------

_SIM_FIRST_NAMES = [
    "Alice", "Bob", "Carol", "David", "Emily", "Frank", "Grace", "Henry",
    "Isabel", "James", "Karen", "Leo", "Maria", "Nathan", "Olivia", "Paul",
    "Quinn", "Rachel", "Samuel", "Teresa", "Victor", "Wendy", "Xander", "Yvonne",
]

_SIM_LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Thomas", "Jackson",
    "White", "Harris", "Martin", "Thompson", "Martinez", "Robinson",
]

_SIM_INSTRUCTIONS = [
    "Take 1 tablet by mouth once daily in the morning",
    "Take 1 tablet by mouth twice daily with food",
    "Take 2 tablets by mouth every 4 to 6 hours as needed for pain",
    "Take 1 capsule by mouth three times daily until finished",
    "Take 1 tablet by mouth once daily for blood pressure",
    "Take 1 tablet by mouth daily for cardiovascular protection",
    "Take 1 tablet by mouth once daily at bedtime",
    "Take 1 tablet by mouth every 12 hours",
    "Inject 10 units subcutaneously once daily before breakfast",
    "Inhale 2 puffs by mouth every 4 to 6 hours as needed",
]

_SIM_REJECTION_REASONS = [
    "Incorrect quantity — prescriber authorization needed",
    "Patient allergy on file",
    "Duplicate therapy detected",
    "Insurance rejection — prior authorization required",
    "Incorrect dosage form",
    "Drug interaction identified — prescriber notified",
    "Quantity exceeds authorized limit",
]

_SIM_PERFORMER = "virtual-sim"


def _sim_get_config(db: "SessionLocal") -> "SystemConfig | None":  # type: ignore[name-defined]
    """Return SystemConfig row id=1, or None if missing."""
    return db.query(SystemConfig).filter(SystemConfig.id == 1).first()


def _sim_assign_bin(db: "SessionLocal", bin_count: int) -> int:  # type: ignore[name-defined]
    """Weighted bin assignment — same algorithm as the router's _assign_bin."""
    rows = (
        db.query(Refill.bin_number, func.count(Refill.id).label("cnt"))
        .filter(Refill.state == RxState.READY, Refill.bin_number.isnot(None))
        .group_by(Refill.bin_number)
        .all()
    )
    counts: dict[int, int] = {int(row.bin_number): row.cnt for row in rows}
    bins = list(range(1, bin_count + 1))
    max_count = max(counts.values(), default=0)
    weights = [max_count - counts.get(b, 0) + 1 for b in bins]
    return random.choices(bins, weights=weights, k=1)[0]


# ---------------------------------------------------------------------------
# Simulation tasks
# ---------------------------------------------------------------------------

_SIM_BATCH = 5  # max refills processed per cycle per agent


@shared_task(name="app.tasks.simulate_patient_arrivals", bind=True, max_retries=3)
def simulate_patient_arrivals(self: Any) -> dict:  # type: ignore[type-arg]
    """Virtual patients submit new prescriptions, entering the QT queue.

    Picks random patients, prescribers, and drugs from whatever already exists
    in the database. Skips silently if no base data is present, so it is safe
    to run even before test data is seeded.
    """
    lock_key = "lock:simulate_patient_arrivals"
    if not _acquire_lock(lock_key):
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            cfg = _sim_get_config(db)
            if not cfg or not cfg.simulation_enabled:
                return {"skipped": True}

            patients = db.query(Patient).limit(100).all()
            prescribers = db.query(Prescriber).limit(50).all()
            drugs = db.query(Drug).limit(50).all()

            if not patients or not prescribers or not drugs:
                logger.info("simulate_patient_arrivals: no base data — skipping")
                return {"skipped": True, "reason": "no base data"}

            count = random.randint(1, max(1, _int(cfg.sim_arrival_rate)))
            created = 0
            now = datetime.now(timezone.utc)
            audit_rows: list[dict] = []

            for _ in range(count):
                patient = random.choice(patients)
                drug = random.choice(drugs)
                prescriber = random.choice(prescribers)

                quantity = random.choice([30, 60, 90])
                total_refills = random.randint(2, 6)
                days_supply = random.choice([30, 60, 90])
                today = date.today()

                rx = Prescription(
                    drug_id=drug.id,
                    daw_code=0,
                    original_quantity=quantity * total_refills,
                    remaining_quantity=quantity * total_refills,
                    date_received=today,
                    expiration_date=today.replace(year=today.year + 1),
                    patient_id=patient.id,
                    prescriber_id=prescriber.id,
                    instructions=random.choice(_SIM_INSTRUCTIONS),
                )
                db.add(rx)
                db.flush()

                refill = Refill(
                    prescription_id=rx.id,
                    patient_id=patient.id,
                    drug_id=drug.id,
                    due_date=today,
                    quantity=quantity,
                    days_supply=days_supply,
                    total_cost=Decimal(str(drug.cost)) * quantity,
                    priority=Priority.normal,
                    state=RxState.QT,
                    source="simulation",
                    triage_reason="simulated patient arrival",
                )
                db.add(refill)
                rx.remaining_quantity = max(0, (quantity * total_refills) - quantity)  # type: ignore[assignment]
                db.flush()

                audit_rows.append({
                    "timestamp": now,
                    "action": "SIM_PATIENT_ARRIVAL",
                    "entity_type": "refill",
                    "entity_id": _int(refill.id),
                    "prescription_id": _int(rx.id),
                    "details": (
                        f"virtual patient arrival: drug_id={drug.id} qty={quantity} "
                        f"patient_id={patient.id}"
                    ),
                    "user_id": None,
                    "performed_by": _SIM_PERFORMER,
                })
                created += 1

            if audit_rows:
                db.execute(insert(AuditLog), audit_rows)
            db.commit()
            if created:
                _invalidate_queue_cache()
                logger.info("simulate_patient_arrivals: created %d new prescription(s)", created)
            return {"created": created}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in simulate_patient_arrivals task")
        raise self.retry(exc=exc, countdown=60)
    finally:
        _release_lock(lock_key)


@shared_task(name="app.tasks.simulate_technician", bind=True, max_retries=3)
def simulate_technician(self: Any) -> dict:  # type: ignore[type-arg]
    """Virtual pharmacy technicians work the QT, QP, and READY queues.

    Each active SimWorker with role=technician is stationed at triage (QT),
    fill (QP), or window (READY→SOLD).  Technicians can only work at their
    current station.  If work dries up, they travel to a station that has
    items — taking 5–10 seconds before they can process anything again.
    Window work also archives the sold refill to RefillHist.
    """
    lock_key = "lock:simulate_technician"
    if not _acquire_lock(lock_key):
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            cfg = _sim_get_config(db)
            if not cfg or not cfg.simulation_enabled:
                return {"skipped": True}

            techs = (
                db.query(SimWorker)
                .filter(SimWorker.role == SimWorkerRole.technician, SimWorker.is_active.is_(True))
                .all()
            )
            if not techs:
                return {"skipped": True, "reason": "no active technicians"}

            now = datetime.now(timezone.utc)
            today = date.today()
            audit_rows: list[dict] = []
            qt_advanced = 0
            qp_advanced = 0
            ready_advanced = 0
            traveling = 0

            # Snapshot queue depths once; used to decide whether it's worth traveling.
            qt_count = db.query(func.count(Refill.id)).filter(Refill.state == RxState.QT).scalar() or 0
            qp_count = db.query(func.count(Refill.id)).filter(Refill.state == RxState.QP).scalar() or 0
            ready_count = db.query(func.count(Refill.id)).filter(
                Refill.state == RxState.READY, Refill.completed_date <= today,
            ).scalar() or 0

            # Track IDs already claimed this cycle so workers at the same station
            # don't process the same refill (SKIP LOCKED only guards across transactions,
            # not within the same transaction).
            claimed_ids: set[int] = set()

            for tech in techs:
                label = tech.name

                # Skip workers who are still in transit between stations.
                if tech.busy_until is not None and tech.busy_until > now:
                    continue

                batch_size = max(1, _int(tech.speed))
                current = tech.current_station or StationName.triage

                if current == StationName.triage:
                    # Try to advance QT → QV1
                    qt_filter = db.query(Refill.id).filter(Refill.state == RxState.QT)
                    if claimed_ids:
                        qt_filter = qt_filter.filter(~Refill.id.in_(claimed_ids))
                    _qt_ids = [r[0] for r in (
                        qt_filter
                        .with_for_update(skip_locked=True)
                        .limit(batch_size)
                        .all()
                    )]
                    qt_batch = db.query(Refill).filter(Refill.id.in_(_qt_ids)).all() if _qt_ids else []
                    if qt_batch:
                        claimed_ids.update(_int(rx.id) for rx in qt_batch)
                        for rx in qt_batch:
                            rx.state = RxState.QV1  # type: ignore[assignment]
                            audit_rows.append({
                                "timestamp": now,
                                "action": "SIM_TECH_ACTION",
                                "entity_type": "refill",
                                "entity_id": _int(rx.id),
                                "prescription_id": _int(rx.prescription_id),
                                "details": f"{label} [triage]: QT → QV1",
                                "user_id": None,
                                "performed_by": _SIM_PERFORMER,
                            })
                            qt_advanced += 1
                        tech.current_refill_id = qt_batch[-1].id  # type: ignore[assignment]
                        work_secs = random.randint(6, 9)
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.busy_until = now + timedelta(seconds=work_secs)  # type: ignore[assignment]
                    elif qp_count > 0:
                        # Nothing to do at triage — walk to the fill station.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.fill  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: triage → fill ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1
                    elif ready_count > 0:
                        # Nothing at triage or fill — help at the dispensing window.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.window  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: triage → window ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1

                elif current == StationName.fill:
                    # Try to advance QP → QV2
                    qp_filter = db.query(Refill.id).filter(Refill.state == RxState.QP)
                    if claimed_ids:
                        qp_filter = qp_filter.filter(~Refill.id.in_(claimed_ids))
                    _qp_ids = [r[0] for r in (
                        qp_filter
                        .with_for_update(skip_locked=True)
                        .limit(batch_size)
                        .all()
                    )]
                    qp_batch = db.query(Refill).filter(Refill.id.in_(_qp_ids)).all() if _qp_ids else []
                    if qp_batch:
                        claimed_ids.update(_int(rx.id) for rx in qp_batch)
                        for rx in qp_batch:
                            rx.state = RxState.QV2  # type: ignore[assignment]
                            audit_rows.append({
                                "timestamp": now,
                                "action": "SIM_TECH_ACTION",
                                "entity_type": "refill",
                                "entity_id": _int(rx.id),
                                "prescription_id": _int(rx.prescription_id),
                                "details": f"{label} [fill]: QP → QV2",
                                "user_id": None,
                                "performed_by": _SIM_PERFORMER,
                            })
                            qp_advanced += 1
                        tech.current_refill_id = qp_batch[-1].id  # type: ignore[assignment]
                        work_secs = random.randint(6, 9)
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.busy_until = now + timedelta(seconds=work_secs)  # type: ignore[assignment]
                    elif qt_count > 0:
                        # Nothing to do at fill — walk back to triage.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.triage  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: fill → triage ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1
                    elif ready_count > 0:
                        # Nothing at fill or triage — help at the dispensing window.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.window  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: fill → window ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1

                elif current == StationName.window:
                    # Dispense READY → SOLD at the pickup window.
                    ready_filter = db.query(Refill.id).filter(
                        Refill.state == RxState.READY,
                        Refill.completed_date <= today,
                    )
                    if claimed_ids:
                        ready_filter = ready_filter.filter(~Refill.id.in_(claimed_ids))
                    _ready_ids = [r[0] for r in (
                        ready_filter
                        .with_for_update(skip_locked=True)
                        .limit(batch_size)
                        .all()
                    )]
                    ready_batch = db.query(Refill).filter(Refill.id.in_(_ready_ids)).all() if _ready_ids else []
                    if ready_batch:
                        claimed_ids.update(_int(rx.id) for rx in ready_batch)
                        for rx in ready_batch:
                            rx.state = RxState.SOLD  # type: ignore[assignment]
                            hist = RefillHist(
                                prescription_id=rx.prescription_id,
                                patient_id=rx.patient_id,
                                drug_id=rx.drug_id,
                                quantity=_int(rx.quantity),
                                days_supply=_int(rx.days_supply),
                                completed_date=rx.completed_date or today,
                                sold_date=today,
                                total_cost=Decimal(str(rx.total_cost)),
                                insurance_id=rx.insurance_id,
                                copay_amount=(
                                    Decimal(str(rx.copay_amount)) if rx.copay_amount is not None else None
                                ),
                                insurance_paid=(
                                    Decimal(str(rx.insurance_paid)) if rx.insurance_paid is not None else None
                                ),
                            )
                            db.add(hist)
                            audit_rows.append({
                                "timestamp": now,
                                "action": "SIM_TECH_ACTION",
                                "entity_type": "refill",
                                "entity_id": _int(rx.id),
                                "prescription_id": _int(rx.prescription_id),
                                "details": f"{label} [window]: READY → SOLD",
                                "user_id": None,
                                "performed_by": _SIM_PERFORMER,
                            })
                            ready_advanced += 1
                        tech.current_refill_id = ready_batch[-1].id  # type: ignore[assignment]
                        work_secs = random.randint(6, 9)
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.busy_until = now + timedelta(seconds=work_secs)  # type: ignore[assignment]
                    elif qt_count > 0:
                        # Window is clear — walk back to triage.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.triage  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: window → triage ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1
                    elif qp_count > 0:
                        # Window clear, no triage work — walk to fill.
                        tech.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        tech.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        tech.task_started_at = now  # type: ignore[assignment]
                        tech.current_station = StationName.fill  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": tech.id,
                            "prescription_id": None,
                            "details": f"{label}: window → fill ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        traveling += 1

            if audit_rows:
                db.execute(insert(AuditLog), audit_rows)
            db.commit()
            total = qt_advanced + qp_advanced + ready_advanced
            if total:
                _invalidate_queue_cache()
            if total or traveling:
                logger.info(
                    "simulate_technician: %d tech(s), advanced %d refill(s) "
                    "(%d QT→QV1, %d QP→QV2, %d READY→SOLD), %d traveling",
                    len(techs), total, qt_advanced, qp_advanced, ready_advanced, traveling,
                )
            return {
                "advanced": total,
                "qt_to_qv1": qt_advanced,
                "qp_to_qv2": qp_advanced,
                "ready_to_sold": ready_advanced,
                "traveling": traveling,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in simulate_technician task")
        raise self.retry(exc=exc, countdown=60)
    finally:
        _release_lock(lock_key)


@shared_task(name="app.tasks.simulate_pharmacist", bind=True, max_retries=3)
def simulate_pharmacist(self: Any) -> dict:  # type: ignore[type-arg]
    """Virtual pharmacists work the QV1 and QV2 verification queues.

    Each active SimWorker with role=pharmacist processes up to `speed` refills
    per queue per cycle.
    QV1: ~(100 - sim_reject_rate)% approve → QP; remainder return to QT with rejection reason.
    QV2: ~90% approve → READY (with bin); ~10% send back to QP for re-check.
    """
    lock_key = "lock:simulate_pharmacist"
    if not _acquire_lock(lock_key):
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            cfg = _sim_get_config(db)
            if not cfg or not cfg.simulation_enabled:
                return {"skipped": True}

            pharmacists = (
                db.query(SimWorker)
                .filter(SimWorker.role == SimWorkerRole.pharmacist, SimWorker.is_active.is_(True))
                .all()
            )
            if not pharmacists:
                return {"skipped": True, "reason": "no active pharmacists"}

            reject_rate = _int(cfg.sim_reject_rate) / 100.0
            bin_count = _int(cfg.bin_count) or 100
            now = datetime.now(timezone.utc)
            audit_rows: list[dict] = []
            approved_qv1 = 0
            rejected_qv1 = 0
            approved_qv2 = 0
            returned_qv2 = 0

            # Snapshot queue depths for travel decisions.
            qv1_count = db.query(func.count(Refill.id)).filter(Refill.state == RxState.QV1).scalar() or 0
            qv2_count = db.query(func.count(Refill.id)).filter(Refill.state == RxState.QV2).scalar() or 0
            pharm_traveling = 0

            # Track IDs claimed this cycle to prevent two pharmacists at the same
            # station from processing the same refill within the same transaction.
            pharm_claimed_ids: set[int] = set()

            for pharm in pharmacists:
                label = pharm.name

                # Skip pharmacists who are still walking between stations.
                if pharm.busy_until is not None and pharm.busy_until > now:
                    continue

                batch_size = max(1, _int(pharm.speed))
                current = pharm.current_station or StationName.verify_1

                if current == StationName.verify_1:
                    # QV1: pharmacist first verification
                    qv1_filter = db.query(Refill.id).filter(Refill.state == RxState.QV1)
                    if pharm_claimed_ids:
                        qv1_filter = qv1_filter.filter(~Refill.id.in_(pharm_claimed_ids))
                    _qv1_ids = [r[0] for r in (
                        qv1_filter
                        .with_for_update(skip_locked=True)
                        .limit(batch_size)
                        .all()
                    )]
                    qv1_batch = db.query(Refill).filter(Refill.id.in_(_qv1_ids)).all() if _qv1_ids else []
                    if qv1_batch:
                        pharm_claimed_ids.update(_int(rx.id) for rx in qv1_batch)
                        for rx in qv1_batch:
                            if random.random() < reject_rate:
                                reason = random.choice(_SIM_REJECTION_REASONS)
                                rx.state = RxState.QT  # type: ignore[assignment]
                                rx.rejected_by = label  # type: ignore[assignment]
                                rx.rejection_reason = reason  # type: ignore[assignment]
                                rx.rejection_date = date.today()  # type: ignore[assignment]
                                rx.triage_reason = f"Pharmacist rejected: {reason}"  # type: ignore[assignment]
                                detail = f"{label} [verify_1]: QV1 → QT (rejected — {reason})"
                                rejected_qv1 += 1
                            else:
                                rx.state = RxState.QP  # type: ignore[assignment]
                                detail = f"{label} [verify_1]: QV1 → QP (approved)"
                                approved_qv1 += 1
                            audit_rows.append({
                                "timestamp": now,
                                "action": "SIM_PHARM_ACTION",
                                "entity_type": "refill",
                                "entity_id": _int(rx.id),
                                "prescription_id": _int(rx.prescription_id),
                                "details": detail,
                                "user_id": None,
                                "performed_by": _SIM_PERFORMER,
                            })
                        pharm.current_refill_id = qv1_batch[-1].id  # type: ignore[assignment]
                        work_secs = random.randint(6, 9)
                        pharm.task_started_at = now  # type: ignore[assignment]
                        pharm.busy_until = now + timedelta(seconds=work_secs)  # type: ignore[assignment]
                    elif qv2_count > 0:
                        pharm.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        pharm.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        pharm.task_started_at = now  # type: ignore[assignment]
                        pharm.current_station = StationName.verify_2  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": pharm.id,
                            "prescription_id": None,
                            "details": f"{label}: verify_1 → verify_2 ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        pharm_traveling += 1

                elif current == StationName.verify_2:
                    # QV2: pharmacist final verification (lower rejection rate)
                    qv2_filter = db.query(Refill.id).filter(Refill.state == RxState.QV2)
                    if pharm_claimed_ids:
                        qv2_filter = qv2_filter.filter(~Refill.id.in_(pharm_claimed_ids))
                    _qv2_ids = [r[0] for r in (
                        qv2_filter
                        .with_for_update(skip_locked=True)
                        .limit(batch_size)
                        .all()
                    )]
                    qv2_batch = db.query(Refill).filter(Refill.id.in_(_qv2_ids)).all() if _qv2_ids else []
                    if qv2_batch:
                        pharm_claimed_ids.update(_int(rx.id) for rx in qv2_batch)
                        for rx in qv2_batch:
                            if random.random() < 0.10:
                                rx.state = RxState.QP  # type: ignore[assignment]
                                detail = f"{label} [verify_2]: QV2 → QP (sent back for re-check)"
                                returned_qv2 += 1
                            else:
                                rx.state = RxState.READY  # type: ignore[assignment]
                                rx.completed_date = date.today()  # type: ignore[assignment]
                                rx.bin_number = _sim_assign_bin(db, bin_count)  # type: ignore[assignment]
                                detail = f"{label} [verify_2]: QV2 → READY (bin {rx.bin_number})"
                                approved_qv2 += 1
                            audit_rows.append({
                                "timestamp": now,
                                "action": "SIM_PHARM_ACTION",
                                "entity_type": "refill",
                                "entity_id": _int(rx.id),
                                "prescription_id": _int(rx.prescription_id),
                                "details": detail,
                                "user_id": None,
                                "performed_by": _SIM_PERFORMER,
                            })
                        pharm.current_refill_id = qv2_batch[-1].id  # type: ignore[assignment]
                        work_secs = random.randint(6, 9)
                        pharm.task_started_at = now  # type: ignore[assignment]
                        pharm.busy_until = now + timedelta(seconds=work_secs)  # type: ignore[assignment]
                    elif qv1_count > 0:
                        pharm.current_refill_id = None  # type: ignore[assignment]
                        travel_secs = random.randint(5, 10)
                        pharm.busy_until = now + timedelta(seconds=travel_secs)  # type: ignore[assignment]
                        pharm.task_started_at = now  # type: ignore[assignment]
                        pharm.current_station = StationName.verify_1  # type: ignore[assignment]
                        audit_rows.append({
                            "timestamp": now,
                            "action": "SIM_WORKER_TRAVEL",
                            "entity_type": None,
                            "entity_id": pharm.id,
                            "prescription_id": None,
                            "details": f"{label}: verify_2 → verify_1 ({travel_secs}s travel)",
                            "user_id": None,
                            "performed_by": _SIM_PERFORMER,
                        })
                        pharm_traveling += 1

            if audit_rows:
                db.execute(insert(AuditLog), audit_rows)
            db.commit()
            total = approved_qv1 + rejected_qv1 + approved_qv2 + returned_qv2
            if total:
                _invalidate_queue_cache()
            if total or pharm_traveling:
                logger.info(
                    "simulate_pharmacist: %d pharmacist(s), %d action(s) "
                    "(QV1: %d approved, %d rejected | QV2: %d approved, %d returned), %d traveling",
                    len(pharmacists), total, approved_qv1, rejected_qv1, approved_qv2, returned_qv2,
                    pharm_traveling,
                )
            return {
                "total": total,
                "qv1_approved": approved_qv1,
                "qv1_rejected": rejected_qv1,
                "qv2_approved": approved_qv2,
                "qv2_returned": returned_qv2,
                "traveling": pharm_traveling,
            }
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in simulate_pharmacist task")
        raise self.retry(exc=exc, countdown=60)
    finally:
        _release_lock(lock_key)


@shared_task(name="app.tasks.simulate_patient_pickups", bind=True, max_retries=3)
def simulate_patient_pickups(self: Any) -> dict:  # type: ignore[type-arg]
    """Virtual patients pick up READY prescriptions from the bin shelf.

    Processes READY refills (completed today or earlier) with a 70% pickup
    probability per cycle to give a natural, staggered pickup pattern.
    Each sold refill is archived to RefillHist.
    """
    lock_key = "lock:simulate_patient_pickups"
    if not _acquire_lock(lock_key):
        return {"skipped": True}

    try:
        db = SessionLocal()
        try:
            cfg = _sim_get_config(db)
            if not cfg or not cfg.simulation_enabled:
                return {"skipped": True}

            today = date.today()
            now = datetime.now(timezone.utc)
            audit_rows: list[dict] = []
            sold = 0

            _ready_ids = [r[0] for r in (
                db.query(Refill.id)
                .filter(
                    Refill.state == RxState.READY,
                    Refill.completed_date <= today,
                )
                .with_for_update(skip_locked=True)
                .limit(_SIM_BATCH)
                .all()
            )]
            ready_batch = db.query(Refill).filter(Refill.id.in_(_ready_ids)).all() if _ready_ids else []

            for rx in ready_batch:
                # 70% chance patient actually shows up this cycle
                if random.random() > 0.70:
                    continue

                rx_quantity = _int(rx.quantity)
                rx_days_supply = _int(rx.days_supply)

                rx.state = RxState.SOLD  # type: ignore[assignment]

                hist = RefillHist(
                    prescription_id=rx.prescription_id,
                    patient_id=rx.patient_id,
                    drug_id=rx.drug_id,
                    quantity=rx_quantity,
                    days_supply=rx_days_supply,
                    completed_date=rx.completed_date or today,
                    sold_date=today,
                    total_cost=Decimal(str(rx.total_cost)),
                    insurance_id=rx.insurance_id,
                    copay_amount=(
                        Decimal(str(rx.copay_amount)) if rx.copay_amount is not None else None
                    ),
                    insurance_paid=(
                        Decimal(str(rx.insurance_paid)) if rx.insurance_paid is not None else None
                    ),
                )
                db.add(hist)

                audit_rows.append({
                    "timestamp": now,
                    "action": "SIM_PATIENT_PICKUP",
                    "entity_type": "refill",
                    "entity_id": _int(rx.id),
                    "prescription_id": _int(rx.prescription_id),
                    "details": (
                        f"virtual patient pickup: READY → SOLD "
                        f"drug_id={rx.drug_id} qty={rx_quantity}"
                    ),
                    "user_id": None,
                    "performed_by": _SIM_PERFORMER,
                })
                sold += 1

            if audit_rows:
                db.execute(insert(AuditLog), audit_rows)
            db.commit()
            if sold:
                _invalidate_queue_cache()
                logger.info("simulate_patient_pickups: sold %d refill(s)", sold)
            return {"sold": sold}
        finally:
            db.close()
    except Exception as exc:
        logger.exception("Error in simulate_patient_pickups task")
        raise self.retry(exc=exc, countdown=60)
    finally:
        _release_lock(lock_key)
