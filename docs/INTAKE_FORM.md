# Intake form — model-driven upgrade

**Branch:** `Dash/NewApplicant`
**Status:** In progress (implemented as of this writing per the workflow below).
**Read first:** [SPEC.md](SPEC.md) §1, [MODEL.md](Model.md), [DASHBOARD.md](DASHBOARD.md) §3, [DATABASE.md](DATABASE.md) §C. [DESIGN_POLICY.md](DESIGN_POLICY.md) governs *how*.

## What this is

The intake form (`apps/web/src/pages/intake/IntakePage.tsx`) moves from a fixed
TB-only questionnaire to a **model-driven** form. The operator picks which model
arms apply from a **vertical checkbox menu** ("click all that applicable"); each
selected model expands a **panel** with:

- an **instruction** telling the operator which **report/upload** must be
  submitted for that model (and the accepted file types), and
- that model's **risk-factor fields**.

The applicant + coverage sections stay model-agnostic at the top. Evidence is a
single dropzone, with each model's panel instructing which file to attach.

## Model registry

One **Chest X-ray** arm backs all three historical CXR entries (OpenCXR,
CheXpert, CXR-CVD) via **TorchXRayVision (DenseNet)** — see [SPEC.md §6](SPEC.md)
and [PHASE1_PLAN.md](PHASE1_PLAN.md). CXR-CVD is deferred; its cardio risk
factors ride on the single CXR panel.

| # | Tab (model) | Upload instruction (required unless noted) | Fields |
|---|---|---|---|
| 1 | **Chest X-ray** — TorchXRayVision (DenseNet) | Chest X-ray — `.dcm .png .jpg` | **Symptoms:** cough >2wk · weight loss · night sweats · haemoptysis · fever · **TB history:** prior TB (+ completed course), diabetes, HIV, household contact, antibiotics no improvement, smoker · **Cardio:** hypertension, high cholesterol, family heart disease |
| 2 | **Mirai** — breast / mammography | Mammogram, 4 views — `.dcm` | family history breast cancer · prior breast biopsy · BRCA/genetic result (`not tested / negative / positive`) — default-off, jurisdiction-gated per SPEC §10 |
| 3 | **HAM10000** — dermoscopy | Lesion photo — `.png .jpg` | skin type (I–VI) · prior skin cancer · body site |
| 4 | **EyePACS** — retinopathy / fundus | Retinal photo — `.png .jpg .dcm` | diabetes duration · hypertension · smoking |
| 5 | **BioBERT** — clinical NLP / EHR | Clinical note / physician report — `.pdf .txt` | *(none structured — reads the note)* |
| 6 | **XGBoost** — actuarial / tabular | **No report needed** — demographic form only | height cm · weight kg (→BMI) · alcohol · physical activity · occupation · smoking |
| 7 | **Neuro MRI** — 3D brain (MONAI) | Brain MRI — `.dcm` | memory concern · speech concern · mobility concern |

## Data model

Fields collected per selected model are stored as a **per-model-keyed**
`declared_history` JSONB on `applications`, alongside a `models_requested` array
telling the orchestrator which arms to run. See [DATABASE.md §C](DATABASE.md) —
**that section is the authority and every change there is highlighted `▶︎ CHANGED`**
so DB-doc edits are unmistakable.

## Workflow (small-chunk commits)

One atomic, build/lint-green commit per step. Each step is committed before the
next is started.

1. **Docs config** — this file (workflow + registry).
2. **DB markdown** — update `docs/DATABASE.md` §C: add `applicants.height_cm` /
   `weight_kg`, `applications.models_requested` / `policy_term` (plus the existing
   C columns), and rewrite `declared_history` to the per-model shape. Every change
   marked `▶︎ CHANGED`.
3. **Schema** — mirror those columns into `db/schema.sql` (`applicants`,
   `applications`). `evidence_file_type` enum unchanged (modality recorded in file
   metadata, not a new enum).
4. **Form** — restructure `IntakePage.tsx` in one coherent commit (the registry,
   vertical checkbox menu, `selectedModels`/`modelFields` state, `ModelPanel`
   pop-outs with per-model instructions + fields, XGBoost fields-only, extended
   `FILE_TYPES`, and required-upload gating all share the single file, so they
   are committed together rather than as artificial partial states).
5. ~~**Form panels**~~ — folded into step 4 (same file).
6. ~~**Form evidence/gating**~~ — folded into step 4 (same file).
7. **Screen spec** — rewrite `DASHBOARD.md` §3 for the model-selector design.

Verification before each commit: `npm run lint` · `npm run typecheck` ·
`npm run build` (in `apps/web`).

## Out of scope

- Backend `POST /api/applications` — owned by [PHASE1_PLAN.md](PHASE1_PLAN.md)
  Commit 1; the form keeps its submission stub and just builds the new payload.
- Reconcile [MODEL.md](Model.md) hub-and-spoke architecture vs
  [DESIGN_POLICY.md](DESIGN_POLICY.md) / [SPEC.md](SPEC.md) (BackgroundTasks, no
  broker). The form spans models regardless of how the backend orchestrates them.
