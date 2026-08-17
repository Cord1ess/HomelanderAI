# HomelanderAI

A multi-tenant decision-support platform for life, health, and critical-illness insurance underwriting.

Carriers submit an applicant evidence package — medical imaging, clinical notes, and structured questionnaire or lab data. HomelanderAI runs it through an ensemble of specialised models and returns a Composite Risk Score with per-arm sub-scores, visual evidence, factor attribution, a recommended underwriting action, and an immutable audit record.

Every output is a **recommendation**. A licensed underwriter records the final decision, and their identity forms part of the audit trail. The platform never issues an automated denial.

---

## Status

**Early development.** No functional pipeline yet — the architecture and scope are specified, implementation has not started.

This is an academic capstone project. It is not a medical device, not clinically validated, and not intended for use in real underwriting decisions. See [Disclaimer](#disclaimer).

## The problem

Underwriters face **early-claim asymmetry.** An applicant may carry early-stage, asymptomatic pathology that passes a health questionnaire and a basic nurse screening. Underwritten at baseline rates, a few months of collected premium can be followed by a catastrophic critical-illness claim.

HomelanderAI surfaces findings associated with elevated near-term morbidity risk from evidence the carrier already collects, so that elevated-risk applications reach a human reviewer with the relevant evidence attached — and low-risk applications clear faster.

## How it works

```
Evidence package
      │
      ▼
Async job queue  ──►  Model arms (run independently)
                        ├─ Vision      chest radiograph classification
                        ├─ Clinical NLP  entity + assertion extraction
                        └─ Tabular     actuarial / mortality risk
                              │
                              ▼
                      Per-arm calibration
                              │
                              ▼
                        Score fusion  ──►  Composite Risk Score
                              │
                              ▼
              Tier recommendation + explanation artifacts
                              │
                              ▼
                Underwriter review  ──►  Audit record
```

Each arm implements a common interface (`preprocess → infer → calibrate → explain`) and is registered in a table, so arms can be added or removed without touching the pipeline.

### Recommendation tiers

| Tier | Recommendation | Human step |
|---|---|---|
| Low | Cleared for fast-track at baseline rates | One-click confirmation |
| Moderate | Approve with rate adjustment | Underwriter sets final rate |
| Elevated | Route to senior underwriter with full evidence pack | Mandatory senior review |
| Insufficient evidence | Request additional evidence | — |

## Explainability

Explainability is a product output, not a debug feature. If an arm cannot explain itself, it does not ship.

- **Grad-CAM overlays** on the source image, stored as artifacts keyed to the inference so the audit record reproduces exactly what the underwriter saw.
- **Factor attribution** over the fusion layer and the tabular arm, breaking the composite score into contributing features.
- **Annotated clinical text** showing extracted entity spans tagged by assertion status (`PRESENT` / `NEGATED` / `FAMILY_HISTORY` / `HYPOTHETICAL`), so a negated finding is never silently scored as a positive one.
- **Tamper-evident audit log** — an append-only, hash-chained record of model versions, weight hashes, preprocessing version, input digest, every sub-score, and the human decision that followed.

## Planned stack

| Layer | Choice |
|---|---|
| API | FastAPI, Python 3.12, Pydantic v2 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Object storage | MinIO (S3-compatible) |
| Async jobs | Redis-backed task queue |
| ML | PyTorch for training, ONNX Runtime for inference |
| Frontend | Next.js 15, TypeScript, Tailwind, shadcn/ui, TanStack Query |
| Imaging | pydicom, server-rendered overlays |
| Local dev | Docker Compose |

## Data and models

No real patient data is used at any stage. Development runs on public, de-identified research datasets and a synthetic applicant generator.

Model weights are sourced from published research releases, most of which are licensed for **non-commercial research use**. Dataset and model provenance is tracked in `docs/DATA_SOURCES.md` and `docs/MODEL_LICENSES.md`.

## Disclaimer

Research software. Not a medical device. Not clinically validated, and not approved by any regulatory body.

The models used here were developed and validated for **clinical screening in patient populations**. Applying them to an insurance applicant population to inform a financial decision is a change of both distribution and purpose, and their outputs should not be read as diagnoses or as clinically actionable findings.

Automated risk assessment and pricing in life and health insurance is a regulated activity in most jurisdictions, including as a high-risk application under the EU AI Act. Nothing in this repository is fit for deployment against real applicants.

## License

Not yet determined. Until a license is added, all rights are reserved.
