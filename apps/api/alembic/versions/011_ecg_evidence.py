"""Store a 12-lead ECG as evidence.

Revision ID: 011
Revises: 010
Create Date: 2026-09-22

A tracing exported from an ECG machine is a signal, not an image and not a
document, and `evidence_file_type` had no honest value for it. `db/schema.sql`
declares the value, so a fresh database already has it.
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE cannot run inside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE evidence_file_type ADD VALUE IF NOT EXISTS 'ecg'")


def downgrade() -> None:
    # Postgres cannot remove an enum value; rows are moved off it instead.
    op.execute("UPDATE evidence_files SET file_type = 'questionnaire' WHERE file_type = 'ecg'")
