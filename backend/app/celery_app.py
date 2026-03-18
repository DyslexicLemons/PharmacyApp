"""Celery application and Beat schedule.

Uses Redis as both the broker and result backend — the same Redis instance
already used for quick-code caching.

Beat is the sole source of schedule truth and must run as exactly ONE
replica. Workers can scale freely; the Redis lock inside each task ensures
a duplicate invocation (e.g. from a mis-configured second Beat) is a no-op.

Schedule (all times UTC):
  - expire-prescriptions-daily   — 00:00 UTC
  - promote-scheduled-refills-daily — 03:00 UTC
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

celery_app = Celery(
    "pharmacy",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"],
)

celery_app.conf.update(
    enable_utc=True,
    timezone="UTC",
    task_serializer="json",
    result_expires=3600,
    beat_schedule={
        "expire-prescriptions-daily": {
            "task": "app.tasks.expire_prescriptions",
            "schedule": crontab(hour=0, minute=0),
        },
        "promote-scheduled-refills-daily": {
            "task": "app.tasks.promote_scheduled_refills",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)
