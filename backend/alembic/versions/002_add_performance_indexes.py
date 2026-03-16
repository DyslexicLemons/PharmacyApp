"""Add explicit performance indexes on high-cardinality query columns.

Columns targeted:
  - patients.last_name       — patient search by name
  - refills.state            — queue filtering (QT / QV1 / QP / QV2 / READY …)
  - audit_log.timestamp      — time-range queries on the audit trail

These indexes are already declared via index=True on the SQLAlchemy model columns
and may exist in databases created by create_all(). The migration uses
postgresql_if_not_exists / if_not_exists so it is safe to run against both
fresh and existing databases.

Revision ID: 002_perf_indexes
Revises: 001_baseline
Create Date: 2026-03-16
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "002_perf_indexes"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # patient lookups by last name (e.g. "find patient Smith")
    op.create_index(
        "ix_patients_last_name",
        "patients",
        ["last_name"],
        if_not_exists=True,
    )

    # refill queue views filter heavily on state (QT, QV1, READY …)
    op.create_index(
        "ix_refills_state",
        "refills",
        ["state"],
        if_not_exists=True,
    )

    # audit log time-range queries (e.g. "all actions in the last 7 days")
    op.create_index(
        "ix_audit_log_timestamp",
        "audit_log",
        ["timestamp"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_timestamp", table_name="audit_log", if_exists=True)
    op.drop_index("ix_refills_state", table_name="refills", if_exists=True)
    op.drop_index("ix_patients_last_name", table_name="patients", if_exists=True)
