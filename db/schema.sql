-- ============================================================================
-- HomelanderAI Database Schema — v2
-- PostgreSQL 16+ (developed and tested against 17)
-- Academic capstone project — not for production use with real applicant data
--
-- v2 changes (per DATABASE.md): auth columns, tenant_id + RLS on every
-- tenant-owned table, intake form fields, model output detail, audit
-- payload + append-only trigger, evidence integrity, scoring provenance,
-- stuck-job recovery column.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

-- The three staff roles. Applicants have no role: they are not users.
-- 'medical_professional' was 'senior_underwriter' until migration 008.
CREATE TYPE user_role AS ENUM ('underwriter', 'medical_professional', 'admin');

-- 'awaiting_evidence' is an underwriter asking the applicant for more, as
-- distinct from 'insufficient_evidence', which is the model being unable to
-- read what it was given. The two look alike in the queue and mean opposite
-- things: one waits on the client, the other on the operator.
CREATE TYPE application_status AS ENUM (
    'submitted', 'processing', 'insufficient_evidence', 'awaiting_evidence',
    'scored', 'escalated',    -- handed to a medical professional; decision still open
    'decided'
);

-- 'image' covers a radiograph uploaded as PNG or JPEG rather than DICOM, which
-- is most of them. Without it such a file had to be filed as 'questionnaire',
-- which is simply untrue on a record that has to stand up to being audited.
-- 'ecg' is a 12-lead tracing stored as a signal array (400 Hz, 12 x 4096),
-- which is neither a picture nor a document.
CREATE TYPE evidence_file_type AS ENUM (
    'dicom', 'image', 'lab_report', 'clinical_note', 'questionnaire', 'ecg'
);

CREATE TYPE model_arm_type AS ENUM ('vision', 'nlp', 'tabular');

CREATE TYPE model_run_status AS ENUM ('pending', 'running', 'completed', 'failed');

CREATE TYPE explanation_artifact_type AS ENUM ('gradcam', 'shap', 'annotated_text');

CREATE TYPE risk_tier AS ENUM ('low', 'moderate', 'elevated', 'insufficient_evidence');

CREATE TYPE underwriter_decision_type AS ENUM (
    'confirmed_fast_track', 'approved_with_adjustment',
    'escalated_senior_review', 'requested_additional_evidence', 'declined'
);

CREATE TYPE notification_type AS ENUM (
    'application_submitted', 'processing_complete', 'tier_escalation',
    'decision_recorded', 'evidence_requested', 'api_key_expiring', 'doctor_reviewed',
    'access_requested', 'access_decided', 'documents_uploaded',
    'policy_issued', 'policy_cancelled',
    'claim_filed', 'claim_updated', 'deletion_requested'
);

CREATE TYPE notification_channel AS ENUM ('email', 'in_app', 'sms');

CREATE TYPE notification_status AS ENUM ('pending', 'sent', 'failed', 'read');

-- ============================================================================
-- TENANTS
-- ============================================================================

CREATE TABLE tenants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL,
    subscription_tier   VARCHAR(50)  NOT NULL DEFAULT 'standard',
    -- How long this carrier tells applicants a decision usually takes, in
    -- working days. Set by the carrier's admin; copied onto each application
    -- as a date at submit, so changing it later does not move promises already
    -- made.
    turnaround_business_days INTEGER NOT NULL DEFAULT 2
        CHECK (turnaround_business_days BETWEEN 1 AND 30),
    -- Risk-score tier boundaries, set by the carrier's admin. Every score
    -- snapshots the boundaries it was tiered with (composite_scores.
    -- tier_thresholds), so changing these affects new scores only.
    tier_low_max        NUMERIC(5,2)  NOT NULL DEFAULT 30.00
        CHECK (tier_low_max > 0 AND tier_low_max < 100),
    tier_moderate_max   NUMERIC(5,2)  NOT NULL DEFAULT 65.00
        CHECK (tier_moderate_max > 0 AND tier_moderate_max < 100),
    CONSTRAINT ck_tenants_tier_order CHECK (tier_low_max < tier_moderate_max),
    -- Pricing policy: the monthly premium for the low and moderate plans at
    -- the reference cover; premiums scale linearly with the cover requested.
    -- Elevated and unscorable tiers carry no rate on purpose (see plans.py).
    premium_low_bdt      NUMERIC(12,2) NOT NULL DEFAULT 5000.00  CHECK (premium_low_bdt > 0),
    premium_moderate_bdt NUMERIC(12,2) NOT NULL DEFAULT 7500.00  CHECK (premium_moderate_bdt > 0),
    reference_cover_bdt  NUMERIC(14,2) NOT NULL DEFAULT 1000000.00 CHECK (reference_cover_bdt > 0),
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
    life_expense_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 22.32,
    life_interest_pct NUMERIC(5, 2) NOT NULL DEFAULT 5.00,
    health_rate_per_lakh_bdt NUMERIC(10, 2) NOT NULL DEFAULT 1800,
    smoker_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 50,
    monthly_loading_pct NUMERIC(5, 2) NOT NULL DEFAULT 5
);


-- ============================================================================
-- USERS  [v2: + password_hash, is_active, last_login_at]
-- ============================================================================

CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    full_name        VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,   -- Argon2id only
    role             user_role NOT NULL,
    license_number   VARCHAR(100),
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at    TIMESTAMPTZ,
    -- Set when the person chose their own password, so a built-in staff
    -- account is never reset to the demo password after that.
    password_changed_at TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Email is unique across the whole system, not per company.
    -- Sign-in asks only for an email and password, so the same address in two
    -- companies would make it impossible to tell which account is meant.
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX idx_users_tenant_id ON users(tenant_id);


-- Every change to a company's settings (tenants.*), who made it and what it was before.
-- Separate from audit_log, whose hash chain is per application; a company
-- setting belongs to no application.
CREATE TABLE tenant_settings_changes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    changed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- {field: {"from": x, "to": y}} for each field that changed.
    changes      JSONB NOT NULL
);

CREATE INDEX idx_tenant_settings_changes_tenant ON tenant_settings_changes(tenant_id, changed_at DESC);

-- ============================================================================
-- APPLICANTS
-- ============================================================================

CREATE TABLE applicants (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_ref   VARCHAR(100) NOT NULL,   -- auto-assigned from applicants_ref_seq (see trigger below)
    name           VARCHAR(150),            -- operator-entered; carrier reference, not from file header
    phone          VARCHAR(30),             -- operator-entered; carrier reference, not from file header
    date_of_birth  DATE,
    sex            VARCHAR(20),
    height_cm      NUMERIC(5,2),     -- feeds the XGBoost (tabular) BMI feature
    weight_kg      NUMERIC(5,2),
    face_photo_path VARCHAR(500),    -- identity photo; NO model reads this
    -- Client portal sign-in. portal_id is random, not the HL- reference: the
    -- reference is a sequence, so it reveals how many applications exist and is
    -- known to staff, which makes it a poor login name. The password is
    -- generated at intake and stored only as an Argon2id hash.
    portal_id       VARCHAR(20) UNIQUE,
    email           VARCHAR(255),
    password_hash   VARCHAR(255),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_applicants_tenant_external_ref UNIQUE (tenant_id, external_ref),
    nid_number VARCHAR(20),
    nid_name VARCHAR(200),
    nid_date_of_birth DATE,
    nid_image_path VARCHAR(500),
    nominee_name VARCHAR(200),
    nominee_relation VARCHAR(50),
    nominee_phone VARCHAR(30),
    consent_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

-- Per-tenant-diagnostic reference, generated automatically by the database at
-- INSERT time: HL-<seq>. Guaranteed monotonic and globally unique, so it works
-- without the client ever typing or guessing an id.
CREATE SEQUENCE applicants_ref_seq;

CREATE OR REPLACE FUNCTION applicants_gen_ref() RETURNS trigger AS $$
BEGIN
    NEW.external_ref := 'HL-' || lpad(nextval('applicants_ref_seq')::text, 6, '0');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_applicants_gen_ref
    BEFORE INSERT ON applicants
    FOR EACH ROW
    WHEN (NEW.external_ref IS NULL OR NEW.external_ref = '')
    EXECUTE FUNCTION applicants_gen_ref();

CREATE INDEX idx_applicants_tenant_id ON applicants(tenant_id);

-- ============================================================================
-- APPLICATIONS  [v2: + coverage/intake fields, processing_started_at]
-- ============================================================================

CREATE TABLE applications (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id              UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    applicant_id           UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    status                 application_status NOT NULL DEFAULT 'submitted',
    coverage_type          VARCHAR(50),
    coverage_amount        NUMERIC(12,2),
    policy_term            VARCHAR(20),
    -- Which arms to run, e.g. ["cxr_lung"]. Adding an arm needs no migration.
    models_requested       JSONB NOT NULL DEFAULT '[]'::jsonb,
    declared_history       JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- When the applicant was told to expect an answer. Set from the carrier
    -- default at submit; any underwriter may revise it with a reason, which is
    -- kept in expected_by_note and in the audit log. A date, not a countdown.
    expected_by            DATE,
    expected_by_note       VARCHAR(300),
    -- When an underwriter first sent it to a doctor. A doctor sees only the
    -- applications with this set; nothing else in the company is theirs.
    sent_to_doctor_at      TIMESTAMPTZ,
    evaluated_at           TIMESTAMPTZ,
    processing_started_at  TIMESTAMPTZ,
    submitted_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    payment_mode VARCHAR(10) NOT NULL DEFAULT 'monthly',
    assigned_to UUID REFERENCES users(id) ON DELETE SET NULL,
    assigned_at TIMESTAMPTZ
);

CREATE INDEX idx_applications_tenant_id ON applications(tenant_id);
CREATE INDEX idx_applications_applicant_id ON applications(applicant_id);
CREATE INDEX idx_applications_status ON applications(status);

-- ============================================================================
-- MODEL_ARMS  [v2: + preprocessing_version. Not tenant-scoped: shared registry]
-- ============================================================================

CREATE TABLE model_arms (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   VARCHAR(255) NOT NULL,
    arm_type               model_arm_type NOT NULL,
    version                VARCHAR(50) NOT NULL,
    preprocessing_version  VARCHAR(50) NOT NULL,
    weight_hash            VARCHAR(255) NOT NULL,
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_model_arms_name_version UNIQUE (name, version)
);

-- ============================================================================
-- EVIDENCE_FILES  [v2: + tenant_id, file metadata, content_hash, deidentified_at]
-- ============================================================================

CREATE TABLE evidence_files (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id      UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    file_type           evidence_file_type NOT NULL,
    storage_path        VARCHAR(500) NOT NULL,   -- relative path under ./data
    original_filename   VARCHAR(255),
    mime_type           VARCHAR(100),
    size_bytes          BIGINT,
    content_hash        VARCHAR(64),             -- sha256 of stored (de-identified) file
    deidentified_at     TIMESTAMPTZ,              -- NULL = not DICOM, or not yet processed
    -- Which arm this file is for. Nullable: a generic report attached to the
    -- application belongs to no single arm (DATABASE.md §C).
    model_arm_id        UUID REFERENCES model_arms(id) ON DELETE SET NULL,
    -- What the evidence is, as confirmed by the operator at intake. Distinct
    -- from file_type, which is the container (dicom, image, document); this is
    -- the content, and it decides which model may read the file. NULL means
    -- nobody established it, in which case no model runs on it.
    evidence_kind       VARCHAR(30),
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_files_tenant_id ON evidence_files(tenant_id);
CREATE INDEX idx_evidence_files_application_id ON evidence_files(application_id);
CREATE INDEX idx_evidence_files_model_arm_id ON evidence_files(model_arm_id);

-- ============================================================================
-- MODEL_RUNS  [v2: + tenant_id, error_message]
-- ============================================================================

CREATE TABLE model_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    model_arm_id     UUID NOT NULL REFERENCES model_arms(id) ON DELETE RESTRICT,
    status           model_run_status NOT NULL DEFAULT 'pending',
    error_message    TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    CONSTRAINT chk_model_runs_timing CHECK (
        completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX idx_model_runs_tenant_id ON model_runs(tenant_id);
CREATE INDEX idx_model_runs_application_id ON model_runs(application_id);
CREATE INDEX idx_model_runs_model_arm_id ON model_runs(model_arm_id);

-- ============================================================================
-- SUB_SCORES  [v2: + tenant_id, details]
-- ============================================================================

CREATE TABLE sub_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id          UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_run_id       UUID NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    raw_score          NUMERIC(5,2) NOT NULL,
    calibrated_score   NUMERIC(5,2) NOT NULL,
    details            JSONB NOT NULL DEFAULT '{}'::jsonb,  -- e.g. per-finding probabilities
    CONSTRAINT chk_sub_scores_range CHECK (calibrated_score >= 0 AND calibrated_score <= 100)
);

CREATE INDEX idx_sub_scores_tenant_id ON sub_scores(tenant_id);
CREATE INDEX idx_sub_scores_model_run_id ON sub_scores(model_run_id);

-- ============================================================================
-- EXPLANATION_ARTIFACTS  [v2: + tenant_id]
-- ============================================================================

CREATE TABLE explanation_artifacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    model_run_id   UUID NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    artifact_type  explanation_artifact_type NOT NULL,
    storage_path   VARCHAR(500) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_explanation_artifacts_tenant_id ON explanation_artifacts(tenant_id);
CREATE INDEX idx_explanation_artifacts_model_run_id ON explanation_artifacts(model_run_id);

-- ============================================================================
-- COMPOSITE_SCORES  [v2: + tenant_id, method, tier_thresholds]
-- ============================================================================

CREATE TABLE composite_scores (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id         UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id    UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    version           INTEGER NOT NULL DEFAULT 1,
    crs_value         NUMERIC(5,2) NOT NULL,
    tier              risk_tier NOT NULL,
    method            VARCHAR(100) NOT NULL DEFAULT 'expert_weights_v1',
    tier_thresholds   JSONB NOT NULL DEFAULT '{}'::jsonb,  -- cut-points at scoring time
    -- Which declared-history rules fired, with their points and the wording
    -- shown to the underwriter. Stored rather than recomputed: the rules will
    -- be re-tuned, and a past decision has to stay explainable in the terms it
    -- was actually made in.
    adjustments       JSONB NOT NULL DEFAULT '[]'::jsonb,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_composite_scores_range CHECK (crs_value >= 0 AND crs_value <= 100),
    CONSTRAINT uq_composite_scores_application_version UNIQUE (application_id, version)
);

CREATE INDEX idx_composite_scores_tenant_id ON composite_scores(tenant_id);
CREATE INDEX idx_composite_scores_application_id ON composite_scores(application_id);

-- ============================================================================
-- UNDERWRITER_DECISIONS  [v2: + tenant_id]
-- ============================================================================

CREATE TABLE underwriter_decisions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    underwriter_id   UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision         underwriter_decision_type NOT NULL,
    final_premium    NUMERIC(12,2),
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_underwriter_decisions_application UNIQUE (application_id),
    rating_pct INTEGER NOT NULL DEFAULT 0,
    exclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    decline_reason VARCHAR(40),
    decline_note TEXT,
    reapply_after DATE
);

CREATE INDEX idx_underwriter_decisions_tenant_id ON underwriter_decisions(tenant_id);
CREATE INDEX idx_underwriter_decisions_underwriter_id ON underwriter_decisions(underwriter_id);

-- ============================================================================
-- REQUESTED_DOCUMENTS
-- What an underwriter has asked the applicant to supply. Requesting evidence is
-- a pause, not a decision: underwriter_decisions is write-once, and if asking
-- for a document consumed the one decision, nothing could be decided once the
-- document arrived. So this is its own table and its own status.
-- ============================================================================

CREATE TABLE requested_documents (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    requested_by     UUID REFERENCES users(id) ON DELETE RESTRICT,
    -- In the underwriter's words, shown verbatim to the applicant:
    -- "A chest X-ray taken within the last 6 months".
    description      VARCHAR(300) NOT NULL,
    requested_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    fulfilled_at     TIMESTAMPTZ,
    -- The evidence that satisfied it, once the applicant uploads one.
    fulfilled_by     UUID REFERENCES evidence_files(id) ON DELETE SET NULL
);

CREATE INDEX idx_requested_documents_tenant_id ON requested_documents(tenant_id);

-- A doctor's review of the readers' results. The doctor does not decide the
-- policy: they say whether the results are medically right, and the
-- application goes back to the underwriter carrying that verdict as a tag.
CREATE TABLE doctor_reviews (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    doctor_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    verdict         VARCHAR(20) NOT NULL CHECK (verdict IN ('accurate', 'inaccurate')),
    note            TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_doctor_reviews_application ON doctor_reviews(application_id, created_at DESC);

-- A doctor writing to the client directly, when what the evidence shows
-- cannot wait for the policy: "see a doctor today". Shown on the client's
-- portal and emailed when mail is set up. Never carries a score.
CREATE TABLE client_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id  UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    sender_id       UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    urgency         VARCHAR(20) NOT NULL CHECK (urgency IN ('urgent', 'routine')),
    message         TEXT NOT NULL,
    emailed         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_client_messages_application ON client_messages(application_id, created_at DESC);

-- A client's personal details are the company owner's to hand out. An
-- underwriter or a doctor who needs them asks, with a reason; an administrator
-- approves or declines. An approval opens that one client to that one person
-- for a day.
-- An approved application becomes a policy: the plan, the monthly premium, the
-- sum assured paid out on a claim, and the dates it runs between. Only an
-- administrator cancels one.
CREATE TABLE policies (
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
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    product VARCHAR(20) NOT NULL DEFAULT 'life',
    annual_premium_bdt NUMERIC(12, 2),
    premium_mode VARCHAR(10) NOT NULL DEFAULT 'monthly',
    rating_pct INTEGER NOT NULL DEFAULT 0,
    exclusions JSONB NOT NULL DEFAULT '[]'::jsonb,
    free_look_until DATE,
    waiting_until DATE,
    preexisting_until DATE
);

CREATE INDEX idx_policies_tenant ON policies(tenant_id, status);
CREATE INDEX idx_policies_applicant ON policies(applicant_id);

-- Every message the platform tried to send. Never the body: it can hold a
-- password.
CREATE TABLE email_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id  UUID REFERENCES applications(id) ON DELETE CASCADE,
    kind            VARCHAR(40) NOT NULL,
    recipient       VARCHAR(255) NOT NULL,
    subject         VARCHAR(255) NOT NULL,
    status          VARCHAR(20) NOT NULL
                    CHECK (status IN ('sent', 'not_configured', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_email_log_application ON email_log(application_id, created_at DESC);

-- A claim on a policy: a death claim on a life policy, or hospital bills on
-- hospital cover. By law a claim is settled within 90 days of the documents
-- being complete (`settle_by`).
CREATE TABLE claims (
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
);

CREATE INDEX idx_claims_tenant ON claims(tenant_id, status);
CREATE INDEX idx_claims_policy ON claims(policy_id);

CREATE TABLE claim_documents (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    claim_id        UUID NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    storage_path    VARCHAR(500) NOT NULL,
    original_filename VARCHAR(255),
    mime_type       VARCHAR(100),
    uploaded_by_client BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_claim_documents_claim ON claim_documents(claim_id);

-- A client asking for their data to be deleted. An administrator approves it;
-- it is then carried out on `delete_on`, thirty days after the request.
CREATE TABLE data_deletion_requests (
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
);

CREATE INDEX idx_data_deletion_tenant ON data_deletion_requests(tenant_id, status);
CREATE UNIQUE INDEX idx_applicants_tenant_nid ON applicants(tenant_id, nid_number)
    WHERE nid_number IS NOT NULL;

CREATE TABLE client_access_requests (
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
);

CREATE INDEX idx_client_access_requests_tenant ON client_access_requests(tenant_id, status, created_at DESC);
CREATE INDEX idx_client_access_requests_requester ON client_access_requests(requester_id, applicant_id);
CREATE INDEX idx_requested_documents_application_id ON requested_documents(application_id);

-- ============================================================================
-- AUDIT_LOG  [v2: + tenant_id, payload, actor_user_id; enforced append-only]
-- ============================================================================

CREATE TABLE audit_log (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    actor_user_id    UUID REFERENCES users(id) ON DELETE RESTRICT,  -- NULL = system
    event_type       VARCHAR(100) NOT NULL,
    payload          JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_hash     VARCHAR(255) NOT NULL,
    prev_hash        VARCHAR(255),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_tenant_id ON audit_log(tenant_id);
CREATE INDEX idx_audit_log_application_id ON audit_log(application_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);

-- Enforce append-only at the database level, not just by convention.
CREATE OR REPLACE FUNCTION audit_log_is_append_only()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();

-- ============================================================================
-- NOTIFICATIONS
-- ============================================================================

CREATE TABLE notifications (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    application_id      UUID REFERENCES applications(id) ON DELETE CASCADE,
    notification_type   notification_type NOT NULL,
    channel             notification_channel NOT NULL,
    status              notification_status NOT NULL DEFAULT 'pending',
    message             TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    read_at             TIMESTAMPTZ
);

CREATE INDEX idx_notifications_user_id ON notifications(user_id);
CREATE INDEX idx_notifications_application_id ON notifications(application_id);
CREATE INDEX idx_notifications_status ON notifications(status);

-- ============================================================================
-- ROW LEVEL SECURITY
-- Applied to every table carrying tenant_id. The application must connect
-- as a plain (non-superuser) role for this to have any effect.
-- ============================================================================

-- Guarded so this file can be run more than once.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
        CREATE ROLE app_user LOGIN PASSWORD 'CHANGE_ME_BEFORE_DEPLOY';
    END IF;
END $$;

-- GRANT ... ON DATABASE needs the database name spelled out, so build the
-- statement at run time rather than calling current_database() inline.
DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO app_user', current_database());
END $$;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
REVOKE UPDATE, DELETE ON audit_log FROM app_user;  -- append-only: belt and braces

DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'users', 'applicants', 'applications', 'evidence_files',
        'model_runs', 'sub_scores', 'explanation_artifacts', 'composite_scores',
        'underwriter_decisions', 'requested_documents', 'audit_log',
        'notifications'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY;', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I USING (tenant_id = current_setting(''app.tenant_id'', true)::uuid);',
            t
        );
    END LOOP;
END $$;

-- The API must run, once per transaction:
--   SET LOCAL app.tenant_id = '<uuid from the session>';
-- Never SET (without LOCAL) — that leaks across pooled connections.

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
