"""
Shared utility functions used across multiple routers.
"""

import hashlib
import hmac
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .models import AuditLog, Priority


def _mask_patient_id(patient_id: int) -> str:
    """Return a short, non-reversible HMAC token for a patient ID, safe to log.

    The same patient_id always produces the same token (allowing log correlation)
    but the token cannot be reversed to recover the ID without the LOG_SALT secret.
    """
    salt = os.environ.get("LOG_SALT", "dev-salt").encode()
    return hmac.new(salt, str(patient_id).encode(), hashlib.sha256).hexdigest()[:12]


def _int(val) -> int:  # type: ignore[no-untyped-def]
    """Safely coerce a possibly-Column SQLAlchemy value to a plain Python int."""
    return int(val) if val is not None else 0


def _parse_priority(priority_str: str) -> Priority:
    """Convert a validated priority string to Priority enum. Raises 400 on bad value."""
    try:
        return Priority[priority_str.lower()]
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority '{priority_str}'. Must be one of: low, normal, high, stat",
        )


def _write_audit(
    db: Session,
    action: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    details: Optional[str] = None,
    user_id: Optional[int] = None,
    performed_by: Optional[str] = None,
    prescription_id: Optional[int] = None,
) -> None:
    """Append a row to the audit_log table inside the current transaction (no commit)."""
    entry = AuditLog(
        timestamp=datetime.now(timezone.utc),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
        user_id=user_id,
        performed_by=performed_by,
        prescription_id=prescription_id,
    )
    db.add(entry)
