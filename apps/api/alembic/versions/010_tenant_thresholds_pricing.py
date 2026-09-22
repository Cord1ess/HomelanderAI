"""Per-company risk-score boundaries and pricing policy, with a change log.

Revision ID: 010
Revises: 009
Create Date: 2026-09-22

The tier cut-points (30 / 65) and the plan premiums (5,000 / 7,500 per
1,000,000 of cover) were constants in code. They are now columns on `tenants`,
set by the company's administrator, with the constants as defaults so nothing
changes for an existing company until someone changes it.

Every score already snapshots the thresholds it was tiered with, so a change
here affects new scores only; that was agreed on 2026-09-22.

`tenant_settings_changes` records who changed what and from what. It is a
separate table because `audit_log` is hash-chained per application and a
company setting belongs to no application.
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenants
            ADD COLUMN IF NOT EXISTS tier_low_max NUMERIC(5,2) NOT NULL DEFAULT 30.00,
            ADD COLUMN IF NOT EXISTS tier_moderate_max NUMERIC(5,2) NOT NULL DEFAULT 65.00,
            ADD COLUMN IF NOT EXISTS premium_low_bdt NUMERIC(12,2) NOT NULL DEFAULT 5000.00,
            ADD COLUMN IF NOT EXISTS premium_moderate_bdt NUMERIC(12,2) NOT NULL DEFAULT 7500.00,
            ADD COLUMN IF NOT EXISTS reference_cover_bdt NUMERIC(14,2) NOT NULL DEFAULT 1000000.00
        """
    )
    for name, check in (
        ("ck_tenants_tier_low_max", "tier_low_max > 0 AND tier_low_max < 100"),
        ("ck_tenants_tier_moderate_max", "tier_moderate_max > 0 AND tier_moderate_max < 100"),
        ("ck_tenants_tier_order", "tier_low_max < tier_moderate_max"),
        ("ck_tenants_premium_low", "premium_low_bdt > 0"),
        ("ck_tenants_premium_moderate", "premium_moderate_bdt > 0"),
        ("ck_tenants_reference_cover", "reference_cover_bdt > 0"),
    ):
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
                    ALTER TABLE tenants ADD CONSTRAINT {name} CHECK ({check});
                END IF;
            END $$;
            """
        )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_settings_changes (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            changes       JSONB NOT NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tenant_settings_changes_tenant "
        "ON tenant_settings_changes(tenant_id, changed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tenant_settings_changes")
    for name in (
        "ck_tenants_tier_low_max",
        "ck_tenants_tier_moderate_max",
        "ck_tenants_tier_order",
        "ck_tenants_premium_low",
        "ck_tenants_premium_moderate",
        "ck_tenants_reference_cover",
    ):
        op.execute(f"ALTER TABLE tenants DROP CONSTRAINT IF EXISTS {name}")
    op.execute(
        """
        ALTER TABLE tenants
            DROP COLUMN IF EXISTS tier_low_max,
            DROP COLUMN IF EXISTS tier_moderate_max,
            DROP COLUMN IF EXISTS premium_low_bdt,
            DROP COLUMN IF EXISTS premium_moderate_bdt,
            DROP COLUMN IF EXISTS reference_cover_bdt
        """
    )
