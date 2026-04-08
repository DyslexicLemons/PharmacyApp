# PharmacyApp

A pharmacy management system for tracking patients, prescriptions, and the refill workflow from intake through dispensing.

**Stack:** FastAPI · PostgreSQL · Redis · Celery · React 18 · TypeScript · Vite

---

## Table of Contents

- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start (Docker)](#quick-start-docker)
- [Local Development (No Docker)](#local-development-no-docker)
- [Environment Variables](#environment-variables)
- [Database Migrations](#database-migrations)
- [Running Tests](#running-tests)
- [Common Operations](#common-operations)
- [Refill Workflow](#refill-workflow)
- [Deployment](#deployment)

---

## Architecture

| Service | Description | Port |
|---|---|---|
| `backend` | FastAPI REST API | 8000 |
| `frontend` | React app (Nginx in Docker, Vite locally) | 80 / 5173 |
| `postgres` | Primary database | 5432 |
| `redis` | Task queue + caching | 6379 |
| `celery-worker` | Background task workers (scalable) | — |
| `celery-beat` | Scheduled task scheduler (**single replica only**) | — |

All API routes are prefixed `/api/v1`. Interactive API docs: `http://localhost:8000/docs`

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (recommended)
- OR: Python 3.12, Node 18+, PostgreSQL 16, Redis 7

---

## Quick Start (Docker)

```bash
# 1. Copy and fill in environment variables
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set JWT_SECRET_KEY

# 2. Build and start all services
make dev

# 3. Apply database migrations
make migrate
```

The app is now running:
- Frontend: http://localhost
- API: http://localhost:8000
- API docs: http://localhost:8000/docs

On first startup the backend automatically creates a default admin account (`admin` / `admin`) if no users exist. Change the password after logging in.

**Other useful commands:**
```bash
make logs       # tail logs from all services
make down       # stop and remove containers
```

---

## Local Development (No Docker)

You'll need Postgres and Redis running locally first.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash
# or: source .venv/bin/activate      # macOS/Linux

pip install -r requirements.txt

cp .env.example .env
# Edit .env — set DATABASE_URL, REDIS_URL, JWT_SECRET_KEY

alembic upgrade head                 # apply migrations
uvicorn app.main:app --reload        # starts on port 8000
```

In separate terminals, start the Celery workers:
```bash
celery -A app.celery_app worker --loglevel=info
celery -A app.celery_app beat --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev                          # starts on port 5173
```

---

## Environment Variables

All variables are documented in [backend/.env.example](backend/.env.example). Key ones:

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET_KEY` | Secret for signing JWTs — generate with `openssl rand -hex 32` |
| `REDIS_URL` | Redis connection string |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated), e.g. `http://localhost:5173` |
| `UPLOAD_DIR` | Directory for prescription image uploads |
| `LOG_SALT` | Salt for hashing sensitive values in audit logs |
| `LOG_RX_DEBUG` | Set `true` to enable verbose prescription logging |

Never commit `.env` files. In production, secrets come from AWS Secrets Manager.

---

## Database Migrations

Whenever a model in [backend/app/models.py](backend/app/models.py) changes, create a migration — never alter the schema directly.

```bash
cd backend

# Generate a migration (autogenerate detects model changes)
alembic revision --autogenerate -m "short_description"

# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Inside Docker
make migrate
# or: docker compose exec backend alembic upgrade head
```

Migration files live in [backend/alembic/versions/](backend/alembic/versions/).

---

## Running Tests

```bash
# Backend (run from backend/)
.venv/Scripts/python -m pytest tests/ -v

# Inside Docker
docker compose exec backend python -m pytest tests/ -v

# Frontend (run from frontend/)
npm test
npm run test:watch   # watch mode
```

CI runs backend tests against a real PostgreSQL instance — do not mock the database.

---

## Common Operations

### Access the database directly
```bash
docker compose exec postgres psql -U postgres pharmacy_db
```

### View API docs
`http://localhost:8000/docs` (Swagger UI)

### Rebuild after dependency changes
```bash
docker compose build backend
# or rebuild everything:
make dev
```

### Check service health
`GET http://localhost:8000/health` — returns Postgres and Redis status.

---

## Refill Workflow

Refills move through a state machine:

```
QT → QV1 → QP → QV2 → READY → SOLD
          ↘ HOLD ↙
          REJECTED
```

| State | Meaning |
|---|---|
| `QT` | Queue Triage — new refill, awaiting triage |
| `QV1` | Pharmacist verification #1 |
| `QP` | Queue Production — being filled by technician |
| `QV2` | Pharmacist verification #2 |
| `READY` | Ready for pickup |
| `SOLD` | Dispensed to patient |
| `HOLD` | On hold |
| `SCHEDULED` | Scheduled for future fill |
| `REJECTED` | Rejected — requires reason |

---

## Deployment

Infrastructure is managed with Terraform (see [infra/](infra/)) targeting AWS ECS Fargate.

```bash
# One-time: create S3 state bucket and DynamoDB lock table
make bootstrap-apply

# Initialize Terraform (after bootstrap)
make infra-init

# Preview changes
make infra-plan

# Apply
make infra-apply
```

The frontend deploys to S3 + CloudFront. The backend and workers run as ECS services.
See [aws/](aws/) for AWS CLI setup if needed.
