"""Real products and prices, declines, claims, NID, nominees, consent and data deletion.

Revision ID: 016
Revises: 015
Create Date: 2026-10-04

* **Products.** Two: term life (level premium for 5-25 years) and hospital
  cover (a one-year policy, renewed each year). Premiums come from a pricing
  engine (`app/pricing.py`) instead of a flat illustrative rate; the company's
  pricing assumptions are new columns on `tenants`.
* **Decisions** can now decline, with a reason and a date the client may apply
  again; an approval can carry a rating (an extra percentage on the premium)
  and exclusions (conditions the policy will not pay for).
* **Policies** know their product, premium and how it is paid, the free-look
  window, and for hospital cover the waiting periods. Payments are handled by
  the bank, so `premium_payments` goes.
* **Claims**, with their documents and the 90-day settlement clock.
* **Applicants** gain the NID read from their card, a nominee, consent to
  processing, and a deletion marker; `data_deletion_requests` holds what they
  ask for. **Applications** can be taken by one underwriter.

Everything is IF NOT EXISTS: `db/schema.sql` declares the same objects.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None

NEW_NOTIFICATIONS = ("claim_filed", "claim_updated", "deletion_requested")

CLAIMS = """
CREATE TABLE IF NOT EXISTS claims (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id            UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    policy_id            UUID NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    applicant_id         UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    claim_number         VARCHAR(40) NOT NULL UNIQUE,
    claim_type           VARCHAR(20) NOT NULL CHECK (claim_type IN ('death', 'hospital')),
    event_date           DATE NOT NULL,
    claimed_amount_bdt   NUMERIC(14, 2) NOT NULL CHECK (claimed_amount_bdt > 0),
    description          TEXT NOT NULL,
    hospital             VARCHAR(200),
    claimant_name        VARCHAR(200),
    accident             BOOLEAN NOT NULL DEFAULT false,
    status               VARCHAR(30) NOT NULL DEFAULT 'submitted'
                         CHECK (status IN ('submitted', 'documents_requested', 'under_review',
                                           'approved', 'rejected', 'settled')),
    documents_note       TEXT,
    documents_complete_at TIMESTAMPTZ,
    settle_by            DATE,
    approved_amount_bdt  NUMERIC(14, 2),
    decision_note        TEXT,
    decided_by           UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at           TIMESTAMPTZ,
    settled_at           TIMESTAMPTZ,
    settlement_reference VARCHAR(100),
    filed_by_client      BOOLEAN NOT NULL DEFAULT false,
    filed_by             UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

CLAIM_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS claim_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    storage_path    VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255),
    mime_type       VARCHAR(100),
    uploaded_by_client BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

DELETIONS = """
CREATE TABLE IF NOT EXISTS data_deletion_requests (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    applicant_id    UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    reason          TEXT,
    status          VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'approved', 'declined', 'withdrawn', 'completed')),
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    delete_on       DATE NOT NULL,
    decided_by      UUID REFERENCES users(id) ON DELETE SET NULL,
    decided_at      TIMESTAMPTZ,
    decline_reason  TEXT,
    completed_at    TIMESTAMPTZ
)
"""

COLUMNS = {
    "tenants": [
        "life_expense_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 22.32",
        "life_interest_pct NUMERIC(5, 2) NOT NULL DEFAULT 5.00",
        "health_rate_per_lakh_bdt NUMERIC(10, 2) NOT NULL DEFAULT 1800",
        "smoker_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 50",
        "monthly_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 5",
    ],
    "underwriter_decisions": [
        "rating_pct INTEGER NOT NULL DEFAULT 0",
        "exclusions JSONB NOT NULL DEFAULT '[]'::jsonb",
        "decline_reason VARCHAR(40)",
        "decline_note TEXT",
        "reapply_after DATE",
    ],
    "policies": [
        "product VARCHAR(20) NOT NULL DEFAULT 'life'",
        "annual_premium_bdt NUMERIC(12, 2)",
        "premium_mode VARCHAR(10) NOT NULL DEFAULT 'monthly'",
        "rating_pct INTEGER NOT NULL DEFAULT 0",
        "exclusions JSONB NOT NULL DEFAULT '[]'::jsonb",
        "free_look_until DATE",
        "waiting_until DATE",
        "preexisting_until DATE",
    ],
    "applicants": [
        "nid_number VARCHAR(20)",
        "nid_name VARCHAR(200)",
        "nid_date_of_birth DATE",
        "nid_image_path VARCHAR(500)",
        "nominee_name VARCHAR(200)",
        "nominee_relation VARCHAR(50)",
        "nominee_phone VARCHAR(30)",
        "consent_at TIMESTAMPTZ",
        "deleted_at TIMESTAMPTZ",
    ],
    "applications": [
        "payment_mode VARCHAR(10) NOT NULL DEFAULT 'monthly'",
        "assigned_to UUID REFERENCES users(id) ON DELETE SET NULL",
        "assigned_at TIMESTAMPTZ",
    ],
}


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE underwriter_decision_type ADD VALUE IF NOT EXISTS 'declined'")
        for value in NEW_NOTIFICATIONS:
            op.execute(f"ALTER TYPE notification_type ADD VALUE IF NOT EXISTS '{value}'")

    for table, columns in COLUMNS.items():
        for column in columns:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column}")

    # Policies issued before the pricing engine: their monthly premium times
    # twelve is the yearly figure, and they are life policies.
    op.execute(
        "UPDATE policies SET annual_premium_bdt = monthly_premium_bdt * 12 "
        "WHERE annual_premium_bdt IS NULL"
    )
    op.execute(
        "UPDATE policies SET free_look_until = start_date + 15 WHERE free_look_until IS NULL"
    )

    # Payments are handled by the bank, not here.
    op.execute("DROP TABLE IF EXISTS premium_payments")

    op.execute(CLAIMS)
    op.execute("ALTER TABLE claims ADD COLUMN IF NOT EXISTS accident BOOLEAN NOT NULL DEFAULT false")
    op.execute("CREATE INDEX IF NOT EXISTS idx_claims_tenant ON claims(tenant_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id)")
    op.execute(CLAIM_DOCUMENTS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_documents_claim ON claim_documents(claim_id)"
    )
    op.execute(DELETIONS)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_data_deletion_tenant "
        "ON data_deletion_requests(tenant_id, status)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_applicants_tenant_nid "
        "ON applicants(tenant_id, nid_number) WHERE nid_number IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS data_deletion_requests")
    op.execute("DROP TABLE IF EXISTS claim_documents")
    op.execute("DROP TABLE IF EXISTS claims")
    op.execute("DROP INDEX IF EXISTS idx_applicants_tenant_nid")
    for table, columns in COLUMNS.items():
        for column in columns:
            name = column.split()[0]
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {name}")
    # Enum values cannot be removed in PostgreSQL; the new ones stay, unused.
