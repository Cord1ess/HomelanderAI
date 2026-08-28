-- ============================================================================
-- HomelanderAI Database Schema
-- PostgreSQL 16
-- Academic capstone project — not for production use with real applicant data
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE user_role AS ENUM (
    'underwriter',
    'senior_underwriter',
    'admin'
);

CREATE TYPE application_status AS ENUM (
    'submitted',
    'processing',
    'insufficient_evidence',
    'scored',
    'decided'
);

CREATE TYPE evidence_file_type AS ENUM (
    'dicom',
    'lab_report',
    'clinical_note',
    'questionnaire'
);

CREATE TYPE model_arm_type AS ENUM (
    'vision',
    'nlp',
    'tabular'
);

CREATE TYPE model_run_status AS ENUM (
    'pending',
    'running',
    'completed',
    'failed'
);

CREATE TYPE explanation_artifact_type AS ENUM (
    'gradcam',
    'shap',
    'annotated_text'
);

CREATE TYPE risk_tier AS ENUM (
    'low',
    'moderate',
    'elevated',
    'insufficient_evidence'
);

CREATE TYPE underwriter_decision_type AS ENUM (
    'confirmed_fast_track',
    'approved_with_adjustment',
    'escalated_senior_review',
    'requested_additional_evidence'
);

CREATE TYPE notification_type AS ENUM (
    'application_submitted',
    'processing_complete',
    'tier_escalation',
    'decision_recorded',
    'evidence_requested',
    'api_key_expiring'
);

CREATE TYPE notification_channel AS ENUM (
    'email',
    'in_app',
    'sms'
);

CREATE TYPE notification_status AS ENUM (
    'pending',
    'sent',
    'failed',
    'read'
);

-- ============================================================================
-- TENANTS  (subscribing insurance carriers)
-- ============================================================================

CREATE TABLE tenants (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(255) NOT NULL,
    subscription_tier   VARCHAR(50)  NOT NULL DEFAULT 'standard',
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============================================================================
-- USERS  (underwriters, senior underwriters, admins — all belong to a tenant)
-- ============================================================================

CREATE TABLE users (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id        UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    full_name        VARCHAR(255) NOT NULL,
    email            VARCHAR(255) NOT NULL,
    role             user_role NOT NULL,
    license_number   VARCHAR(100),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_tenant_email UNIQUE (tenant_id, email)
);

CREATE INDEX idx_users_tenant_id ON users(tenant_id);

-- ============================================================================
-- API_KEYS  (tenant credentials for REST API access)
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
-- APPLICANTS  (the individual being underwritten — synthetic/de-identified)
-- ============================================================================

CREATE TABLE applicants (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    external_ref   VARCHAR(100) NOT NULL,
    date_of_birth  DATE,
    sex            VARCHAR(20),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_applicants_tenant_external_ref UNIQUE (tenant_id, external_ref)
);

CREATE INDEX idx_applicants_tenant_id ON applicants(tenant_id);

-- ============================================================================
-- APPLICATIONS  (one evidence-package submission for one applicant)
-- ============================================================================

CREATE TABLE applications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    applicant_id    UUID NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
    status          application_status NOT NULL DEFAULT 'submitted',
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_applications_tenant_id ON applications(tenant_id);
CREATE INDEX idx_applications_applicant_id ON applications(applicant_id);
CREATE INDEX idx_applications_status ON applications(status);

-- ============================================================================
-- EVIDENCE_FILES  (uploaded imaging, lab, notes, questionnaire files)
-- ============================================================================

CREATE TABLE evidence_files (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    file_type        evidence_file_type NOT NULL,
    storage_path     VARCHAR(500) NOT NULL,
    uploaded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_evidence_files_application_id ON evidence_files(application_id);

-- ============================================================================
-- MODEL_ARMS  (registered model arms — pluggable, not hardcoded)
-- ============================================================================

CREATE TABLE model_arms (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(255) NOT NULL,
    arm_type     model_arm_type NOT NULL,
    version      VARCHAR(50) NOT NULL,
    weight_hash  VARCHAR(255) NOT NULL,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_model_arms_name_version UNIQUE (name, version)
);

-- ============================================================================
-- MODEL_RUNS  (one execution of one arm against one application)
-- ============================================================================

CREATE TABLE model_runs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    model_arm_id     UUID NOT NULL REFERENCES model_arms(id) ON DELETE RESTRICT,
    status           model_run_status NOT NULL DEFAULT 'pending',
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    CONSTRAINT chk_model_runs_timing CHECK (
        completed_at IS NULL OR started_at IS NULL OR completed_at >= started_at
    )
);

CREATE INDEX idx_model_runs_application_id ON model_runs(application_id);
CREATE INDEX idx_model_runs_model_arm_id ON model_runs(model_arm_id);

-- ============================================================================
-- SUB_SCORES  (per-arm raw + calibrated score for one model run)
-- ============================================================================

CREATE TABLE sub_scores (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_run_id       UUID NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    raw_score          NUMERIC(5,2) NOT NULL,
    calibrated_score   NUMERIC(5,2) NOT NULL,
    CONSTRAINT chk_sub_scores_range CHECK (
        calibrated_score >= 0 AND calibrated_score <= 100
    )
);

CREATE INDEX idx_sub_scores_model_run_id ON sub_scores(model_run_id);

-- ============================================================================
-- EXPLANATION_ARTIFACTS  (Grad-CAM overlays, SHAP breakdowns, annotated text)
-- ============================================================================

CREATE TABLE explanation_artifacts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_run_id   UUID NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    artifact_type  explanation_artifact_type NOT NULL,
    storage_path   VARCHAR(500) NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_explanation_artifacts_model_run_id ON explanation_artifacts(model_run_id);

-- ============================================================================
-- COMPOSITE_SCORES  (fused CRS per application; versioned for re-scoring)
-- ============================================================================

CREATE TABLE composite_scores (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    version          INTEGER NOT NULL DEFAULT 1,
    crs_value        NUMERIC(5,2) NOT NULL,
    tier             risk_tier NOT NULL,
    computed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_composite_scores_range CHECK (crs_value >= 0 AND crs_value <= 100),
    CONSTRAINT uq_composite_scores_application_version UNIQUE (application_id, version)
);

CREATE INDEX idx_composite_scores_application_id ON composite_scores(application_id);

-- ============================================================================
-- UNDERWRITER_DECISIONS  (final human decision — always required, never automated)
-- ============================================================================

CREATE TABLE underwriter_decisions (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    underwriter_id   UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    decision         underwriter_decision_type NOT NULL,
    final_premium    NUMERIC(12,2),
    decided_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_underwriter_decisions_application UNIQUE (application_id)
);

CREATE INDEX idx_underwriter_decisions_underwriter_id ON underwriter_decisions(underwriter_id);

-- ============================================================================
-- AUDIT_LOG  (append-only, hash-chained record of every event)
-- ============================================================================

CREATE TABLE audit_log (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id   UUID NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    event_type       VARCHAR(100) NOT NULL,
    payload_hash     VARCHAR(255) NOT NULL,
    prev_hash        VARCHAR(255),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_audit_log_application_id ON audit_log(application_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);

-- ============================================================================
-- NOTIFICATIONS  (in-app / email / sms notifications sent to users)
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
-- NOTIFICATION_PREFERENCES  (per-user, per-type channel opt-in/out)
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
-- END OF SCHEMA
-- ============================================================================
