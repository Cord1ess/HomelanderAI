# HomelanderAI

A multi-tenant decision-support platform for life, health, and critical-illness insurance underwriting.

Carriers submit an applicant evidence package — medical imaging, clinical notes, and structured questionnaire or lab data. HomelanderAI runs it through an ensemble of specialised models and returns a Composite Risk Score with per-arm sub-scores, visual evidence, factor attribution, a recommended underwriting action, and an immutable audit record.

Every output is a **recommendation**. A licensed underwriter records the final decision, and their identity forms part of the audit trail. The platform never issues an automated denial.

---

## Status

**Phase 0 — scaffold.** Dependencies, tooling and a running dev server. No pipeline, no models, no database yet.

What exists today: a FastAPI app with a health endpoint, a React + Mantine page that polls it, linting, tests, and a Compose file for the infrastructure that lands next.

Full scope, architecture decisions and roadmap live in **[docs/SPEC.md](docs/SPEC.md)**.

This is an academic capstone project. It is not a medical device, not clinically validated, and not intended for use in real underwriting decisions. See [Disclaimer](#disclaimer).

---

## Getting started

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.5+ | Manages Python itself — you do **not** need Python pre-installed. It fetches 3.12 for this project. |
| [Node.js](https://nodejs.org) | 22+ | Tested on 24.18. Comes with npm. |
| Git | any | |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | — | **Not needed yet.** Required from Phase 1, when Postgres lands. |

> Your system Python version doesn't matter. uv pins 3.12 for this project because torch and spaCy don't yet support 3.13+.

### Setup

```bash
git clone https://github.com/Cord1ess/HomelanderAI.git
cd HomelanderAI
npm install
```

That's it. The root `postinstall` hook installs the frontend dependencies for you, and `uv` creates the Python virtualenv automatically the first time you run the API.

If you'd rather do the Python install up front instead of on first run:

```bash
npm run setup
```

### Run it

```bash
npm run dev
```

One command, both servers, colour-coded output:

```
[api] Uvicorn running on http://127.0.0.1:8000
[web] VITE ready — http://localhost:5173/
```

| | |
|---|---|
| Portal | **http://localhost:5173** |
| API docs | http://127.0.0.1:8000/docs |

`Ctrl+C` stops both. You should see a status page reporting that the server is running, with live version and uptime. If the API isn't up, the page says so rather than failing silently.

The Vite dev server proxies `/api` to port 8000, so the browser stays same-origin with the API. That matters later — the portal session will be an httpOnly cookie, and same-origin avoids CORS and `SameSite` problems.

Need the two halves in separate terminals? `npm run dev:api` and `npm run dev:web`.

---

## Commands

All from the repo root.

| Command | Does |
|---|---|
| `npm run dev` | **Both servers.** This is the one you want. |
| `npm run dev:api` | API only |
| `npm run dev:web` | Frontend only |
| `npm run check` | Everything CI would run: lint, typecheck, tests, build |
| `npm run lint` | oxlint + ruff |
| `npm run typecheck` | TypeScript only |
| `npm run test` | pytest |
| `npm run format` | ruff format |
| `npm run build` | Production build to `apps/web/dist/` |
| `npm run gen:api` | Regenerate TS types from the API's OpenAPI schema (API must be running) |
| `npm run setup` | Reinstall both dependency trees |

Infrastructure — **Phase 1 onward**, needs Docker Desktop:

| Command | Does |
|---|---|
| `npm run infra:up` | Start Postgres |
| `npm run infra:ps` | Status |
| `npm run infra:down` | Stop (keeps data) |

Working directly in one app? `apps/api` takes `uv run pytest`, `uv run ruff check .`; `apps/web` takes the usual `npm run dev`/`build`/`lint`.

---

## Project layout

```
package.json            root scripts — `npm run dev` lives here
docker-compose.yml      infra only (Phase 1)
.env.example            all config, one place
apps/
  api/                  FastAPI service
    app/
      main.py           app factory, CORS, router registration
      config.py         settings from .env (pydantic-settings)
      routers/          HTTP routes
    tests/
    pyproject.toml      Python deps + ruff/pytest config
  web/                  React + Vite + Mantine portal
    src/
      main.tsx          providers: Mantine, TanStack Query
      App.tsx           status page
      theme.ts          Mantine theme
      api/client.ts     fetch wrapper
docs/
  SPEC.md               working specification — scope, decisions, roadmap
  DESIGN_POLICY.md      how we implement — read before writing code
  DATABASE.md           schema changes needed (handoff)
  DASHBOARD.md          screens, intake form, API contract (handoff)
  PHASE1_PLAN.md        TB screening + scoring, in three commits
  Idea.md               original concept (superseded by SPEC.md)
```

Landing in later phases: `packages/ml` (model arms, calibration, fusion, XAI), `docs/adr` (decision records).

`packages/ml` must stay importable and testable without the API running, so ML work never requires Docker.

---

## Working on models

The ML libraries are heavy, so they're optional extras. Skip them unless you're actually building a model arm.

```bash
cd apps/api
uv sync --extra ml       # torch (CPU), TorchXRayVision, XGBoost, SHAP, Grad-CAM, MLflow  (~2-3 GB)
uv sync --extra nlp      # spaCy, scispaCy, negspaCy, transformers                        (~1 GB)
uv sync --all-extras     # everything
```

**Torch is pinned to CPU wheels** via a dedicated index in `pyproject.toml` — much smaller, and correct for the local-compute constraint. If you have an NVIDIA GPU, change that index URL to the matching `cuXXX` variant and re-sync.

**scispaCy NER models are not pip packages.** They install from release URLs and must match your installed scispaCy version — see the [scispaCy README](https://github.com/allenai/scispacy#available-models) for the URL, then:

```bash
uv pip install <model-url-from-that-page>
```

---

## Known issues

**`medspacy` is deliberately not a declared dependency.** Its published sdist is broken — `setup.py` reads a `requirements/requirements.txt` that isn't in the tarball, so metadata fails to build on every platform, and because `uv sync` resolves *all* extras even when installing none, it took the entire lockfile down. `negspacy` covers NegEx negation, which is what the clinical NLP arm needs first. If you later want full ConText assertion detection (`FAMILY_HISTORY` and `HYPOTHETICAL`, not just `NEGATED`), install it out-of-band:

```bash
uv pip install "medspacy @ git+https://github.com/medspacy/medspacy"
```

**`openapi-typescript` isn't in `package.json`.** It peer-depends on TypeScript 5.x while this project is on TypeScript 6. Rather than forcing `--legacy-peer-deps` into a fresh repo, `npm run gen:api` invokes it through `npx` on demand. Revisit once it supports TS 6.

**Deprecation warning in tests.** Starlette's `TestClient` reports that using it with `httpx` is deprecated in favour of `httpx2`. Harmless — tests pass. Worth resolving when the ecosystem settles.

---

## The problem

Underwriters face **early-claim asymmetry.** An applicant may carry early-stage, asymptomatic pathology that passes a health questionnaire and a basic nurse screening. Underwritten at baseline rates, a few months of collected premium can be followed by a catastrophic critical-illness claim.

HomelanderAI surfaces findings associated with elevated near-term morbidity risk from evidence the carrier already collects, so that elevated-risk applications reach a human reviewer with the relevant evidence attached — and low-risk applications clear faster.

## How it works

```
Evidence package
      │
      ▼
Async job queue  ──►  Model arms (run independently)
                        ├─ Vision        chest radiograph classification
                        ├─ Clinical NLP  entity + assertion extraction
                        └─ Tabular       actuarial / mortality risk
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

## Stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite 8, TypeScript, Mantine 9, TanStack Query, React Router |
| API | FastAPI, Python 3.12, Pydantic v2 |
| Persistence | PostgreSQL 16, SQLAlchemy 2.0, Alembic, `tenant_id` + row-level security |
| Jobs | FastAPI `BackgroundTasks` + a `jobs` table in Postgres — no broker |
| Evidence storage | Local filesystem under `./data`, served via authenticated routes |
| Auth | JWT session cookie + hashed carrier API keys, Argon2id |
| ML | PyTorch, TorchXRayVision, scispaCy + negspaCy, PubMedBERT, XGBoost, scikit-learn |
| Explainability | pytorch-grad-cam, SHAP |
| Tracking | MLflow (self-hosted) |
| Imaging | pydicom, Pillow, SimpleITK |
| Tooling | uv, ruff, pytest, oxlint, Playwright, Docker Compose |

## Data and models

No real patient data is used at any stage. Development runs on public, de-identified research datasets and a synthetic applicant generator.

Model weights are sourced from published research releases, most of which are licensed for **non-commercial research use**. Dataset and model provenance is tracked in `docs/DATA_SOURCES.md` and `docs/MODEL_LICENSES.md`.

`/data` is gitignored. Never commit medical images, model weights, or `.env`.

## Disclaimer

Research software. Not a medical device. Not clinically validated, and not approved by any regulatory body.

The models used here were developed and validated for **clinical screening in patient populations**. Applying them to an insurance applicant population to inform a financial decision is a change of both distribution and purpose, and their outputs should not be read as diagnoses or as clinically actionable findings.

Automated risk assessment and pricing in life and health insurance is a regulated activity in most jurisdictions, including as a high-risk application under the EU AI Act. Nothing in this repository is fit for deployment against real applicants.

## License

Not yet determined. Until a license is added, all rights are reserved.
