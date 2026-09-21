"""Let an underwriter ask for specific documents without spending the decision.

Revision ID: 005
Revises: 004
Create Date: 2026-09-22

`underwriter_decisions` is write-once. If "request more evidence" were recorded
there, the application would be decided forever the moment a document was asked
for, and nothing could be decided once it arrived. So a request is its own row
and its own status, and the decision stays open.

`db/schema.sql` declares all of this, so a fresh database already has it.
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD VALUE cannot run inside the migration's transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE application_status ADD VALUE IF NOT EXISTS "
            "'awaiting_evidence' AFTER 'insufficient_evidence'"
        )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS requested_documents (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
            requested_by     UUID REFERENCES users(id) ON DELETE RESTRICT,
            description      VARCHAR(300) NOT NULL,
            requested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            fulfilled_at     TIMESTAMPTZ,
            fulfilled_by     UUID REFERENCES evidence_files(id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_requested_documents_tenant_id "
        "ON requested_documents(tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_requested_documents_application_id "
        "ON requested_documents(application_id)"
    )
    # Same isolation policy as every other tenant-owned table.
    op.execute("ALTER TABLE requested_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE requested_documents FORCE ROW LEVEL SECURITY")
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'requested_documents') THEN "
        "CREATE POLICY tenant_isolation ON requested_documents "
        "USING (tenant_id = current_setting('app.tenant_id', true)::uuid); "
        "END IF; END $$"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS requested_documents")
    # Postgres cannot remove an enum value; rows are moved off it instead.
    op.execute(
        "UPDATE applications SET status = 'scored' WHERE status = 'awaiting_evidence'"
    )
