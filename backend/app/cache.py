"""Redis cache client — used for quick-code storage and future caching needs.

When REDIS_URL is set, quick codes are stored in Redis with a 10-minute TTL
instead of the `quick_codes` database table. This removes write load from
Postgres for transient data and gives sub-millisecond lookups.

If REDIS_URL is not configured (local dev without Redis), all operations
return False / None so callers fall back to the database transparently.
"""

import logging
import os
from typing import Optional

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
