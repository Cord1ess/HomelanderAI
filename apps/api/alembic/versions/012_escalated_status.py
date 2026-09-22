"""An application status for "handed to a medical professional".

Revision ID: 012
Revises: 011
Create Date: 2026-09-22

Escalating used to be recorded as the application's one write-once decision,
which meant the medical professional it was handed to could never decide it.
It is now a status the application passes through, with the decision still
open. Enum values cannot be removed in PostgreSQL, so the downgrade is a no-op;
nothing breaks by the value existing unused.
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Outside a transaction block: ADD VALUE cannot run inside one on older
    # PostgreSQL, and Alembic wraps migrations in one by default.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE application_status ADD VALUE IF NOT EXISTS 'escalated'")


def downgrade() -> None:
    pass
