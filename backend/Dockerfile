# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# libpq-dev + gcc needed to compile psycopg2 from source
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update \
    && apt-get install -y --no-install-recommends libpq-dev gcc curl postgresql-client

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY app/ ./app/
COPY migrations/ ./migrations/
COPY alembic/ ./alembic/
COPY alembic.ini .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
