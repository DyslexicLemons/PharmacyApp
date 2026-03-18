"""
Pharmacy API — main application entry point.

This file is intentionally thin: it configures middleware, mounts routers,
and provides the health-check endpoints. All business logic lives in routers/.
"""

# Load secrets from AWS Secrets Manager before any other module reads env vars.
# In local dev / CI this is a no-op (AWS_SECRET_NAME is not set).
from .secrets import load_aws_secrets
load_aws_secrets()

import ipaddress
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .cache import close_redis, init_redis
from .routers import admin, auth, billing, drugs, insurance, patients, prescriptions, prescribers, refills

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pharmacy.rx")

# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    init_redis()
    yield
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

# ---------------------------------------------------------------------------
# Rate-limit key function
# ---------------------------------------------------------------------------
# Behind an ALB every request arrives from the ALB's IP, so all users would
# share one rate-limit bucket if we keyed on the TCP peer.  When ALB_TRUSTED_CIDR
# is set we trust X-Forwarded-For — but only when the direct peer actually falls
# inside that CIDR, so a spoofed header from the public internet is ignored.
_ALB_TRUSTED_CIDR = os.environ.get("ALB_TRUSTED_CIDR", "")


def _get_client_ip(request: Request) -> str:
    """Return the real client IP, honouring X-Forwarded-For only from trusted ALB."""
    if _ALB_TRUSTED_CIDR:
        peer_ip = request.client.host if request.client else ""
        try:
            if ipaddress.ip_address(peer_ip) in ipaddress.ip_network(_ALB_TRUSTED_CIDR, strict=False):
                forwarded_for = request.headers.get("X-Forwarded-For", "")
                client_ip = forwarded_for.split(",")[0].strip()
                if client_ip:
                    return client_ip
        except ValueError:
            pass
    return get_remote_address(request)


# Rate limiting (login endpoints apply @limiter.limit in the router)
limiter = Limiter(key_func=_get_client_ip)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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
