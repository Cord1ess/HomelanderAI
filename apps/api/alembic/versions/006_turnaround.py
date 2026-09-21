"""Tell the applicant when to expect an answer.

Revision ID: 006
Revises: 005
Create Date: 2026-09-22

A per-carrier default in working days, and a date on each application that is
set from it at submit and revisable by an underwriter with a reason.

Existing applications are left with no expected date rather than a back-dated
guess: an estimate nobody made at the time is not something to show a client.

`db/schema.sql` declares all of this, so a fresh database already has it.
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE tenants ADD COLUMN IF NOT EXISTS turnaround_business_days "
        "INTEGER NOT NULL DEFAULT 2"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tenants_turnaround_business_days_check') THEN "
        "ALTER TABLE tenants ADD CONSTRAINT tenants_turnaround_business_days_check "
        "CHECK (turnaround_business_days BETWEEN 1 AND 30); "
        "END IF; END $$"
    )
    op.execute("ALTER TABLE applications ADD COLUMN IF NOT EXISTS expected_by DATE")
    op.execute(
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS expected_by_note VARCHAR(300)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS expected_by_note")
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS expected_by")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS turnaround_business_days")
