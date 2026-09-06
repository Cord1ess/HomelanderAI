# Phase 1 — implementation plan

**For:** me (the scoring pipeline owner).
**Scope:** evidence in → TB screening → risk score → underwriter sees it.
**Governed by:** [DESIGN_POLICY.md](DESIGN_POLICY.md). Every structural choice
below is justified against it.

---

## Status — 2026-09-01

| Piece | State |
|---|---|
| `scoring.py` — rules, CRS, tiers | **Done**, 18 tests |
| `intake.py` — DICOM de-identification, hashing | **Done**, 17 tests |
| `arms/` — registry + TB arm + learned scorer + Grad-CAM | **Done**, 19 tests |
| `pipeline.py` — evidence in, score out | **Done**, 11 tests |
| `audit.py` — hash chain + verifier | **Done**, 12 tests |
| TB model — trained and exported | **Done**, AUC 0.877 (internal) |
| Database persistence | **Done** — 11 ORM models, `persistence.py` |
| HTTP endpoints | **Done** — intake, queue, review, decision, audit, files |
| Dashboard wired to the API | **Done** — no screen runs on stub data |

106 tests passing. The whole path runs end to end: an application submitted
through the form is de-identified, stored, scored in the background, and shown
to an underwriter with the image, the heatmap, the findings that moved the
score, and the history rules that adjusted it.

**Two things the schema had wrong**, found the first time it was actually
executed against Postgres:

- `db/schema.sql` created an index on `evidence_files(model_arm_id)`, a column
  the table never had. Postgres aborts the whole file on that, so the schema had
  never once run — which is also why nothing had ever been tested against a real
  database.
- `applications` was missing `policy_term` and `models_requested`, both required
  by DATABASE.md §C and both already being sent by the intake form.

**Model status.** Logistic regression over TorchXRayVision's 18 findings,
trained on Shenzhen. AUC 0.877 (5-fold CV) against 0.772 for the hand-weighted
composite it replaced. **Internal validation only** — Montgomery is not
downloadable, so there is no external number. See SPEC §6.

Fast loop while developing (skips model inference, well under a second):

```bash
uv run pytest tests/test_scoring.py tests/test_intake.py tests/test_audit.py
```

Reproduce the model (features cache after the first run, then it is instant):

```bash
python scripts/fetch_tb_data.py shenzhen
python scripts/tb_experiment.py
```

---

## What Phase 1 delivers

An application submitted through the intake form is de-identified, stored,
screened by one vision arm, scored against declared history, given a tier, and
presented to an underwriter with visual evidence and a plain-language
explanation of what moved the number.

One arm. One condition. Whole path working end to end.

---

## The one structural decision

More arms are coming (NLP, tabular, and other conditions). That is a **stated
current requirement**, not speculation, so a seam is earned under
[DESIGN_POLICY.md](DESIGN_POLICY.md) §17. But it must be the smallest seam that
works.

**The seam is a function signature and a dictionary. That is all.**

```
An arm is:   a function that takes evidence and returns an ArmResult
The registry is:  a dict mapping arm name -> that function
```

Adding an arm later = one new module + one dict entry. Nothing else changes.

**Explicitly not doing:** no abstract base class, no `ArmFactory`, no plugin
loader, no dependency injection, no `BaseArm`/`AbstractArm` hierarchy. §2 and §7
name these directly. A dataclass and a dict give us everything a class hierarchy
would, with none of the indirection.

The database already supports this — `model_arms` is a registry table, so a new
arm is a row, not a migration.

---

## File layout

```
apps/api/app/
  intake.py         de-identify + store uploaded evidence
  arms/
    __init__.py     ArmResult dataclass + ARMS registry dict
    tb_xray.py      Phase 1 arm: chest X-ray screening
  scoring.py        findings + declared history -> CRS + tier
  pipeline.py       runs the arms, writes results, moves status
  audit.py          hash-chained audit log writes
```

Six files. Each has one job that can be stated in a sentence — the test from §6
for whether a split is real or cosmetic.

`scoring.py` stays separate from `arms/` on purpose: an arm answers *"what is in
this image"*, scoring answers *"what does that mean for this applicant"*. Those
change for different reasons and at different times.

---

## Commit 1 — Evidence in, stored safely

**Goal:** the intake form's POST works. Files land on disk, de-identified, with
their hashes recorded. Nothing is scored yet.

### Build

- `POST /api/applications` — multipart: applicant fields, coverage, declared
  history JSON, files
- `intake.py`:
  - DICOM → strip identifying header tags with `pydicom`, keep pixels and the
    clinically useful tags
  - Render to PNG for storage and display (no DICOM viewer needed downstream)
  - sha256 the stored bytes → `evidence_files.content_hash`
  - Write to `data/uploads/{tenant_id}/{application_id}/`
- `GET /api/files/:id` — serve a file, tenant-scoped
- Status → `submitted`

### Dependencies added here

`uv add python-multipart pydicom pillow sqlalchemy alembic psycopg`

Per the convention in `pyproject.toml`: added when the import is written, and
`uv.lock` committed alongside.

### Done when

- A DICOM upload produces a stored PNG whose header contains **no patient name**
- `content_hash` is populated and stable across re-reads
- A file belonging to tenant A returns 404 for tenant B
- Tests cover: de-identification actually strips tags, and cross-tenant access
  fails

**Verify by hand:** upload one of the reference project's sample X-rays from
`Reference/Nirnoy/assets/samples/`, then re-open the stored file and confirm the
tags are gone.

---

## Commit 2 — The TB arm runs

**Goal:** submitting an application triggers screening in the background, and
the findings land in the database with a heatmap.

### Build

- `arms/__init__.py` — the `ArmResult` dataclass and the `ARMS` dict
- `arms/tb_xray.py` — ported from `Reference/Nirnoy/backend/specialists/txrv.py`:
  - **Copy the preprocessing exactly.** Normalise to `[-1024, 1024]`,
    centre-crop, resize to 224. Their comment is not decoration — skip it and the
    model returns confident nonsense
  - **Use `densenet121-res224-all` weights.** Other weight sets have untrained
    labels that predict randomly
  - Load the model **once** at module level, not per request
  - Return all 18 findings in `details`, plus a TB-suggestive composite as the
    score
- Grad-CAM overlay → PNG → `explanation_artifacts`
- `pipeline.py` — `BackgroundTasks` runs the arm, writes `model_runs` +
  `sub_scores`, moves status `submitted → processing → scored`
- Startup recovery: reset applications stuck in `processing` (see
  [DATABASE.md §H](DATABASE.md))

### Dependencies added here

`uv add torch torchvision torchxrayvision grad-cam` (CPU wheels — the index is
already configured)

### Critical detail

The pipeline function must be `def`, **not** `async def`. FastAPI runs sync
background functions in a threadpool; an `async def` doing blocking inference
would stall the event loop and freeze the whole API.

### Done when

- Submitting an application produces a `model_runs` row that reaches `completed`
- `sub_scores.details` holds all 18 findings
- A Grad-CAM PNG exists and is servable
- An arm crash writes `status='failed'` with `error_message` set, and the
  application still resolves — no silent swallow (§12), no dead-end
- Killing the API mid-run and restarting recovers the stuck application

---

## Commit 3 — Score, tier, decision, audit

**Goal:** the underwriter sees a number, a tier, the reasons, and can record a
decision.

### Build

- `scoring.py`:
  - Vision composite → 0–100
  - Declared-history rules as **a list of small rule entries**, not branching
    code — adding a condition later is one list entry
  - Each rule that fires records its adjustment **and a plain-language reason**;
    those strings are what the review screen shows
  - CRS = clamped vision score + adjustments
  - Tier from thresholds, snapshotted into `composite_scores.tier_thresholds`
- Insufficient-evidence path: no X-ray, unreadable image, or arm failed →
  `insufficient_evidence`, no CRS invented
- `POST /api/applications/:id/decision`
- `audit.py` — hash-chained writes at every event, plus a verifier that walks
  the chain
- Notification row on completion

### The rules to port

From `Reference/Nirnoy/backend/fallback.py` and `prompts.py` — their record
rules, retargeted at underwriting:

| Condition | Effect |
|---|---|
| Prior TB, treatment completed, no current symptoms | **Lower** — post-treatment scarring, not active disease |
| Prior TB with current symptoms | **Raise sharply** — possible relapse |
| Diabetes | Raise — roughly 3× TB risk |
| HIV positive | Raise — major multiplier, atypical presentation |
| Household TB contact | Raise — documented exposure |
| Antibiotics without improvement | Raise — argues against pneumonia |
| Smoker, or age over 60 | Raise slightly — widen toward malignancy |

**The first two rows are the whole point.** Same X-ray, opposite conclusion
depending on history. That is the case the reference project was built to prove,
and it is what a pure image classifier structurally cannot do.

### Done when

- An application gets a CRS, a tier and a list of reasons
- The two prior-TB cases produce visibly different scores from the same image
- No path can produce a "reject" outcome — **assert this in a test**
- The audit chain verifies from the first row to the last
- Tampering with a payload breaks verification

---

## Not in Phase 1

NLP arm · tabular arm · calibration against a labelled set · SHAP · learned
fusion · bias audit · DICOM viewer · multiple conditions.

Each is real work with its own commit later. None is needed to prove the path.

---

## The honest part — read before starting

**Phase 1 ships a working pipeline with a weak vision signal, and that is the
correct order.**

TorchXRayVision has no TB label. The reference project's own validation scored
**−0.051 separation on labelled TB/Normal data — the wrong direction**
([SPEC.md §6](SPEC.md)). Their system works anyway because history and reasoning
carry much of the signal, which is exactly why the rules in Commit 3 matter as
much as the model in Commit 2.

So Phase 1 is genuinely useful — the history rules do real work — but the vision
half needs upgrading. The fix is **Commit 4: fine-tune a proper TB classifier**
on the labelled TB/Normal set the reference project already ships in
`Reference/Nirnoy/assets/samples/`.

Because of the seam, that upgrade **touches one file** — `arms/tb_xray.py`.
Nothing in intake, pipeline, scoring, audit or the dashboard changes. That is
the entire return on the seam, and it is why the seam is worth its small cost.

Calibration lands with that commit too: until there is a labelled test set,
`raw_score` and `calibrated_score` are equal, and the code should say so plainly
rather than implying a calibration that has not happened.

---

## Blocked on teammates

Cannot start Commit 1 until these land from [DATABASE.md](DATABASE.md):

- **C** — intake fields on `applications`
- **F** — evidence integrity columns
- **B** — `tenant_id` everywhere (needed to scope file access)

Cannot finish Commit 2 without **D** (`sub_scores.details`,
`model_runs.error_message`), or Commit 3 without **E** (audit payload) and
**G** (scoring provenance).

Seed data with **two tenants** is needed before the isolation tests mean
anything.
