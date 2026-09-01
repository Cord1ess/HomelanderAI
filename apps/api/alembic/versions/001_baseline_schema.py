"""Baseline schema.

Revision ID: 001
Revises:
Create Date: 2026-09-01

This runs `db/schema.sql` as-is instead of repeating it as Alembic operations.

That file is the reviewed description of the database — all 15 tables, the enum
types, the indexes, the append-only triggers on audit_log, and the row-level
security that keeps one company from reading another's rows. Rewriting it by
hand here would mean two descriptions of the same database, and they had already
drifted apart: an earlier version of this migration created 5 tables out of 15,
had no row-level security, and was missing the `is_active` column that
`db/seed.sql` writes to, so seeding failed.

One file, run directly, cannot drift.
"""

from pathlib import Path

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

# apps/api/alembic/versions/ -> apps/api/alembic -> apps/api -> apps -> repo root
SCHEMA_FILE = Path(__file__).resolve().parents[4] / "db" / "schema.sql"

# Dropping the types requires the tables to be gone first, so this order matters.
TABLES = [
    "notification_preferences",
    "notifications",
    "audit_log",
    "underwriter_decisions",
    "composite_scores",
    "explanation_artifacts",
    "sub_scores",
    "model_runs",
    "model_arms",
    "evidence_files",
    "applications",
    "applicants",
    "api_keys",
    "users",
    "tenants",
]

ENUMS = [
    "notification_status",
    "notification_channel",
    "notification_type",
    "underwriter_decision_type",
    "risk_tier",
    "explanation_artifact_type",
    "model_run_status",
    "model_arm_type",
    "evidence_file_type",
    "application_status",
    "user_role",
]


def upgrade() -> None:
    if not SCHEMA_FILE.exists():
        raise FileNotFoundError(
            f"Cannot find {SCHEMA_FILE}. The migration reads the schema from the "
            "repository, so it must be run from a full checkout."
        )
    op.execute(SCHEMA_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    for enum in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum}")
    op.execute("DROP SEQUENCE IF EXISTS applicants_ref_seq")
    op.execute("DROP FUNCTION IF EXISTS audit_log_is_append_only() CASCADE")
