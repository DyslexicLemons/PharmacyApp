"""Authentication and user management endpoints."""

import string
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt as _bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from slowapi import Limiter
from slowapi.util import get_remote_address

from ..auth import create_access_token, require_admin
from ..database import get_db
from ..models import QuickCode, User
from .. import cache, schemas

router = APIRouter(tags=["auth"])
limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ---------------------------------------------------------------------------
# Quick code helpers — 3 uppercase letters only (26^3 = 17,576 combos)
# ---------------------------------------------------------------------------

_QUICK_CODE_ALPHABET = string.ascii_uppercase
_QUICK_CODE_LENGTH = 3


def _generate_quick_code() -> str:
    return "".join(secrets.choice(_QUICK_CODE_ALPHABET) for _ in range(_QUICK_CODE_LENGTH))


def _create_quick_code(user_id: int, db: Session) -> str:
    code = _generate_quick_code()
    if not cache.store_quick_code(code, user_id):
        # Redis unavailable — persist to database instead
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
        db.add(QuickCode(code=code, user_id=user_id, expires_at=expires_at))
        db.commit()
    return code


def _consume_quick_code(code: str, db: Session) -> "User | None":
    """
    Validate and consume a quick code, checking Redis first then the database.
    Returns the associated User, or None if the code is invalid/expired.
    """
    # --- Redis path ---
    user_id = cache.consume_quick_code(code)
    if user_id is not None:
        return db.query(User).filter(User.id == user_id, User.is_active == True).first()

    # --- Database fallback ---
    now = datetime.now(timezone.utc)
    quick_code = db.query(QuickCode).filter(
        QuickCode.code == code,
        QuickCode.used == False,
        QuickCode.expires_at > now,
    ).first()
    if not quick_code:
        return None
    quick_code.used = True
    db.commit()
    return db.query(User).filter(User.id == quick_code.user_id, User.is_active == True).first()


# ---------------------------------------------------------------------------
# Login endpoints (rate-limited in main.py via slowapi)
# ---------------------------------------------------------------------------

@router.post("/login", response_model=schemas.LoginResponse)
@limiter.limit("5/minute")
def login(request: Request, payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with username + password. Returns JWT access token and a quick code."""
    user = db.query(User).filter(User.username == payload.username, User.is_active == True).first()
    if not user or not _verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    quick_code = _create_quick_code(user.id, db)
    token = create_access_token(user)
    return schemas.LoginResponse(
        success=True,
        username=user.username,
        is_admin=user.is_admin,
        quick_code=quick_code,
        access_token=token,
    )


@router.post("/login/code", response_model=schemas.LoginResponse)
@limiter.limit("10/minute")
def login_with_code(request: Request, payload: schemas.CodeLoginRequest, db: Session = Depends(get_db)):
    """Authenticate with a 3-character quick code. Returns a new JWT and a refreshed quick code."""
    code_upper = payload.code.upper().strip()
    if len(code_upper) != _QUICK_CODE_LENGTH or not code_upper.isalpha():
        raise HTTPException(status_code=400, detail="Code must be exactly 3 letter characters")

    user = _consume_quick_code(code_upper, db)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired code")

    new_code = _create_quick_code(user.id, db)
    token = create_access_token(user)
    return schemas.LoginResponse(
        success=True,
        username=user.username,
        is_admin=user.is_admin,
        quick_code=new_code,
        access_token=token,
    )


# ---------------------------------------------------------------------------
# User management (admin-only)
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """List all active users. Requires admin JWT."""
    users = db.query(User).filter(User.is_active == True).order_by(User.username).all()
    return [{"id": u.id, "username": u.username, "is_admin": u.is_admin} for u in users]


@router.post("/users", status_code=201)
def create_user(
    payload: schemas.CreateUserRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Create a new user. Requires admin JWT."""
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=409, detail=f"Username '{payload.username}' already exists")
    user = User(
        username=payload.username,
        hashed_password=_hash_password(payload.password),
        is_active=True,
        is_admin=payload.is_admin,
    )
    db.add(user)
    db.commit()
    return {"success": True, "id": user.id, "username": user.username, "is_admin": user.is_admin}
