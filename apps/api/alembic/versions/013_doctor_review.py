"""The doctor reviews results and writes to clients; they no longer decide.

Revision ID: 013
Revises: 012
Create Date: 2026-10-03

A doctor used to record the insurance decision on an escalated application.
They now do what a doctor does: say whether the readers' results are
medically right (`doctor_reviews`, which tags the application for the
underwriter) and, when something cannot wait, tell the client directly
(`client_messages`). `applications.sent_to_doctor_at` scopes what a doctor can
see to the applications sent to them.

Everything is IF NOT EXISTS: `db/schema.sql` declares the same objects, so a
database built from scratch already has them.
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'doctor_reviewed'")

    op.execute(
        "ALTER TABLE applications ADD COLUMN IF NOT EXISTS sent_to_doctor_at TIMESTAMPTZ"
    )
    # Anything already with a doctor was sent to one.
    op.execute(
        "UPDATE applications SET sent_to_doctor_at = now() "
        "WHERE status = 'escalated' AND sent_to_doctor_at IS NULL"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS doctor_reviews (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            doctor_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            verdict         VARCHAR(20) NOT NULL CHECK (verdict IN ('accurate', 'inaccurate')),
            note            TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_doctor_reviews_application "
        "ON doctor_reviews(application_id, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS client_messages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            sender_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            urgency         VARCHAR(20) NOT NULL CHECK (urgency IN ('urgent', 'routine')),
            message         TEXT NOT NULL,
            emailed         BOOLEAN NOT NULL DEFAULT false,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_messages_application "
        "ON client_messages(application_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS client_messages")
    op.execute("DROP TABLE IF EXISTS doctor_reviews")
    op.execute("ALTER TABLE applications DROP COLUMN IF EXISTS sent_to_doctor_at")
    # Enum values cannot be removed in PostgreSQL; 'doctor_reviewed' stays, unused.
