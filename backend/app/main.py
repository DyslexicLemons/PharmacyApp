"""
Pharmacy API — main application entry point.

This file is intentionally thin: it configures middleware, mounts routers,
and provides the health-check endpoints. All business logic lives in routers/.
"""

# Load secrets from AWS Secrets Manager before any other module reads env vars.
# In local dev / CI this is a no-op (AWS_SECRET_NAME is not set).
from .secrets import load_aws_secrets
load_aws_secrets()

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .cache import close_redis, init_redis
from .database import Base, engine, SessionLocal
from .models import Prescription, Refill, RxState
from .routers import admin, auth, billing, drugs, insurance, patients, prescriptions, prescribers, refills
from .utils import _int, _write_audit

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pharmacy.rx")

# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------------------------------
# Background task: auto-expire prescriptions
# ---------------------------------------------------------------------------

async def _promote_scheduled_refills_task() -> None:
    """
    Runs daily at 3 AM. Finds all SCHEDULED refills whose due_date is today
    or in the past and moves them to QT (Queue Triage) so they enter the
    active fill workflow.
    """
    while True:
        now = datetime.now()
        next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if next_3am <= now:
            next_3am += timedelta(days=1)
        await asyncio.sleep((next_3am - now).total_seconds())

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
                    .all()
                )
                for refill in due:
                    refill.state = RxState.QT  # type: ignore[assignment]
                    _write_audit(
                        db,
                        "REFILL_AUTO_QUEUED",
                        entity_type="refill",
                        entity_id=_int(refill.id),
                        prescription_id=_int(refill.prescription_id),
                        details=f"auto-promoted from SCHEDULED to QT: due_date={refill.due_date}",
                    )
                if due:
                    db.commit()
                    logger.info("Auto-queued %d scheduled refill(s) into QT", len(due))
            finally:
                db.close()
        except Exception:
            logger.exception("Error in scheduled refill promotion task")


async def _expire_prescriptions_task() -> None:
    """
    Runs at startup and then every 24 hours. Marks any active prescription
    whose expiration_date is in the past as inactive and writes an audit entry.
    """
    while True:
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
            finally:
                db.close()
        except Exception:
            logger.exception("Error in prescription expiration task")

        await asyncio.sleep(86400)  # 24 hours


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    init_redis()
    expire_task = asyncio.create_task(_expire_prescriptions_task())
    schedule_task = asyncio.create_task(_promote_scheduled_refills_task())
    yield
    for t in (expire_task, schedule_task):
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
    close_redis()


# ---------------------------------------------------------------------------
# App and middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="Pharmacy API", version="1.0.0", lifespan=lifespan)

# CORS — restrict to known origins via env var
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (login endpoints apply @limiter.limit in the router)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Static file serving for prescription images
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.environ.get(
    "UPLOAD_DIR",
    os.path.normpath(os.path.join(_BASE_DIR, "..", "..", "uploads")),
)
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

# Global exception handler — hides internal details from clients
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})

# ---------------------------------------------------------------------------
# Routers (all under /api/v1 prefix)
# ---------------------------------------------------------------------------

API_PREFIX = "/api/v1"
app.include_router(auth.router,          prefix=API_PREFIX)
app.include_router(patients.router,      prefix=API_PREFIX)
app.include_router(prescriptions.router, prefix=API_PREFIX)
app.include_router(refills.router,       prefix=API_PREFIX)
app.include_router(drugs.router,         prefix=API_PREFIX)
app.include_router(prescribers.router,   prefix=API_PREFIX)
app.include_router(insurance.router,     prefix=API_PREFIX)
app.include_router(billing.router,       prefix=API_PREFIX)
app.include_router(admin.router,         prefix=API_PREFIX)

# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------

@app.get("/")
def read_root():
    return {"message": "Pharmacy API running. Visit /docs for Swagger UI.", "version": "1.0.0"}


@app.get("/health")
def health():
    from datetime import datetime, timezone
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}
