"""Let an applicant sign in to see where their application stands.

Revision ID: 007
Revises: 006
Create Date: 2026-09-22

Applicants were deliberately not users. They still are not users of the
console; this gives them a separate, read-only sign-in with its own id and an
Argon2id-hashed password, generated at intake.

Existing applicants get no credentials: a password nobody was given is not an
account. `db/schema.sql` declares these columns, so a fresh database has them.
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS portal_id VARCHAR(20)")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS email VARCHAR(255)")
    op.execute("ALTER TABLE applicants ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_applicants_portal_id ON applicants(portal_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_applicants_portal_id")
    op.execute("ALTER TABLE applicants DROP COLUMN IF EXISTS password_hash")
    op.execute("ALTER TABLE applicants DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE applicants DROP COLUMN IF EXISTS portal_id")
