"""Store which declared-history rules fired alongside the score.

Revision ID: 002
Revises: 001
Create Date: 2026-09-01

`db/schema.sql` now declares this column, so a database created from scratch
already has it — hence IF NOT EXISTS. This migration exists for databases
already at 001.
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE composite_scores "
        "ADD COLUMN IF NOT EXISTS adjustments JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE composite_scores DROP COLUMN IF EXISTS adjustments")
