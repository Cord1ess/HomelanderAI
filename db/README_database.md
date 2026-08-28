# HomelanderAI — Database

PostgreSQL 16 schema for the HomelanderAI decision-support platform. This is the database layer for the project described in the main [README.md](./README.md) and [SaaS Specification](./Software_project_proposal.pdf).

## Files

| File | Purpose |
|---|---|
| `schema.sql` | Full DDL — enum types, tables, constraints, indexes |

## Design principles

- **Multi-tenant isolation.** Every carrier-owned row (`users`, `applicants`, `applications`, `api_keys`, `notifications`) carries a `tenant_id`. Application-level queries must always filter by tenant.
- **Human-in-the-loop is structurally enforced.** `underwriter_decisions.underwriter_id` is `NOT NULL` and the table has a `UNIQUE` constraint on `application_id` — the schema makes it impossible to record a decision without a licensed underwriter attached, and impossible to have two conflicting final decisions on one application. The platform never writes an automated approval or denial into this table.
- **Model arms are pluggable.** `model_arms` is data, not code — new vision/NLP/tabular arms are added by inserting a row, matching the README's requirement that arms "can be added or removed without touching the pipeline."
- **Scoring is versioned, not overwritten.** `composite_scores` allows multiple rows per `application_id` (one per `version`), so a re-score after additional evidence is submitted doesn't destroy the original score — both remain in the audit trail.
- **Audit log is append-only.** `audit_log` is hash-chained (`payload_hash`, `prev_hash`); application code should only ever `INSERT` into this table, never `UPDATE` or `DELETE`.

## Entity overview

| Table | What it represents |
|---|---|
| `tenants` | Subscribing insurance carrier |
| `users` | Underwriters, senior underwriters, admins |
| `api_keys` | Per-tenant REST API credentials |
| `applicants` | The individual being underwritten (synthetic/de-identified) |
| `applications` | One evidence-package submission for one applicant |
| `evidence_files` | Uploaded DICOM scans, lab reports, clinical notes, questionnaires |
| `model_arms` | Registered AI models (vision / NLP / tabular) |
| `model_runs` | One execution of one arm against one application |
| `sub_scores` | Raw + calibrated score from one model run |
| `explanation_artifacts` | Grad-CAM overlays, SHAP breakdowns, annotated clinical text |
| `composite_scores` | Fused Composite Risk Score (CRS), versioned |
| `underwriter_decisions` | Final human decision — always required |
| `audit_log` | Append-only, hash-chained event record |
| `notifications` | In-app / email / SMS notifications sent to users |
| `notification_preferences` | Per-user, per-type channel opt-in/out |

## Known intentional denormalization

`composite_scores.tier` could theoretically be derived from `crs_value` at query time using the tiering matrix. It's stored directly instead, because the tiering thresholds are a business rule that may change over time — storing the tier at the moment of computation preserves what the applicant actually experienced, which matters for the audit trail and regulatory defensibility. This is a deliberate trade-off, not a normalization oversight.

## Setup

```bash
createdb homelander_ai
psql -d homelander_ai -f schema.sql
```

Requires PostgreSQL 16+ with the `pgcrypto` extension available (used for `gen_random_uuid()`).

## Normalization

Schema is verified to 3NF:

- **1NF** — every column holds a single atomic value; no repeating groups (e.g. each evidence file is its own row in `evidence_files`, not an array column on `applications`).
- **2NF** — every table has a single-column surrogate primary key (`id UUID`), so partial-key dependency is not possible.
- **3NF** — no non-key attribute depends on another non-key attribute. The one apparent exception (`composite_scores.tier`) is documented above as an intentional trade-off, not a functional dependency oversight.

## Not included in this schema (out of scope for capstone)

- Billing / subscription invoicing tables
- Full RBAC permission tables (role is a single enum column on `users` for now)
- Data retention / deletion job tracking

## Disclaimer

This schema supports an academic capstone project. No real patient or applicant data should ever be loaded into it. See the main project README for the full disclaimer on clinical validity and regulatory status.
