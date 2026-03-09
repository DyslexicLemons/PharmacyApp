"""
Pharmacy API — main application entry point.

This file is intentionally thin: it configures middleware, mounts routers,
and provides the health-check endpoints. All business logic lives in routers/.
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .database import Base, engine
from .routers import admin, auth, drugs, insurance, patients, prescriptions, prescribers, refills

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
# App and middleware
# ---------------------------------------------------------------------------

app = FastAPI(title="Pharmacy API", version="1.0.0")

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
