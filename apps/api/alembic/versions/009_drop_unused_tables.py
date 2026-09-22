"""Drop two tables nothing reads: notification_preferences and api_keys.

Revision ID: 009
Revises: 008
Create Date: 2026-09-22

Both were in the original design and neither was ever mapped or read. The seed
filled `notification_preferences` with rows no code looked at, and `api_keys`
was empty everywhere. A table that exists but is not used is a promise the
code does not keep, so they go. `db/schema.sql` no longer declares them.

The downgrade recreates both exactly as schema.sql used to, so the chain still
walks back to the baseline.
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_preferences")
    op.execute("DROP TABLE IF EXISTS api_keys")


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS api_keys (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            key_hash     VARCHAR(255) NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at   TIMESTAMPTZ,
            CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_tenant_id ON api_keys(tenant_id)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_preferences (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_type   notification_type NOT NULL,
            email_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
            in_app_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
            CONSTRAINT uq_notification_preferences_user_type UNIQUE (user_id, notification_type)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_notification_preferences_user_id "
        "ON notification_preferences(user_id)"
    )
