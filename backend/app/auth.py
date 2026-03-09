"""
JWT authentication utilities for the Pharmacy API.

Provides:
- create_access_token(user)  — sign an 8-hour JWT for a User
- get_current_user(...)      — Bearer-token dependency; returns User or raises 401
- require_admin(...)         — composes on top of get_current_user; raises 403 if not admin
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User

# JWT configuration — no fallback; missing env var raises KeyError at startup
SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8

# auto_error=False so we can raise a consistent 401 instead of FastAPI's default 403
_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: User) -> str:
    """Return a signed JWT encoding the user's id, username, and admin flag."""
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "is_admin": user.is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validate Bearer JWT, return the authenticated User.
    Raises 401 for missing/invalid/expired tokens.
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

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = db.get(User, int(user_id_str))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    FastAPI dependency: require an authenticated admin user.
    Composes on top of get_current_user — always validates the token first.
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
