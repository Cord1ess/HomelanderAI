-- ============================================================================
-- HomelanderAI Database Schema — v2
-- PostgreSQL 16
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

CREATE TYPE user_role AS ENUM ('underwriter', 'senior_underwriter', 'admin');

CREATE TYPE application_status AS ENUM (
    'submitted', 'processing', 'insufficient_evidence', 'scored', 'decided'
);

CREATE TYPE evidence_file_type AS ENUM (
    'dicom', 'lab_report', 'clinical_note', 'questionnaire'
);

CREATE TYPE model_arm_type AS ENUM ('vision', 'nlp', 'tabular');

CREATE TYPE model_run_status AS ENUM ('pending', 'running', 'completed', 'failed');

CREATE TYPE explanation_artifact_type AS ENUM ('gradcam', 'shap', 'annotated_text');

CREATE TYPE risk_tier AS ENUM ('low', 'moderate', 'elevated', 'insufficient_evidence');

CREATE TYPE underwriter_decision_type AS ENUM (
    'confirmed_fast_track', 'approved_with_adjustment',
    'escalated_senior_review', 'requested_additional_evidence'
);

CREATE TYPE notification_type AS ENUM (
    'application_submitted', 'processing_complete', 'tier_escalation',
    'decision_recorded', 'evidence_requested', 'api_key_expiring'
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
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
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
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Email is unique across the whole system, not per company.
    -- Sign-in asks only for an email and password, so the same address in two
    -- companies would make it impossible to tell which account is meant.
    CONSTRAINT uq_users_email UNIQUE (email)
);

CREATE INDEX idx_users_tenant_id ON users(tenant_id);

-- ============================================================================
-- API_KEYS
-- ============================================================================

CREATE TABLE api_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    key_hash     VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at   TIMESTAMPTZ,
    CONSTRAINT uq_api_keys_key_hash UNIQUE (key_hash)
);

CREATE INDEX idx_api_keys_tenant_id ON api_keys(tenant_id);

-- ============================================================================
-- APPLICANTS  [unchanged — no name column is intentional, keep it that way]
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
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_applicants_tenant_external_ref UNIQUE (tenant_id, external_ref)
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
    declared_history       JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at           TIMESTAMPTZ,
    processing_started_at  TIMESTAMPTZ,
    submitted_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_applications_tenant_id ON applications(tenant_id);
CREATE INDEX idx_applications_applicant_id ON applications(applicant_id);
CREATE INDEX idx_applications_status ON applications(status);

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
    uploaded_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_files_tenant_id ON evidence_files(tenant_id);
CREATE INDEX idx_evidence_files_application_id ON evidence_files(application_id);
CREATE INDEX idx_evidence_files_model_arm_id ON evidence_files(model_arm_id);

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
    CONSTRAINT uq_underwriter_decisions_application UNIQUE (application_id)
);

CREATE INDEX idx_underwriter_decisions_tenant_id ON underwriter_decisions(tenant_id);
CREATE INDEX idx_underwriter_decisions_underwriter_id ON underwriter_decisions(underwriter_id);

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
-- NOTIFICATION_PREFERENCES
-- ============================================================================

CREATE TABLE notification_preferences (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type   notification_type NOT NULL,
    email_enabled       BOOLEAN NOT NULL DEFAULT TRUE,
    in_app_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT uq_notification_preferences_user_type UNIQUE (user_id, notification_type)
);

CREATE INDEX idx_notification_preferences_user_id ON notification_preferences(user_id);

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
        'users', 'api_keys', 'applicants', 'applications', 'evidence_files',
        'model_runs', 'sub_scores', 'explanation_artifacts', 'composite_scores',
        'underwriter_decisions', 'audit_log', 'notifications'
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
