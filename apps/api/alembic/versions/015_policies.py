"""Policies, their monthly payments, an email log, and real passwords for the staff accounts.

Revision ID: 015
Revises: 014
Create Date: 2026-10-03

An approval used to end at the decision. It now issues a policy: the plan, the
monthly premium, the sum assured (what is paid out on a claim), the term, and
the dates it runs between. Each month's premium is recorded when it is paid
(`premium_payments`), so the client can see what they have paid and what is
due, and the owner can see what comes in. Only an administrator cancels one.

`email_log` records every message the platform tried to send (never the body,
which can hold a password), so a failed sign-in email can be seen and sent
again. `users.password_changed_at` lets the built-in staff accounts keep a
password they changed instead of being reset to the demo one.

Everything is IF NOT EXISTS: `db/schema.sql` declares the same objects.
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None

NEW_TYPES = ("policy_issued", "policy_cancelled")

POLICIES = """
CREATE TABLE IF NOT EXISTS policies (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id       UUID NOT NULL UNIQUE REFERENCES applications(id) ON DELETE CASCADE,
    applicant_id         UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    policy_number        VARCHAR(40) NOT NULL UNIQUE,
    plan_name            VARCHAR(100) NOT NULL,
    coverage_type        VARCHAR(50),
    sum_assured_bdt      NUMERIC(14, 2) NOT NULL,
    monthly_premium_bdt  NUMERIC(12, 2) NOT NULL,
    term_years           INTEGER NOT NULL CHECK (term_years BETWEEN 1 AND 40),
    start_date           DATE NOT NULL,
    end_date             DATE NOT NULL,
    status               VARCHAR(20) NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'cancelled')),
    cancelled_at         TIMESTAMPTZ,
    cancelled_by         UUID REFERENCES users(id) ON DELETE SET NULL,
    cancel_reason        TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

PAYMENTS = """
CREATE TABLE IF NOT EXISTS premium_payments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    policy_id       UUID NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    due_date        DATE NOT NULL,
    amount_bdt      NUMERIC(12, 2) NOT NULL,
    method          VARCHAR(30) NOT NULL DEFAULT 'cash',
    reference       VARCHAR(100),
    paid_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    recorded_by     UUID REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (policy_id, due_date)
)
"""

EMAILS = """
CREATE TABLE IF NOT EXISTS email_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id  UUID REFERENCES applications(id) ON DELETE CASCADE,
    kind            VARCHAR(40) NOT NULL,
    recipient       VARCHAR(255) NOT NULL,
    subject         VARCHAR(255) NOT NULL,
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('sent', 'not_configured', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

# Approvals recorded before policies existed get one, on the same terms the
# portal already showed: the recorded premium, or the standard rate for the
# cover asked for; the term asked for, or ten years.
BACKFILL = """
INSERT INTO policies (
    tenant_id, application_id, applicant_id, policy_number, plan_name, coverage_type,
    sum_assured_bdt, monthly_premium_bdt, term_years, start_date, end_date
)
SELECT
    a.tenant_id, a.id, a.applicant_id,
    'P-' || ap.external_ref,
    CASE WHEN d.decision = 'confirmed_fast_track' THEN 'Standard' ELSE 'Standard with adjustment' END,
    a.coverage_type,
    a.coverage_amount,
    COALESCE(
        d.final_premium,
        ROUND(t.premium_low_bdt * a.coverage_amount / t.reference_cover_bdt, 2)
    ),
    term.years,
    d.decided_at::date,
    (d.decided_at + make_interval(years => term.years))::date
FROM underwriter_decisions d
JOIN applications a ON a.id = d.application_id
JOIN applicants ap ON ap.id = a.applicant_id
JOIN tenants t ON t.id = a.tenant_id
CROSS JOIN LATERAL (
    SELECT LEAST(40, GREATEST(1, COALESCE(
        NULLIF(regexp_replace(COALESCE(a.policy_term, ''), '[^0-9]', '', 'g'), '')::int, 10
    ))) AS years
) term
WHERE d.decision IN ('confirmed_fast_track', 'approved_with_adjustment')
  AND a.coverage_amount IS NOT NULL
  AND ap.external_ref IS NOT NULL
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for value in NEW_TYPES:
            op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_changed_at TIMESTAMPTZ")
    op.execute(POLICIES)
    op.execute("CREATE INDEX IF NOT EXISTS idx_policies_tenant ON policies(tenant_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_policies_applicant ON policies(applicant_id)")
    op.execute(PAYMENTS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_premium_payments_policy "
        "ON premium_payments(policy_id, due_date)"
    )
    op.execute(EMAILS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_email_log_application "
        "ON email_log(application_id, created_at DESC)"
    )
    op.execute(BACKFILL)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS email_log")
    op.execute("DROP TABLE IF EXISTS premium_payments")
    op.execute("DROP TABLE IF EXISTS policies")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at")
