"""Redis cache client — quick-code storage and query result caching.

When REDIS_URL is set:
- Quick codes are stored with a 10-minute TTL instead of the quick_codes table.
- Hot read endpoints (refill queue, individual refills) cache results with
  short TTLs (30–60 s) and are actively invalidated on writes.

If REDIS_URL is not configured (local dev without Redis), all operations
return False / None so callers fall back to the database transparently.
"""

import json
import logging
import os
from typing import Any, Optional

import redis as _redis

logger = logging.getLogger("pharmacy.cache")

_client: Optional[_redis.Redis] = None  # type: ignore[type-arg]

_QUICK_CODE_TTL = 600  # seconds — matches the 10-minute window in the auth router


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def init_redis() -> None:
    """Connect to Redis if REDIS_URL is configured. Safe to call multiple times."""
    global _client
    url = os.environ.get("REDIS_URL")
    if not url:
        logger.info("REDIS_URL not set — quick codes will use database storage")
        return
    try:
        client = _redis.Redis.from_url(url, decode_responses=True)
        client.ping()
        _client = client
        logger.info("Redis connected: %s", url)
    except Exception as exc:
        logger.warning("Redis unavailable (%s) — falling back to database for quick codes", exc)
        _client = None


def close_redis() -> None:
    """Cleanly close the Redis connection on app shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("Redis connection closed")


def is_available() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# Quick-code operations
# ---------------------------------------------------------------------------

def store_quick_code(code: str, user_id: int) -> bool:
    """
    Write a quick code → user_id mapping with a 10-minute TTL.

    Returns True if stored in Redis, False if Redis is unavailable (caller
    should fall back to the database).
    """
    if _client is None:
        return False
    try:
        _client.setex(f"qc:{code}", _QUICK_CODE_TTL, str(user_id))
        return True
    except Exception as exc:
        logger.warning("Redis store_quick_code failed: %s", exc)
        return False


def consume_quick_code(code: str) -> Optional[int]:
    """
    Atomically read and delete a quick code from Redis.

    Returns the associated user_id if found (and the code is not yet expired),
    or None if the code is unknown/expired or Redis is unavailable.

    The get + delete is issued as a single pipeline so no other request can
    consume the same code between the two operations.
    """
    if _client is None:
        return None
    try:
        key = f"qc:{code}"
        pipe = _client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        value, _ = pipe.execute()
        if value is None:
            return None
        return int(value)
    except Exception as exc:
        logger.warning("Redis consume_quick_code failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Generic query-result cache
# ---------------------------------------------------------------------------

def cache_get(key: str) -> Optional[Any]:
    """Return a previously cached value, or None if missing / Redis unavailable."""
    if _client is None:
        return None
    try:
        raw = _client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("cache_get failed for %s: %s", key, exc)
        return None


def cache_set(key: str, data: Any, ttl: int = 60) -> None:
    """Store *data* (must be JSON-serialisable) under *key* with a TTL in seconds."""
    if _client is None:
        return
    try:
        _client.setex(key, ttl, json.dumps(data))
    except Exception as exc:
        logger.warning("cache_set failed for %s: %s", key, exc)


def cache_delete(key: str) -> None:
    """Delete a single cache key."""
    if _client is None:
        return
    try:
        _client.delete(key)
    except Exception as exc:
        logger.warning("cache_delete failed for %s: %s", key, exc)


def cache_delete_pattern(pattern: str) -> None:
    """Delete all keys matching a glob pattern (e.g. 'refills:queue:*')."""
    if _client is None:
        return
    try:
        keys = list(_client.scan_iter(pattern, count=100))
        if keys:
            _client.delete(*keys)
    except Exception as exc:
        logger.warning("cache_delete_pattern failed for %s: %s", pattern, exc)


# ---------------------------------------------------------------------------
# Prescription view locks
# ---------------------------------------------------------------------------

_LOCK_TTL = 300  # seconds — 5 minutes; clients must heartbeat every ~60 s


def acquire_prescription_lock(
    prescription_id: int, user_id: int, username: str
) -> "tuple[bool, str | None]":
    """
    Atomically acquire a view lock for a prescription.

    Returns (True, None)  — lock acquired or already owned by this user (TTL refreshed).
    Returns (False, name) — held by a different user; *name* is their username.
    Returns (True, None)  — Redis unavailable; fail open so the app stays usable.
    """
    if _client is None:
        return True, None
    key = f"rx:lock:{prescription_id}"
    value = json.dumps({"user_id": user_id, "username": username})
    try:
        acquired = _client.set(key, value, nx=True, ex=_LOCK_TTL)
        if acquired:
            return True, None
        existing = _client.get(key)
        if existing is None:
            # Key expired between our SET and GET — try once more
            acquired = _client.set(key, value, nx=True, ex=_LOCK_TTL)
            return (True, None) if acquired else (False, "another user")
        data = json.loads(existing)
        if data.get("user_id") == user_id:
            _client.expire(key, _LOCK_TTL)
            return True, None
        return False, data.get("username", "another user")
    except Exception as exc:
        logger.warning("acquire_prescription_lock failed for rx:%s: %s", prescription_id, exc)
        return True, None  # fail open


def release_prescription_lock(prescription_id: int, user_id: int) -> None:
    """Release a prescription lock only if it is owned by *user_id*."""
    if _client is None:
        return
    key = f"rx:lock:{prescription_id}"
    try:
        existing = _client.get(key)
        if existing:
            data = json.loads(existing)
            if data.get("user_id") == user_id:
                _client.delete(key)
    except Exception as exc:
        logger.warning("release_prescription_lock failed for rx:%s: %s", prescription_id, exc)


def get_prescription_lock(prescription_id: int) -> "dict | None":
    """Return lock info dict (user_id, username) or None if not locked / Redis unavailable."""
    if _client is None:
        return None
    key = f"rx:lock:{prescription_id}"
    try:
        existing = _client.get(key)
        return json.loads(existing) if existing else None
    except Exception as exc:
        logger.warning("get_prescription_lock failed for rx:%s: %s", prescription_id, exc)
        return None


def check_prescription_locked_by_other(prescription_id: int, user_id: int) -> "str | None":
    """
    Returns the locker's username if this prescription is locked by someone other
    than *user_id*, otherwise None (including when Redis is unavailable).
    """
    data = get_prescription_lock(prescription_id)
    if data and data.get("user_id") != user_id:
        return data.get("username", "another user")
    return None
