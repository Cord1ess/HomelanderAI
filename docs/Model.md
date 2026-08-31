# Homelander AI — Implementation Plan

Multi-model medical imaging evaluation dashboard. Users upload an image (or record), route it to the correct model(s), and view results through a unified dashboard.

---

## 1. Architecture

Hub-and-spoke: one orchestrator, each model isolated as its own microservice. Avoids dependency conflicts (PyTorch versions, MONAI, XGBoost, transformers all clash if crammed into one process) and means one model crashing doesn't take down the rest.

```
Frontend (upload UI, results view)
        │  REST (submit job) / WebSocket (live results)
        ▼
Orchestrator API (FastAPI)
  - modality detection / routing
  - job queue (Celery + Redis)
  - model registry
        │
        ▼
Model microservices (Docker, one per model)
  - each exposes POST /predict
  - returns a common ModelResult schema
```

### Common model interface

```python
class ModelResult(BaseModel):
    model_id: str
    status: Literal["success", "error", "unsupported_input"]
    risk_score: float | None = None
    label: str | None = None
    confidence: float | None = None
    raw_output: dict

class ModelService(Protocol):
    input_modality: Literal[
        "dicom_mammo", "cxr", "fundus", "mri_3d", "dermoscopy", "ehr_text", "tabular"
    ]
    def predict(self, input_data) -> ModelResult: ...
```

---

## 2. Model status (what's real, what needs work)

| Model | Category | Status | Effort to integrate |
|---|---|---|---|
| Mirai | Breast cancer (mammography) | Open weights + Docker inference server (`OncoServe`) exist | Low |
| OpenCXR | Lung/COPD (chest X-ray) | Open-source, `pip install opencxr` | Low |
| CheXpert baseline | Lung findings (chest X-ray) | Public checkpoints via TorchXRayVision | Low |
| BioBERT | Clinical NLP | Loads via HuggingFace `transformers`; general backbone only | Low (backbone) / Medium (fine-tune for BRCA/biopsy extraction) |
| HAM10000 classifier | Skin cancer (dermoscopy) | Dataset is real; no single canonical checkpoint | Medium — fine-tune ResNet/EfficientNet yourself |
| EyePACS-based retinopathy model | Diabetic retinopathy (fundus) | Dataset is real ("RetinaGuard" is not a real published model); no canonical checkpoint | Medium — fine-tune or adopt a published open one |
| XGBoost actuarial model | Tabular/demographic risk | No pretrained model exists — XGBoost is a generic library | Medium/High — needs your own labeled tabular data |
| Neurodegenerative model | Brain MRI (3D) | MONAI is a framework, not a specific model | High — pick an architecture + dataset (e.g. ADNI) and train |
| CXR-CVD | Cardiovascular (chest X-ray) | Published (MGH/Harvard) but no public code/weights | High — reimplement from the paper (CNN + Cox/hazard head) |

---

## 3. Phased build plan

### Phase 1 — Core pipeline + fast wins
**Goal:** working end-to-end dashboard with a few real, low-effort models.

- [ ] Scaffold orchestrator (FastAPI): job submission endpoint, WebSocket result channel
- [ ] Set up Redis + Celery (or RQ) for async jobs
- [ ] Define `ModelResult` schema and model registry pattern
- [ ] Build modality-detection step in upload UI (route file → valid model list only)
- [ ] Integrate Mirai (`OncoServe` Docker image) — 4-view DICOM mammogram input
- [ ] Integrate OpenCXR — chest X-ray segmentation/utility algorithms
- [ ] Integrate CheXpert baseline (TorchXRayVision) — chest X-ray pathology classification
- [ ] Integrate BioBERT as a raw backbone (embeddings/masked predictions) with a clear "backbone only, not fine-tuned" label
- [ ] Basic results view: per-model card showing score/label/confidence
- [ ] Add "Live model" vs. "In development" badges on each model card
- [ ] Add visible disclaimer: research/demo tool, not for clinical decision-making

**Exit criteria:** user can upload a chest X-ray or mammogram and get results back from at least 2 real models through the full pipeline.

### Phase 2 — Trainable models
**Goal:** fill in models where the dataset is real but no checkpoint exists.

- [ ] Fine-tune ResNet/EfficientNet on HAM10000 for skin lesion classification
- [ ] Fine-tune or adopt a published EyePACS-trained model for diabetic retinopathy grading
- [ ] Fine-tune BioBERT with a task-specific head (NER/classification) for BRCA flag / prior biopsy extraction from EHR text
- [ ] Source or construct a labeled tabular dataset; train XGBoost actuarial scoring model
- [ ] Add preprocessing pipelines per modality (fundus FOV cropping, dermoscopy resize/normalize)

**Exit criteria:** all Phase 2 models return real (non-stub) predictions, validated against held-out test data.

### Phase 3 — Research reimplementation
**Goal:** the two hardest, no-public-artifact cases.

- [ ] Reimplement CXR-CVD from the published paper (CNN backbone + hazard/Cox layer), train on an available CXR + outcomes dataset
- [ ] Select a specific published 3D neuro architecture (e.g., MONAI-based 3D CNN) + dataset (e.g., ADNI) for neurodegenerative classification; train and validate
- [ ] Re-benchmark against reported paper metrics where possible

**Exit criteria:** all 9 model slots return genuine model output; no remaining stubs.

### Phase 4 — Hardening
- [ ] GPU inference server (Triton or dedicated containers) for compute-heavy models (3D MRI, mammography)
- [ ] Batching/queue tuning for throughput
- [ ] Data handling review: if any real patient data is used, add appropriate de-identification / access controls
- [ ] Logging, monitoring, error handling per service
- [ ] Auth on the dashboard if it's multi-user

---

## 4. Repo layout

```
homelander-ai/
├── orchestrator/          # FastAPI gateway, job queue, WebSocket, model registry
├── services/
│   ├── mirai/             # Dockerfile + OncoServe wrapper
│   ├── opencxr/
│   ├── chexpert/
│   ├── biobert/
│   ├── ham10000/
│   ├── retinopathy/
│   ├── xgboost_actuarial/
│   ├── neuro_mri/
│   └── cxr_cvd/
├── frontend/               # upload UI, modality router, results dashboard
└── docker-compose.yml      # orchestrator + all services + redis
```

---