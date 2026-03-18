# PharmacyApp — Claude Instructions

## Testing

After making any code changes, always check whether existing tests need to be updated or new tests need to be created to reflect those changes. Do this as part of the same task — don't consider the work done until tests are in sync with the code.

- Backend tests: `.venv/Scripts/python -m pytest tests/ -v` (run from `backend/`)
- Frontend tests: `npm test` (run from `frontend/`)
- CI runs backend pytest against a real PostgreSQL instance — never mock the database in tests

---

## Database Migrations

Whenever a SQLAlchemy model in `backend/app/models.py` is added or changed, always create an Alembic migration. Never alter the schema directly.

**To generate:** run from `backend/`
```
alembic revision --autogenerate -m "short_description"
```

**Naming:** migrations auto-number (`001_`, `002_`, etc.) via `alembic.ini`. The `-m` slug becomes part of the filename — keep it short and descriptive (e.g., `add_insurance_table`, `add_npi_index`).

**Required in every migration:**
- A docstring explaining what changed and why
- `upgrade()` and `downgrade()` both implemented
- Use `if_not_exists=True` / `checkfirst=True` on create/drop operations for safety

**Run migrations:**
```
alembic upgrade head     # apply
alembic downgrade -1     # roll back one
```

---

## SQLAlchemy Models (`backend/app/models.py`)

- All models inherit from `Base` (imported from `database.py`)
- Always set `__tablename__` explicitly
- Use `index=True` on columns that will be filtered or joined on frequently
- Relationships: use `lazy="selectin"` for collections, `lazy="joined"` for single-object lookups
- Timestamps: always `DateTime(timezone=True)` with `default=lambda: datetime.now(timezone.utc)`
- Enums: define as a Python `Enum` class in `models.py` before the model that uses it
- After adding a model, import it in `backend/alembic/env.py` so Alembic detects it

---

## API Endpoints (Routers)

**Structure:**
- New routers go in `backend/app/routers/`
- Register them in `backend/app/main.py` with `app.include_router(...)`
- Always use dependency injection: `db: Session = Depends(get_db)` and `current_user: User = Depends(get_current_user)`
- Validate all input/output with Pydantic schemas defined in `backend/app/schemas.py`
- Use `_int()` from `utils.py` for safe int conversions from request params

**Audit logging:**
Every significant write action (create, update, state change, delete) must call:
```python
_write_audit(db, action, entity_type, entity_id, details, prescription_id, user_id)
```
Action string examples: `PRESCRIPTION_EXPIRED`, `FILL_CREATED`, `STATE_TRANSITION`, `PATIENT_CREATED`
Entity types: `"refill"`, `"prescription"`, `"patient"`

---

## Refill State Machine

The refill workflow uses a strict state machine defined in `backend/app/routers/refills.py`.

**States (`RxState` enum):** `QT → QV1 → QP → QV2 → READY → SOLD`, plus `HOLD`, `SCHEDULED`, `REJECTED`

**Valid transitions (`TRANSITIONS` dict):**
```
QT       → [QV1, HOLD]
QV1      → [QP, HOLD, REJECTED]
QP       → [QV2, HOLD]
QV2      → [READY, QP, HOLD]
HOLD     → [QP, REJECTED]
SCHEDULED→ [QP, HOLD, REJECTED]
READY    → [SOLD]
```

Always validate against `TRANSITIONS` before changing a refill's state. Never bypass it.

---

## Celery Tasks (`backend/app/tasks.py`)

**Task pattern:**
```python
@shared_task(name="app.tasks.task_name", bind=True, max_retries=3)
def my_task(self):
    if not _acquire_lock("lock:task_name"):
        return {"skipped": True}
    try:
        db = SessionLocal()
        # ... do work ...
        return {"result": count}
    except Exception as exc:
        self.retry(exc=exc, countdown=60)
    finally:
        db.close()
```

**Rules:**
- Always acquire a Redis lock (`SET NX EX 300`) before touching the DB — prevents duplicate runs during deploys
- Use `SessionLocal()` directly (workers don't go through FastAPI's `get_db`)
- Return a status dict (`{"skipped": True}` or `{"processed": N}`)
- Register new Beat tasks in `celery_app.conf.beat_schedule` in `backend/app/celery_app.py`

**Critical:** `celery-beat` must always run as exactly **one replica**. Never scale it.

---

## Environment Variables

- All env vars must be documented in `backend/.env.example` with a comment explaining purpose and how to generate if needed
- Load via `os.environ.get("VAR_NAME")` — never hardcode credentials
- In production, secrets come from AWS Secrets Manager (via `backend/app/secrets.py`) — don't add prod credentials to `.env`
- Key vars: `DATABASE_URL`, `JWT_SECRET_KEY`, `REDIS_URL`, `ALLOWED_ORIGINS`, `UPLOAD_DIR`, `AWS_SECRET_NAME`

---

## Docker

**Services:** `postgres`, `redis`, `backend`, `celery-worker`, `celery-beat`, `frontend`

To run commands inside a service:
```
docker compose exec backend <command>
docker compose exec backend alembic upgrade head
docker compose exec backend python -m pytest tests/ -v
```

Use the `.venv` path (`backend/.venv/Scripts/python`) when running locally outside Docker.

---

## AWS / Deployment

- Backend deploys to **ECS Fargate** via ECR — avoid changes that require persistent local filesystem state (use `uploads_data` volume or S3)
- Frontend deploys to **S3 + CloudFront** — all routing must work as a SPA (Nginx config handles this in Docker; CloudFront error pages handle it in prod)
- Never hardcode AWS region, bucket names, or ARNs — these come from env vars or task definition config
