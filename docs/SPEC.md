# HomelanderAI — Working Specification v1

**Status:** Living document. Supersedes `Idea.md` for anything the two disagree on.
[DESIGN_POLICY.md](DESIGN_POLICY.md) governs *how* things get built and overrides this document on implementation choices; this one stays the authority on *what* gets built.
**Context:** Academic capstone / thesis. Team of 2–5. ~3–6 month horizon. Local compute only, no cloud spend.

How to read this:

| Marker | Meaning |
|---|---|
| **LOCKED** | Carried over from `Idea.md` as solid. Do not relitigate without a written ADR. |
| **REVISED** | The idea survives, but the original form was wrong or infeasible. New form given. |
| **CUT** | Removed from v1. Reason given. May return post-thesis. |
| **DECIDE** | Waiting on your call. Listed in §15. |

---

## 1. Product Definition — REVISED

HomelanderAI is a **multi-tenant B2B decision-support platform for life, health, and critical-illness underwriting.** Subscribing carriers submit applicant evidence packages (medical images, clinical text, structured questionnaire/lab data) through a web portal or REST API. The platform runs an ensemble of specialised models and returns, for each applicant:

- a **Composite Risk Score (CRS)** with per-arm sub-scores and calibrated confidence,
- **visual evidence** (Grad-CAM overlays on the source image),
- **factor attribution** explaining what moved the score,
- a **recommended underwriting action**, and
- an **immutable audit record** of the whole inference.

### The one framing change that matters

`Idea.md` describes an *"AI-Driven Automated Underwriting Gateway"* that issues policies instantly and auto-adjusts premiums. **Change this to decision support with mandatory human sign-off.** Every output is a *recommendation*; a licensed underwriter records the final decision in the system, and their identity is part of the audit record.

Why this is not just hedging:

- **It is what makes the thesis defensible.** EU AI Act Annex III §5(c) classifies AI for *risk assessment and pricing in life and health insurance* as high-risk. GDPR Art. 22 gives a person the right not to be subject to a solely-automated decision with significant effect on them. A system that auto-issues and auto-prices walks straight into both. A system that produces a reviewed recommendation is a well-understood, lawful pattern.
- **It costs you nothing.** The pipeline, models, scores, heatmaps, and UI are identical. Only the wording of the tier actions and one extra "underwriter decision" table change.
- **It removes the hardest question at your defence**, which is otherwise "what happens when your model is wrong about a real person's insurability?"

Keep the *speed* claim — Tier 1 becomes "cleared for fast-track, one-click underwriter confirmation." That still delivers the business value in `Idea.md` §2.

**No tier may ever output an automated denial.** The system's escalation path is human review, never rejection. This is stated in `Idea.md` §5 already ("avoids automated denial") — it is now a hard invariant enforced in code and tests.

---

### The operating flow — LOCKED

How the product is actually used, end to end. Two separate sessions, and the
client is only present for the first one.

**Session 1 — intake, client in the room, a few minutes**

1. Operator logs into their carrier's dashboard.
2. Clicks **"Review a new client"**, opening an intake form.
3. Records who the applicant is and what cover they are asking for, plus
   declared medical history.
4. Uploads the medical documents the client brought.
5. Submits. The application status becomes **evaluation pending**.
6. Operator tells the client they will hear back in **1–2 business days**.
   The client leaves.

**Unattended — the platform works alone, hours**

7. Intake pipeline de-identifies the uploads and stores only what is needed
   (§9).
8. Model arms run against the evidence and a score is produced.
9. The result sits and waits for a person.

**Session 2 — review, no client present**

10. An underwriter opens the completed evaluation, reads the score, heatmap and
    factor breakdown, and records the actual decision.
11. The applicant is notified.

**The turnaround promise is an architectural fact, not a detail.** 1–2 business
days means nothing in this system is latency-sensitive. No streaming, no
progress bars, no fast-inference requirement — a CPU model taking three minutes
is entirely acceptable. This is the justification for background jobs over a
broker (§12), and it is why the live-streaming design in the Nirnoy reference is
explicitly *not* copied.

It also means **the operator and the underwriter are different moments, and may
be different people.** Intake is a data-entry surface; review is a
decision-support surface. Do not merge them into one screen.

---

## 2. Problem Statement — LOCKED

**Early-Claim Asymmetry.** Applicants may carry early-stage, asymptomatic pathology that passes questionnaires and basic nurse screening. If underwritten at baseline rates, a few months of premium can be followed by a catastrophic critical-illness claim. The asymmetry between premium collected and claim paid is the loss the platform exists to reduce.

This is a real, well-posed insurance problem and it is the strongest part of the original document. Keep it, keep the worked example, but **label the currency figures as illustrative** — they are not actuarial pricing and should not be presented as such.

**REVISED — drop the "1-to-5-year disease progression horizon" claim** as a blanket property of the platform. Only a small number of models make calibrated time-horizon predictions (Mirai for 5-year breast cancer risk; the CXR-Age / CXR-Lung-Risk family for longitudinal risk). The models you can realistically ship detect *current findings*. Claiming a progression horizon the models were not trained to produce is the kind of overreach an examiner will find. State it accurately: *"detects findings associated with elevated near-term morbidity risk."* Add horizon claims back only for arms that genuinely support them.

---

## 3. Stakeholders — REVISED

| Role | Status | Note |
|---|---|---|
| Chief Risk / Underwriting Officers, Actuarial Directors | **LOCKED** as buyer persona | Drives the portfolio-level dashboard requirement |
| Medical Underwriters | **LOCKED** as primary operator | The whole UI is built for this person |
| Claims Adjusters | **CUT from v1** | Claims is a different product surface. Adding it doubles the domain model for no thesis gain. |
| Applicants (self-service portal) | **CUT from v1** | An applicant-facing surface adds consent flows, auth, and an adverse-action UX you do not have time for. Applicants are affected parties, not users. |

Keep applicants in the **ethics and compliance chapter** as the party whose interests you designed around — that is where they belong in a thesis.

---

## 4. Non-Negotiable System Properties — LOCKED

These four came through from `Idea.md` and are the architectural backbone. Everything else is negotiable.

1. **Multi-tenancy.** Carriers are isolated tenants. Every row of applicant data carries a tenant ID; every query is tenant-scoped. Cross-tenant leakage is the one bug that invalidates the entire product.
2. **Asynchronous job pipeline.** Inference is slow and bursty. Submission returns a job handle immediately; results are polled or pushed. This was right in the original and stays.
3. **Explainability is a first-class output, not a debug feature.** A score with no evidence is unusable to an underwriter and indefensible to a regulator. If an arm cannot explain itself, it does not ship.
4. **Immutable, replayable audit trail.** For every inference: model identities and versions, weight file hashes, preprocessing version, input digest, all sub-scores, the fusion output, and the human decision that followed.

---

## 5. Scope for v1

### In

- Tenant + user management, API keys, role-based access (Underwriter / Senior Underwriter / Tenant Admin).
- Evidence package upload: DICOM and standard images, clinical text, structured JSON/CSV.
- Async inference orchestration over the model arms (§6). **Phase 1 ships one
  arm only: chest radiograph screening for tuberculosis**, carried over from the
  Nirnoy reference project. The NLP and tabular arms follow once that path is
  proven end to end.
- Score fusion with calibration, and the tier recommendation.
- Underwriter review workspace: image + heatmap viewer, attribution panel, decision capture.
- Hash-chained audit log with an export view.
- Bias / subgroup performance report (§11).
- Synthetic applicant generator and a **mock inference mode** so the whole product demos with no GPU.

### Out

Kubernetes. Microservices. Billing and subscription management. Real-time streaming. Mobile apps. A trained-from-scratch model. Claims. Applicant portal. Blockchain anything. Federated learning. On-prem installer. SSO/SAML.

Each of these is a plausible sentence in a pitch deck and a month of your timeline.

---

## 6. Model Stack — REVISED (this section had the most errors)

`Idea.md` §4 lists eight arms. Several entries name **datasets or frameworks as if they were models**, which will be spotted immediately:

| `Idea.md` entry | What it actually is |
|---|---|
| CheXpert | A Stanford chest X-ray **dataset**, not a model |
| EyePACS | A diabetic retinopathy **dataset** (Kaggle DR challenge) |
| HAM10000 | A dermoscopy **dataset** (Harvard Dataverse / ISIC) |
| MONAI 3D | A medical-imaging **framework**, not a model |
| OpenCXR | A CXR preprocessing **toolkit** |
| RetinaGuard | No such model could be identified — likely a placeholder name |

Independently: eight arms across mammography, CXR, CT, fundus, 3D brain MRI, and dermoscopy is not a 3–6 month project for 2–5 people on local hardware. Loading eight model families, each with its own preprocessing, is alone more work than your timeline allows.

### Recommended v1 arms: three, chosen for open licensing, small inputs, and CPU feasibility

**Arm A — Chest radiograph (vision).**
Use **TorchXRayVision** (`pip install torchxrayvision`). Pretrained DenseNet-121 multi-label classifiers over 14+ pathologies, permissively licensed, small inputs (224², single-channel), runs acceptably on CPU. This is the single highest-leverage swap in this document: it replaces "CheXpert / OpenCXR" with something you can have producing real scores in an afternoon. Data: **NIH ChestX-ray14** (fully open, no agreement) as the default; CheXpert if someone completes Stanford's registration; MIMIC-CXR only if a team member already holds PhysioNet credentialing, since CITI training adds 1–2 weeks.

**Arm B — Clinical text (NLP).**
**LOCKED in principle** — `Idea.md` was right that a text arm belongs here. **REVISED in execution:** a bare BioBERT classifier is not enough. Build it as **biomedical NER + assertion detection**: `scispacy` for entity extraction, `medspaCy`/`negspaCy` for negation and hypothetical/family-history assertion, then a PubMedBERT or BioBERT classification head over the asserted findings.

The negation layer is not optional. *"No family history of BRCA1 mutation"* and *"BRCA1 mutation confirmed"* are near-identical token sequences with opposite underwriting meaning. A model that fires a risk flag on the first is the most embarrassing possible demo failure, and handling it properly is a genuinely presentable technical contribution.

**Arm C — Structured / actuarial (tabular).**
**LOCKED** — XGBoost is the right call. The gap `Idea.md` does not address is *what label you train on*, since you have no real underwriting outcomes. **Use NHANES plus the CDC/NCHS Linked Mortality Files**: public, free, demographics + exam + lab features with real mortality follow-up. That gives you a legitimately trained mortality-risk model instead of a model fitted to invented labels, and it is defensible in a thesis in a way synthetic labels never are.

### Phase 1 is TB, and there is a catch — READ THIS

Phase 1 reuses the Nirnoy reference project's chest X-ray path for tuberculosis
screening. The reusable engineering is real, but one assumption does not hold:

**TorchXRayVision has no tuberculosis label.** It was never trained to detect
TB. It reports 18 general findings — consolidation, nodule, fibrosis, effusion
and so on. Nirnoy's own `check_labelled.py` builds a hand-weighted "TB
suggestive" composite out of those findings, and their README reports the
result honestly: on a labelled TB/Normal set the composite achieved
**−0.051 separation — the wrong direction.** Histogram equalisation and CLAHE
both failed to rescue it. The two classes came from different sources, so this
is textbook cross-dataset domain shift, exactly the risk named in §10.

Nirnoy still works because a language model reasons over *findings plus patient
history* rather than trusting the classifier. Their pipeline never claims the
vision model detects TB.

So Phase 1 has to pick one of three routes:

| Route | What it means | Cost |
|---|---|---|
| **A — Fine-tune a real TB classifier** | Train on a labelled TB/Normal chest X-ray set. Produces a genuine, calibratable TB probability and a Grad-CAM that points somewhere meaningful. | Most work; also the most defensible, and gives a real evaluation chapter |
| **B — Findings as features** | Keep TorchXRayVision as-is; feed its 18 findings plus declared history into the fusion layer as evidence, and never label the output "TB". | Least work; honest, but weak on its own given the validation result |
| **C — Adopt Nirnoy's LLM synthesis** | Port the reasoning step. Strong with free-text history. | Needs an API key and internet, or a multi-GB local model. Non-deterministic and uncalibratable — see §15 |

**Recommendation: A, with B as the fallback path when the classifier abstains.**
Route A is what turns "we reused a reference project" into "we trained and
evaluated a model", which is the difference the thesis needs. Whichever is
chosen, **the honest framing stays: an abnormal film is grounds for
escalation, never a diagnosis.**

For underwriting the question is not "does this person have TB" — it is
**"is there an undisclosed condition that changes the risk"**, and that is a
screening question a human then resolves.

### Deferred arms

| Arm | Why deferred |
|---|---|
| Mammography (Mirai, NYU DeepMammo) | Weights sit behind institutional agreements with multi-week lead times. Mammography DICOMs are large with exacting preprocessing. Highest effort-to-payoff ratio in the list. |
| 3D brain MRI (MONAI) | Volumetric inference on local hardware is slow and memory-hungry. Single worst fit for your compute constraint. |
| Fundus / diabetic retinopathy | Actually a decent fit — small images, open APTOS/EyePACS data. **The first arm to add if you finish early.** |
| Dermoscopy (HAM10000) | Also a good fit. Note HAM10000 is CC BY-NC-SA — fine for a thesis, blocks commercial use. **Second candidate for expansion.** |
| CXR-CVD / CXR-Age (MGH) | Genuinely interesting because it *does* make longitudinal claims. Stretch goal for Arm A. |

### The architectural rule that makes this safe

Define one `RiskModelArm` interface — `preprocess → infer → calibrate → explain → ArmResult` — and register arms in a table. Adding or dropping an arm becomes a registry entry, not a refactor. Ship three, and if the project runs hot you can add a fourth in days; if it runs cold you drop to two without touching the pipeline. **Build this interface in week 3, before the second model exists.**

### Licensing reality — flag it now, not at submission

Nearly all of these weights are released for **non-commercial research use**. That is fine for a capstone with proper attribution, and it is a genuine blocker for the commercial product `Idea.md` describes. Maintain `docs/MODEL_LICENSES.md` from day one listing each arm's source, licence, and permitted use. Examiners ask. Buyers ask harder.

---

## 7. Risk Scoring — REVISED

`Idea.md` §5 proposes:

```
CRS = 0.50 × Vision + 0.30 × NLP + 0.20 × Actuarial
```

Two problems.

**First, the inputs are not commensurable.** Raw neural-network output scores are not probabilities and are not comparable across models. A 0.7 from a DenseNet CXR head and a 0.7 from XGBoost mean different things, and summing them is arithmetic without meaning. **Fix: calibrate every arm independently** (Platt scaling or isotonic regression on a held-out split) so each arm emits a genuine probability, then fuse. Report Brier score and expected calibration error per arm. This is cheap to implement and it is the difference between a real risk score and a plausible-looking number.

**Second, the weights are asserted, not derived.** Where does 0.50 come from?

Do not delete the formula — **promote it to a baseline** and make the comparison your contribution:

- **Model E (expert):** the fixed 0.50 / 0.30 / 0.20 weighting from `Idea.md`.
- **Model L (learned):** a deliberately interpretable fusion layer — regularised logistic regression, or a depth-2 GBM — trained on the calibrated arm outputs.

Then evaluate both on discrimination, calibration, and subgroup fairness. *"We compared expert-weighted against learned fusion for multimodal underwriting risk"* is a thesis chapter. *"We picked some weights"* is not. It also gives you an honest fallback: if Model L does not beat Model E on your data, that is a finding, not a failure.

**Tier boundaries — REVISED.** Keep the three-tier structure; it is sound. Change two things:

- The 0–30 / 30–65 / 65–100 cut points are placeholders. **Derive them from the operating characteristic** you want — pick the Tier 3 threshold from the sensitivity your cost model demands, then justify it. Store thresholds as tenant configuration, not constants.
- **Add a fourth outcome: `INSUFFICIENT_EVIDENCE`.** When a required arm is missing, fails, or returns low confidence, the system must say so rather than scoring on partial input. `Idea.md` has no path for a corrupt DICOM or an empty physician note, and in practice that is a large fraction of real submissions.

Tier actions, restated under §1's framing:

| Tier | Range | Recommendation | Human step |
|---|---|---|---|
| 1 — Low | 0.0–30.0 | Cleared for fast-track at baseline rates | One-click underwriter confirmation |
| 2 — Moderate | 30.1–65.0 | Approve with rate adjustment; wellness-plan incentive eligible | Underwriter reviews and sets final rate |
| 3 — Elevated | 65.1–100.0 | Route to senior underwriter with full evidence pack | Mandatory senior review. **Never an automated denial.** |
| — | any | Insufficient evidence | Request additional evidence |

---

## 8. Explainable AI — REVISED

`Idea.md` §6 is the most valuable section in the original document and needs the least conceptual change — but one item is technically wrong.

**Grad-CAM heatmaps — LOCKED.** Use `pytorch-grad-cam`. Overlay on the source image, served alongside the score. Store the overlay as a generated artifact keyed to the inference ID so the audit record can reproduce exactly what the underwriter saw.

**SHAP factor breakdown — REVISED.** The worked example in `Idea.md` ("60% driven by the mammography flag, 25% by the BRCA mention, 15% by age/lifestyle") is presented as SHAP output, but it is just the hand-set fusion weights restated. SHAP over a fixed linear combination returns the coefficients — it tells you nothing you did not type in yourself.

This becomes real once §7's learned fusion layer exists: SHAP over Model L is meaningful, and SHAP over the XGBoost arm is meaningful and standard. Apply it at two levels — **within** the tabular arm (which features drove that sub-score) and **across** arms (which arm drove the CRS). Until Model L exists, label the cross-arm view honestly as "configured weights," not attribution.

**BioBERT explanation — REVISED.** Skip token-level saliency heatmaps. Show the **extracted entity spans with their assertion status** — highlight the phrase in the source note, tagged `PRESENT` / `NEGATED` / `FAMILY_HISTORY` / `HYPOTHETICAL`. This is more useful to an underwriter, more honest about what the model did, and easier to build than integrated gradients. It also puts the negation handling from §6 on screen.

**Immutable audit log — LOCKED, with a concrete mechanism.** `Idea.md` asserts immutability without saying how. Use an **append-only Postgres table with a hash chain**: each row stores `sha256(previous_row_hash || canonical_payload)`. Verification walks the chain. No `UPDATE` or `DELETE` grant on the table for the application role; database triggers reject both. This gives credible tamper-evidence in roughly a day of work, needs no external service, and is straightforward to explain in a defence. It is *tamper-evident*, not *tamper-proof* — say so precisely rather than overclaiming.

---

## 9. Data Strategy

### Intake and PII minimisation — LOCKED

Evidence arrives as files a client handed over in person. Before anything is
stored, the intake step strips identifiers:

- **A DICOM file is pixels plus a header**, and the header is the risk — it
  routinely carries patient name, date of birth, patient ID, referring
  physician and institution. Strip those tags on the way in with `pydicom`.
  Keep the pixel data and the small set of clinically useful tags (modality,
  body part, view position, acquisition date).
- **Store only the de-identified copy.** The original is never written to disk.
- **The database holds the carrier's own reference**, never a name lifted from
  a file header. The schema already enforces this: `applicants` has
  `external_ref`, `date_of_birth` and `sex`, and deliberately **no name
  column**.
- Clinical notes get the same treatment — strip obvious identifiers before the
  text reaches the NLP arm.

This is roughly thirty lines of code. **Do not build a "PII framework" around
it** ([DESIGN_POLICY.md](DESIGN_POLICY.md) §2). It is one function in the
intake path, and it is a strong, concrete point for the compliance chapter
(§10).

You will not have real carrier applicant files, and you must not seek them.

**Build a synthetic applicant generator in week 1–2.** It stitches a public image, a template-generated clinical note, and a sampled demographic/lab row into a plausible applicant package with a known ground-truth label. This unblocks the entire team before a single model works: backend gets fixtures, frontend gets realistic data, ML gets an integration target, and your demo is reproducible on any machine.

Rules:

- Public, de-identified, properly licensed datasets only. Every dataset gets an entry in `docs/DATA_SOURCES.md` with its licence and access terms.
- `/data` is gitignored. A `scripts/fetch_data.py` documents acquisition instead. Never commit medical images.
- Synthetic notes must be clearly watermarked as synthetic in the content itself.
- Split by patient, never by image. Same-patient leakage across train/test is the most common silent error in medical imaging work and it inflates every number you report.

---

## 10. Compliance and Ethics — NEW, and treat it as a first-class chapter

`Idea.md` §6 frames explainability as a regulatory feature, which is the right instinct but stops short. The legal exposure here is the most interesting thing about this project, and addressing it directly converts your biggest weakness into a differentiated chapter. Cover at minimum:

- **EU AI Act.** Annex III §5(c) — life and health insurance risk assessment and pricing is high-risk. Walk through the obligations (risk management, data governance, technical documentation, logging, human oversight, accuracy/robustness) and map each to a component you actually built. Your audit log, model registry, and human-in-the-loop design are direct answers.
- **GDPR.** Art. 9 (health data is a special category — what is your lawful basis?), Art. 22 (automated decision-making — resolved by §1's framing), and the data-minimisation tension in a product that ingests entire medical images.
- **Genetic information — the sharpest issue, and `Idea.md` walks into it.** The BioBERT example explicitly extracts a *BRCA1 mutation flag*. That is genetic information, and it is the most heavily restricted category in insurance underwriting: GINA in the US, an outright ban on its use in life/disability/long-term-care underwriting in several US states, statutory or moratorium-based restrictions across the UK, Canada, and much of the EU. **Recommendation: keep genetic-marker extraction in the system but behind a per-tenant policy flag, default off, with the jurisdictional restriction documented.** Then write about it. A system that knows what it is legally forbidden to use is a much stronger artifact than one that quietly uses everything.
- **Off-label model use.** Every model you use was validated for *clinical screening in a patient population*. You are applying it to an *insurance applicant population* to inform a *financial* decision. That is distribution shift plus a change of purpose, and it is a real limitation. Name it in your limitations section before an examiner names it for you.
- **Local regulator.** The BDT figures suggest Bangladesh — cover IDRA's position and the local data-protection posture. Examiners reward jurisdiction-specific work.
- **Adverse-action transparency.** If a recommendation harms an applicant's terms, what are they told? Answer it, even if the answer for v1 is "the underwriter communicates, and the platform supplies the factor breakdown."

---

## 11. Evaluation Plan

Your business claim is about avoided losses, so do not stop at AUROC.

- **Per-arm discrimination:** AUROC and AUPRC. AUPRC matters more — these conditions are rare and AUROC flatters imbalanced problems.
- **Calibration:** reliability diagrams, Brier score, expected calibration error, per arm and for the fused CRS. Directly justifies §7.
- **Fusion comparison:** Model E vs Model L across all of the above.
- **Subgroup / bias audit — highest-value single addition to this project.** Report per-arm and fused performance sliced by age band and sex, plus any additional attribute your datasets carry (Fitzpatrick skin type if you add dermoscopy; NHANES carries race/ethnicity and income). Report the *gaps*, not just the aggregates. A medical-underwriting AI with no fairness analysis is not a complete thesis, and a documented disparity you found and reported is worth more than a suspiciously clean number.
- **Cost-sensitive utility — this is the metric that tests your actual thesis.** Build a simple expected-value model: cost of a missed high-risk applicant (early claim paid) versus cost of a false escalation (underwriter hours, lost customer, reputational drag). Sweep the tier thresholds and plot net benefit. This is what turns §2's story into a measured result, and it is the graph a CRO would actually look at.
- **Latency and throughput** per arm on your real local hardware, since compute is a stated constraint. Include CPU-only numbers.
- **Ablations:** each arm alone, and all pairs. Shows whether multimodality earns its complexity — and if one arm contributes nothing, that is a legitimate finding to report.

---

## 12. Recommended Tech Stack

Rationale first, alternatives noted. Confirm or override in §15.

### Backend

| Concern | Recommendation | Why |
|---|---|---|
| API | **FastAPI**, Python 3.12 | `Idea.md` had this right. Async, OpenAPI generation for free, Pydantic validation, same language as the ML stack. No reason to churn. |
| Validation / schemas | **Pydantic v2** | Source of truth for the API contract. |
| ORM / migrations | **SQLAlchemy 2.0 + Alembic** | Migrations from commit one. Retrofitting them onto a live schema is miserable. |
| Database | **PostgreSQL 16** (Docker) | Relational core plus `JSONB` for heterogeneous model outputs, which vary per arm. Row-level tenant scoping. |
| Object storage | **Local filesystem** under `./data` | Superseded MinIO. Uploads and heatmap artifacts are written to disk and served through an authenticated FastAPI route — better access control than presigned URLs, and one fewer service. See [DESIGN_POLICY.md](DESIGN_POLICY.md) §9. |
| Background jobs | **FastAPI `BackgroundTasks` + a `jobs` table in Postgres** | Superseded Celery + Redis. Inference genuinely cannot run inside a request, but a broker is not the only way to solve that. Define the worker as `def` rather than `async def` and FastAPI runs it in a threadpool, so blocking inference will not stall the event loop; the frontend polls `/api/jobs/{id}`. **Zero new services.** Accepted limits: in-flight jobs are lost on restart, and this will not scale past one machine — neither matters for a capstone, and introducing Celery later is a contained change. See [DESIGN_POLICY.md](DESIGN_POLICY.md) §2, §19. |
| Auth | **Own JWT + hashed API keys** in Postgres; Argon2id for passwords | Auth0/Clerk means cloud spend, and their tenant models fit awkwardly here. Multi-tenant API-key auth is ~200 lines and you control it. |
| Inference runtime | **PyTorch** for development, **ONNX Runtime** for serving | ONNX export plus CPU int8 quantisation is the difference between a demo that runs on a laptop and one that does not. Do this per arm once it is trained. |
| Logging | **stdlib `logging`** for now; revisit structured logging when the audit trail lands | structlog was dropped — it cost a dependency and a module to print two lines uvicorn already logs. **The rule that matters is unchanged: applicant evidence is PHI-shaped, so never log note text, pixel data, or raw model inputs — log identifiers and let the audit trail carry the rest.** |
| Testing | **pytest** + `httpx.AsyncClient`; Postgres via Docker Compose | Add one test asserting no tier can emit a denial, and one asserting cross-tenant queries return empty. |

**Do not build a separate model-serving tier.** No TorchServe, no Triton, no BentoML. Load models once at application startup and hold them in process. A serving tier is one more thing to run, one more failure mode, and buys you nothing at your scale.

### Frontend

| Concern | Recommendation | Why |
|---|---|---|
| Framework | **Next.js 15** (App Router) + TypeScript | Strong defaults, good DX, easy local dev. |
| Styling / components | **Tailwind CSS + shadcn/ui** | You have no designer. shadcn gives a professional-looking, accessible component set you own the source of, and a dense data UI is exactly its strength. |
| Server state | **TanStack Query** | Job polling, cache invalidation, and loading states are most of this app's frontend complexity, and this handles all three. |
| Charts | **Recharts** | Sufficient for score breakdowns, reliability diagrams, and the portfolio dashboard. |
| Type safety across the boundary | **`openapi-typescript`** generating TS types from FastAPI's OpenAPI schema | With backend and frontend on different people, this is what stops a week of contract drift. Wire it into CI. |
| Medical image viewing | **Start with server-rendered PNG + heatmap overlay.** Add **Cornerstone3D** only if time permits. | `Idea.md` specifies a browser DICOM viewer. Cornerstone3D is the correct library, and it is also a genuine multi-week integration. Server-side rendering via `pydicom` + Pillow gets you a working, demoable viewer in about a day. Treat the real viewer as a stretch goal, not a dependency. |
| E2E | **Playwright**, one happy path | Guards your demo script against regression the week before submission. |

### Infrastructure

**Docker Compose only.** Services: `api`, `worker`, `web`, `postgres`, `redis`, `minio`. One `docker compose up` must bring the whole product to life on any team member's machine, and getting that right in week 1 pays back constantly. No Kubernetes — at your scale it is pure cost.

`pydicom` for DICOM parsing. Never write your own parser; the format will consume the project.

`uv` for Python dependency management (fast, lockfile-based) — or Poetry if the team already knows it. `pnpm` for the frontend.

### Repository layout

Monorepo. You control git, so structure it for readable history.

```
/apps
  /api          FastAPI app: routes, auth, tenancy, persistence
  /worker       job runner, arm orchestration
  /web          Next.js underwriter portal
/packages
  /ml           RiskModelArm implementations, calibration, fusion, XAI
  /schemas      Shared Pydantic models + generated TS types
/infra          docker-compose, Dockerfiles, init SQL
/notebooks      Training, evaluation, bias audit (thesis figures)
/scripts        fetch_data.py, generate_synthetic_applicants.py
/docs
  /adr          Architecture Decision Records
  MODEL_LICENSES.md
  DATA_SOURCES.md
/data           gitignored
```

`packages/ml` must be importable and testable **without** the API running. Your ML people should never need Docker to iterate on a model.

### Team split for 2–5

| Owner | Surface |
|---|---|
| Backend / infra | FastAPI, Postgres, job runner, tenancy, audit log, Compose |
| ML — vision | Arm A, Grad-CAM, ONNX export, calibration |
| ML — text + tabular | Arms B and C, fusion layer, SHAP |
| Frontend | Portal, viewer, attribution UI, dashboard |
| Floating (5th) | Synthetic data generator, evaluation harness, bias audit, compliance chapter, thesis writing |

With 2–3 people, merge ML into one role and have the backend owner take the frontend. The `RiskModelArm` interface and the generated OpenAPI types are what make this split work — they are the two contracts that let people work without blocking each other. Land both early.

---

## 13. Roadmap

| Phase | Weeks | Outcome |
|---|---|---|
| **0 — Foundations** | 1–2 | Repo skeleton, Compose up, Postgres schema + migrations, ADRs for §15 decisions, synthetic applicant generator, OpenAPI contract agreed. |
| **1 — Walking skeleton** | 3–6 | End-to-end with **mock models**: upload → job → fake scores → tier → underwriter review → audit row. `RiskModelArm` interface defined. **The product is fully demoable at week 6 with zero real ML.** This is the most important milestone in the plan — it de-risks everything downstream and guarantees you have something to show. |
| **2 — First real arm** | 7–12 | Arm A live via TorchXRayVision. Real DICOM ingest, Grad-CAM, calibration, ONNX export. One arm working properly beats three half-wired. |
| **3 — Multimodal** | 13–18 | Arms B and C. Fusion Model E and Model L. SHAP. Insufficient-evidence path. |
| **4 — Evaluation and hardening** | 19–22 | Hash-chained audit log verification, bias audit, cost-utility sweep, all thesis figures, Playwright happy path, demo script. |
| **5 — Buffer** | 23–24 | Writing, stretch goals (fourth arm, Cornerstone3D), rehearsal. |

Two rules that matter more than the schedule: **the mock-mode demo must never break**, and **buffer is not spare capacity**. If you are behind at week 18, cut Arm C to a stub — a thoroughly evaluated two-arm system with a real fairness analysis scores better than three arms with no evaluation.

---

## 14. Do / Don't

### Do

- Reframe to decision support with mandatory human sign-off (§1). Everything else in §10 gets easier.
- Build the synthetic generator and mock mode first. Unblocks the whole team; guarantees a demo.
- Define `RiskModelArm` before the second model exists.
- Calibrate every arm before fusing anything.
- Handle negation and assertion in the text arm. Demo it explicitly.
- Keep the fixed-weight formula as a labelled baseline and compare against learned fusion.
- Record model name, version, weight-file hash, and preprocessing version on every inference row. This is what `Idea.md` §6 promised, and it is a small table.
- Hash-chain the audit log and write the verifier.
- Add `INSUFFICIENT_EVIDENCE` as a real outcome.
- Run the subgroup bias audit and report the gaps you find.
- Split data by patient, not by image.
- Write the compliance chapter as a contribution, not a disclaimer.
- Generate frontend types from OpenAPI, in CI.
- Track dataset and model licences from day one.

### Don't

- **Don't auto-deny anyone, in any tier, ever.** Assert it in a test.
- Don't claim multi-year progression horizons for models that classify current findings.
- Don't call the fixed-weight sum "SHAP."
- Don't chase Mirai or NYU DeepMammo weights on this timeline — the agreements outlast your project.
- Don't attempt 3D brain MRI on local hardware.
- Don't use real patient data. Public de-identified datasets only, ever.
- Don't train from scratch. Pretrained and fine-tuned only.
- Don't write your own DICOM parser.
- Don't stand up a separate model-serving tier, Kubernetes, or microservices.
- Don't let PHI-shaped data into logs or error traces.
- Don't build the applicant portal, claims module, or billing.
- Don't blockchain the audit log. A hash chain in Postgres is the same guarantee without the liability.
- Don't sum uncalibrated model outputs and call the result a risk score.
- Don't report a single aggregate AUROC as your result.
- Don't leave the compliance question to the viva.

---

## 15. Open Decisions — DECIDE

1. **Framing.** Confirm the shift to decision-support-with-human-sign-off (§1). Everything downstream assumes it.
2. ~~**Task queue.**~~ **Resolved:** neither. `BackgroundTasks` + a `jobs` table, per the design policy. No broker.
3. **Third arm.** Arm C as NHANES-trained tabular XGBoost, as recommended — or would you rather have a fourth *imaging* arm (fundus/DR) and a simpler tabular stub?
4. **CXR dataset.** NIH ChestX-ray14 (open, start today), CheXpert (registration), or MIMIC-CXR (only if someone already holds PhysioNet credentialing)?
5. **DICOM viewer.** Confirm server-rendered PNG for v1 with Cornerstone3D as a stretch goal.
6. **Jurisdiction.** Is the compliance chapter anchored to Bangladesh/IDRA, the EU AI Act, or a comparative treatment? Affects §10's depth.
7. **Genetic markers.** Confirm the extractor ships behind a default-off tenant policy flag (§10).
8. **Name.** *Homelander* is a Boys character — specifically a figure who conceals what he really is. For a product that detects concealed pathology that is either a sharp piece of naming or a slightly ominous one, depending on the room, and it carries a trademark question if this ever goes commercial. Fine for a thesis; worth a deliberate decision rather than an inherited one.

---

## Appendix — Change Log Against `Idea.md`

| § in `Idea.md` | Disposition |
|---|---|
| 1. Core concept | **REVISED** — automated gateway → decision support with human sign-off |
| 2. Problem & purpose | **LOCKED** — currency figures relabelled illustrative; progression-horizon claim narrowed |
| 3. Stakeholders | **REVISED** — claims adjusters and applicant portal cut from v1 |
| 4. Architecture (FastAPI, Celery, Redis) | **REVISED** — FastAPI locked; Celery, Redis and MinIO dropped under [DESIGN_POLICY.md](DESIGN_POLICY.md) |
| 4. Model stack (8 arms) | **REVISED** — datasets/frameworks corrected; cut to 3 arms with an extension interface |
| 5. CRS formula | **REVISED** — calibration added; fixed weights become a baseline against learned fusion |
| 5. Decision tiers | **LOCKED** — thresholds made configurable and derived; `INSUFFICIENT_EVIDENCE` added; no-auto-denial made an invariant |
| 6. Grad-CAM | **LOCKED** |
| 6. SHAP breakdown | **REVISED** — was not SHAP; becomes real once learned fusion exists |
| 6. Audit logs | **LOCKED** — mechanism specified (Postgres hash chain) |
