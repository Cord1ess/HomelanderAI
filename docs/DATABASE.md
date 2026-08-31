# Database — required changes

**For:** whoever owns the database and auth.
**Base:** `db/schema.sql` as it stands today. This document lists only what needs
to **change**, and why. Everything not mentioned here is fine as-is.

Read [SPEC.md §1 "The operating flow"](SPEC.md) first — the changes below only
make sense against that flow.

---

## The short version

| Group | Why | Blocking? |
|---|---|---|
| **A. Auth columns** | `users` has no password field, so nobody can log in | **Yes — login** |
| **B. `tenant_id` everywhere** | Row-level security needs it on every table | **Yes — security** |
| **C. Intake form fields** | The form collects data with nowhere to go; now **model-driven** with per-arm fields + `models_requested` | **Yes — the form** |
| **D. Model output detail** | The vision arm returns 18 numbers; there is no column for them | **Yes — scoring** |
| **E. Audit payloads** | A hash chain you cannot re-verify proves nothing | Yes |
| **F. Evidence integrity** | The audit trail is specified to record input signatures | Yes |
| **G. Scoring provenance** | No record of *which* scoring method produced a score | Yes |
| **H. Stuck-job recovery** | Jobs run in-process; a restart strands them | Recommended |

---

## What is already right — do not change it

Genuinely good decisions worth calling out, so nobody "fixes" them later:

- ~~**`applicants` has no name column.**~~ **Reversed 2026-09-01** — `applicants`
  now carries `name` + `phone` (operator-entered, carrier reference) plus an
  auto-generated `external_ref`; see [SPEC.md §9](SPEC.md) reversal note. The
  deeper rule still holds: **evidence** is PII-minimised (file-header
  identifiers stripped), and only the de-identified copy is ever stored.
- **UUID primary keys** everywhere — no guessable sequential IDs across tenants.
- **`model_arms` is a registry table**, not hardcoded arms. Adding the NLP or
  tabular arm later becomes a row, not a migration.
- **`composite_scores` is versioned** per application, so re-scoring keeps
  history instead of overwriting it.
- **`underwriter_decisions` has a UNIQUE on `application_id`** — one final
  decision per application, enforced by the database.
- **`application_status` already includes `insufficient_evidence`**, which the
  spec requires as a real outcome rather than an error.
- **`audit_log` already has `prev_hash`** — the chain structure is right.

---

## A. Auth columns — blocks login

`users` currently cannot authenticate anyone.

```sql
ALTER TABLE users
    ADD COLUMN password_hash  VARCHAR(255) NOT NULL,
    ADD COLUMN is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN last_login_at  TIMESTAMPTZ;
```

- `password_hash` — **Argon2id**, not bcrypt, not SHA. Never store the password.
- `is_active` — disable a user without deleting them and breaking their
  historical decisions (`underwriter_decisions.underwriter_id` is
  `ON DELETE RESTRICT`, so users cannot be deleted anyway — this is the intended
  way to deactivate).

**No sessions table.** The session is a signed JWT in an httpOnly cookie, so
there is nothing to store. Add a table only if we later need forced logout.

---

## B. `tenant_id` on every table — blocks row-level security

**This is the most important change in this document.**

Right now only `tenants`, `users`, `api_keys`, `applicants`, `applications` and
`notifications` carry `tenant_id`. Everything else reaches its tenant through a
join. That breaks row-level security, because an RLS policy is written per table
and cannot cheaply join upward.

Add it to all seven remaining tables:

```sql
ALTER TABLE evidence_files        ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE model_runs            ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE sub_scores            ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE explanation_artifacts ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE composite_scores      ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE underwriter_decisions ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;
ALTER TABLE audit_log             ADD COLUMN tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE;

-- backfill from the parent application, then:
ALTER TABLE evidence_files        ALTER COLUMN tenant_id SET NOT NULL;
-- ...repeat for each

CREATE INDEX idx_evidence_files_tenant_id        ON evidence_files(tenant_id);
CREATE INDEX idx_model_runs_tenant_id            ON model_runs(tenant_id);
CREATE INDEX idx_sub_scores_tenant_id            ON sub_scores(tenant_id);
CREATE INDEX idx_explanation_artifacts_tenant_id ON explanation_artifacts(tenant_id);
CREATE INDEX idx_composite_scores_tenant_id      ON composite_scores(tenant_id);
CREATE INDEX idx_underwriter_decisions_tenant_id ON underwriter_decisions(tenant_id);
CREATE INDEX idx_audit_log_tenant_id             ON audit_log(tenant_id);
```

Yes, this duplicates data. That is the standard and correct trade for RLS.

### Then turn RLS on

```sql
-- Repeat this block for every table holding tenant data.
ALTER TABLE applicants ENABLE ROW LEVEL SECURITY;
ALTER TABLE applicants FORCE  ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON applicants
    USING (tenant_id = current_setting('app.tenant_id', true)::uuid);
```

Three details that are easy to get wrong:

1. **`FORCE ROW LEVEL SECURITY` is not optional.** Without it, the table's owner
   bypasses every policy — and in development the app usually *is* the owner. Skip
   this and your policies silently do nothing.
2. **The app must not connect as a superuser.** Superusers bypass RLS
   unconditionally. Create a plain role for the application.
3. **`current_setting('app.tenant_id', true)`** — the `true` means "return NULL
   instead of erroring when unset", so a query outside a request context returns
   no rows rather than crashing.

The API sets this once per transaction:

```sql
SET LOCAL app.tenant_id = '<uuid from the session>';
```

`SET LOCAL` scopes it to the transaction, so it cannot leak across pooled
connections. **Use `SET LOCAL`, never `SET`.**

---

## C. Intake form fields — blocks the form

The form in [DASHBOARD.md](DASHBOARD.md) collects coverage details and declared
medical history. There is nowhere to put either.

> **▶︎ CHANGED** — the intake form is now **model-driven** (see
> [INTAKE_FORM.md](INTAKE_FORM.md)): the operator selects which model arms apply
> from a vertical checkbox menu, and each selected model contributes its own
> risk fields and a required-upload instruction. The schema below is updated to
> hold (a) the coverage columns, (b) which arms to run, and (c) a **per-model**
> declared-history shape. Compare against the previous single-TB `symptoms` /
> `history` object.

**▶︎ CHANGED — `applicants` gains `name`/`phone` (carrier reference, operator-
entered), `face_photo_path` (identity photo, NOT a model input), and a
DB-generated `external_ref`:**

```sql
ALTER TABLE applicants
    ADD COLUMN name            VARCHAR(150),
    ADD COLUMN phone           VARCHAR(30),
    ADD COLUMN height_cm       NUMERIC(5,2),
    ADD COLUMN weight_kg       NUMERIC(5,2),
    ADD COLUMN face_photo_path VARCHAR(500);  -- ▶︎ CHANGED

CREATE SEQUENCE applicants_ref_seq;

-- trigger: fill external_ref = 'HL-' || lpad(nextval('applicants_ref_seq'),6,'0')
-- at INSERT when empty — the reference is generated BY THE DATABASE.
```

**▶︎ CHANGED — note on `name`/`phone`:** this is a **deliberate reversal** of the
earlier "no name column" rule. The applicant's name and phone are operator-
entered for the **carrier's** use (the person in front of you, not from a file
header) and sit on `applicants` as ordinary carrier reference data — see the
dated reversal note in [SPEC.md §9](SPEC.md). This does **not** change evidence
handling: file-header identifiers (DICOM tags, note identifiers) are still
stripped on the way in.

**▶︎ CHANGED — note on `external_ref`:** the reference is **generated
automatically by the database** at INSERT time from `applicants_ref_seq`
(e.g. `HL-000012`), so the client/operator never types or guesses an id. The
form may fetch a preview before submit, but the database is the source of truth
and `uq_applicants_tenant_external_ref` still guarantees uniqueness per tenant.

**▶︎ CHANGED — `applications` gains `models_requested` (which arms the
orchestrator runs) and `policy_term`, alongside the existing coverage and
declared-history columns:**

```sql
ALTER TABLE applications
    ADD COLUMN coverage_type      VARCHAR(50),
    ADD COLUMN coverage_amount    NUMERIC(12,2),
    ADD COLUMN policy_term        VARCHAR(20),   -- ▶︎ CHANGED: 1/5/10/20 years
    ADD COLUMN models_requested   JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ▶︎ CHANGED
    ADD COLUMN declared_history   JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN evaluated_at       TIMESTAMPTZ;
```

**Why `declared_history` is JSONB and not columns.** The field set will change
every time we add a condition, a model arm, or a field on an existing arm. One
JSONB column absorbs that; many boolean columns mean a migration each time. It
is still queryable — `declared_history->'cxr_lung'->>'smoker' = 'true'` works and
can be indexed.

`models_requested` is an array of arm ids (e.g. `["cxr_lung","mirai"]`). It is
the intake half of the model registry in [SPEC.md §6](SPEC.md): the orchestrator
runs exactly the arms it names. Each new arm is a row in the registry table and,
on the form, one more entry in the vertical menu — it does **not** need a
migration.

**▶︎ CHANGED — shape the API will write (per-model keyed, one key per selected
arm):**

```json
{
  "cxr_lung": {
    "symptoms": {
      "cough_over_2_weeks": true,
      "weight_loss": false,
      "night_sweats": true,
      "haemoptysis": false,
      "fever": true
    },
    "history": {
      "prior_tb": true,
      "prior_tb_treatment_completed": true,
      "diabetes": false,
      "hiv": false,
      "household_tb_contact": false,
      "antibiotics_no_improvement": false,
      "smoker": true
    },
    "cardio": {
      "hypertension": false,
      "high_cholesterol": false,
      "family_heart_disease": true
    }
  },
  "mirai": {
    "family_breast_cancer": false,
    "prior_biopsy": false,
    "brca_status": "not_tested"
  },
  "ham10000": {
    "skin_type": "II",
    "prior_skin_cancer": false,
    "body_site": "left_lower_leg"
  },
  "eyepacs": {
    "diabetes_duration": "under_5_years",
    "hypertension": false,
    "smoker": true
  },
  "xgboost": {
    "height_cm": 170,
    "weight_kg": 70,
    "alcohol": "occasionally",
    "activity": "moderate",
    "occupation": "teacher",
    "smoker": true
  },
  "neuro": {
    "memory_concerns": true,
    "speech_concerns": false,
    "mobility_concerns": false
  }
}
```

**▶︎ CHANGED — note on `biobert`:** the clinical-NLP arm reads the uploaded
clinical note directly and contributes no structured keys to `declared_history`
in Phase 1.

**▶︎ CHANGED — note on genetic data (`mirai.brca_status`):** genetic-marker data
ships **default-off**, jurisdiction-gated, per [SPEC.md §10](SPEC.md). The form
collects it but the extracting consumer must honour the tenant policy flag.

**Do not add a separate `intake` table.** One column on the row it belongs to is
simpler and there is no second consumer ([DESIGN_POLICY.md](DESIGN_POLICY.md) §2).

---

## D. Model output detail — blocks scoring

`sub_scores` stores `raw_score` and `calibrated_score` and nothing else. But the
vision arm produces **18 finding probabilities**, and the underwriter needs to
see them. Later arms produce extracted entities or feature values.

```sql
ALTER TABLE sub_scores ADD COLUMN details JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE model_runs ADD COLUMN error_message TEXT;
```

`details` for the vision arm holds the raw finding map:

```json
{ "Consolidation": 0.41, "Nodule": 0.12, "Effusion": 0.07, "...": 0.0 }
```

`error_message` matters because [DESIGN_POLICY.md](DESIGN_POLICY.md) §12 says do
not swallow errors. When an arm fails we need to know why, and `status='failed'`
alone does not say.

---

## E. Audit payloads — makes the chain verifiable

`audit_log` stores `payload_hash` but not the payload. That means the chain can
never be re-verified from the log itself — you would have to reconstruct the
original payload from other tables and hope nothing drifted. A hash chain you
cannot verify proves nothing.

```sql
ALTER TABLE audit_log
    ADD COLUMN payload        JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN actor_user_id  UUID REFERENCES users(id) ON DELETE RESTRICT;
```

`actor_user_id` is **nullable on purpose**: `NULL` means the system did it, a
UUID means a person did. Both need recording.

### Make it genuinely append-only

Application code promising not to update is not a guarantee. Enforce it:

```sql
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
```

Also revoke `UPDATE` and `DELETE` on the table from the application role. Belt
and braces — this is the one table where it is worth both.

---

## F. Evidence integrity

[SPEC.md §4](SPEC.md) requires the audit record to include **input signatures**.
`evidence_files` currently stores only a path.

**▶︎ CHANGED — per-model uploads:** each model's panel uploads its own report, so
`evidence_files` gains a link to the arm that consumes it. The orchestrator
reads a model's inputs via `WHERE model_arm_id = <arm>`.

```sql
ALTER TABLE evidence_files
    ADD COLUMN original_filename VARCHAR(255),
    ADD COLUMN mime_type         VARCHAR(100),
    ADD COLUMN size_bytes        BIGINT,
    ADD COLUMN content_hash      VARCHAR(64),   -- sha256 of the stored (de-identified) file
    ADD COLUMN deidentified_at   TIMESTAMPTZ,   -- NULL = not a DICOM, or not yet processed
    ADD COLUMN model_arm_id      UUID REFERENCES model_arms(id) ON DELETE SET NULL;  -- ▶︎ CHANGED

CREATE INDEX idx_evidence_files_model_arm_id ON evidence_files(model_arm_id);  -- ▶︎ CHANGED
```

`model_arm_id` is **nullable on purpose**: a generic lab report or a file not
yet tied to an arm has no owner. The face photo is **not** stored here — it is an
identity column on `applicants` (§C), never a model input.

`content_hash` is the input signature: it proves which exact bytes were scored.
`deidentified_at` records that the DICOM header was stripped and when.

**Files are stored on disk under `./data`, not in the database.** `storage_path`
holds a relative path. See [SPEC.md §12](SPEC.md).

---

## G. Scoring provenance

`composite_scores` records a number and a tier but not how either was produced.
[SPEC.md §7](SPEC.md) requires comparing expert-weighted against learned fusion,
which is impossible if the method is not recorded.

```sql
ALTER TABLE composite_scores
    ADD COLUMN method            VARCHAR(100) NOT NULL DEFAULT 'expert_weights_v1',
    ADD COLUMN tier_thresholds   JSONB NOT NULL DEFAULT '{}'::jsonb;
```

`tier_thresholds` stores the cut-points used **at the time of scoring**
(`{"low_max": 30.0, "moderate_max": 65.0}`). Thresholds are tenant-configurable
and will be tuned; without this snapshot, an old score cannot be explained later.

---

## H. Stuck-job recovery — recommended

Jobs run in-process via FastAPI `BackgroundTasks`, so an API restart strands
anything mid-flight in `status='processing'` forever.

```sql
ALTER TABLE applications ADD COLUMN processing_started_at TIMESTAMPTZ;
```

On startup the API resets anything obviously abandoned:

```sql
UPDATE applications
   SET status = 'submitted', processing_started_at = NULL
 WHERE status = 'processing'
   AND processing_started_at < now() - interval '1 hour';
```

Roughly ten lines, and it removes the main practical objection to not running a
broker.

---

## Optional — worth a discussion, not blocking

**`applicants.date_of_birth`.** A full date of birth is a strong quasi-identifier.
Underwriting only needs age. Storing `birth_year INTEGER` instead would be more
consistent with the no-name design and is a good line in the compliance chapter.
Only worth changing if it costs nothing now.

**`model_arms.preprocessing_version`.** [SPEC.md §4](SPEC.md) requires recording
preprocessing version alongside model version. It can ride inside the existing
`version` string, or become its own column. Either is fine — just pick one and be
consistent.

---

## Seed data needed for anyone to log in

Please ship a `db/seed.sql`:

- 2 tenants (proves isolation is real — with one tenant, a leak is invisible)
- 3 users: one `underwriter`, one `senior_underwriter`, one `admin`, with known
  dev passwords
- 1 `model_arms` row for the Phase 1 TB vision arm
- Default `notification_preferences` rows for each user

Two tenants matters more than it sounds: the isolation test is *"log in as tenant
A, try to fetch tenant B's application, expect nothing"*, and that test cannot
exist with a single tenant.

---

## Suggested migration order

Each is a separate Alembic revision so any one can be rolled back alone.

1. Auth columns (A) — unblocks login immediately
2. `tenant_id` columns + backfill + indexes (B)
3. RLS policies + non-superuser role (B) — separate from step 2 so it can be
   toggled independently while debugging
4. Intake fields (C)
5. Model output detail (D)
6. Audit payload + append-only triggers (E)
7. Evidence integrity (F)
8. Scoring provenance (G)
9. Stuck-job recovery (H)
10. Seed data

Steps 1–3 unblock login and security. Steps 4–9 unblock the intake form and the
scoring pipeline; I need 4, 5, 7 and 8 before the TB arm can store anything.
