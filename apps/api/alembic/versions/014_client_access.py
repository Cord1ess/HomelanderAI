"""Client details are asked for, with a reason; clients upload what is asked of them.

Revision ID: 014
Revises: 013
Create Date: 2026-10-03

An underwriter or a doctor no longer sees a client's personal details by
default. They ask, with a reason (`client_access_requests`), and an
administrator approves or declines. Three notification types go with it: a
request made, a request answered, and a client uploading a requested document
from their portal.

Everything is IF NOT EXISTS: `db/schema.sql` declares the same objects, so a
database built from scratch already has them.
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'access_requested'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'access_decided'")
        op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'documents_uploaded'")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS client_access_requests (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            applicant_id    UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
            requester_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            reason          TEXT NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending', 'approved', 'declined')),
            decided_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at      TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_access_requests_tenant "
        "ON client_access_requests(tenant_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_client_access_requests_requester "
        "ON client_access_requests(requester_id, applicant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS client_access_requests")
    # Enum values cannot be removed in PostgreSQL; the three new ones stay, unused.
