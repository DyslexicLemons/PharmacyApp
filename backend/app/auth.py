"""
JWT authentication utilities for the Pharmacy API.

Provides:
- create_access_token(user)   — sign an 8-hour JWT for a User
- get_current_user(...)       — Bearer-token dependency; returns User or raises 401
- require_admin(...)          — raises 403 if user role != "admin"
- require_pharmacist(...)     — raises 403 if user role is "technician"
                                (pharmacist AND admin both pass)
- create_client_token(client) — sign a 15-minute JWT for an ERxClient (external clinic)
- get_current_client(...)     — Bearer-token dependency; returns ERxClient or raises 401

User tokens and client tokens share JWT_SECRET_KEY but carry a "token_type" claim
("user" vs "client") so neither dependency will ever accept the other's token,
even though both are signed with the same key.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import ERxClient, User

# JWT configuration — no fallback; missing env var raises KeyError at startup
SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8
CLIENT_TOKEN_EXPIRE_MINUTES = 15

# auto_error=False so we can raise a consistent 401 instead of FastAPI's default 403
_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    """Return a signed JWT encoding the user's id, username, admin flag, and role."""
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": user.is_admin,
        "role": user.role,
        "token_type": "user",
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validate Bearer JWT, return the authenticated User.
    Raises 401 for missing/invalid/expired tokens, or tokens issued for a
    different purpose (e.g. an external clinic's client-credentials token).
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # Tokens issued before this claim existed have no "token_type" — treat as "user".
    if payload.get("token_type") not in (None, "user"):
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.get(User, int(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def create_client_token(client: ERxClient) -> str:
    """Return a signed, short-lived JWT for an external clinic's ERxClient."""
    payload = {
        "sub": str(client.id),
        "client_id": client.client_id,
        "clinic_name": client.clinic_name,
        "token_type": "client",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=CLIENT_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_client(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> ERxClient:
    """
    FastAPI dependency: validate a clinic's Bearer JWT, return the ERxClient.
    Raises 401 for missing/invalid/expired tokens, inactive clients, or
    tokens issued for a different purpose (e.g. a staff login token).
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    if payload.get("token_type") != "client":
        raise HTTPException(status_code=401, detail="Invalid token type")

    client_id_str = payload.get("sub")
    if not client_id_str:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    client = db.get(ERxClient, int(client_id_str))
    if not client or not client.is_active:
        raise HTTPException(status_code=401, detail="Client not found or inactive")
    return client


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: require an authenticated admin user.
    Composes on top of get_current_user — always validates the token first.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def require_pharmacist(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: require a pharmacist or admin user.
    Technicians receive 403. Admins always pass (they can perform any action).
    """
    role = getattr(current_user, "role", None) or ""
    if role not in ("pharmacist", "admin"):
        raise HTTPException(status_code=403, detail="Pharmacist access required")
    return current_user
