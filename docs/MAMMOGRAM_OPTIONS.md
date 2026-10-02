# The mammogram arm — audit, options, and the plan

**Status:** Phases 1–4 done. **Mirai runs on this laptop, on the CPU, and is
the arm.** The remote server and the stand-in are gone. What was measured:

| check | result |
|---|---|
| container on CPU, no `--gpus` | `mitjclinic/mirai:v0.14.1`, `torch.cuda.is_available() == False` |
| the authors' demo exam | `0.0298 0.0483 0.0684 0.09 0.1016` — **exactly their published output** |
| … after our de-identification | identical to four decimal places |
| our CBIS-DDSM demo films | accepted; `0.001 … 0.0115`, the same numbers the old remote server gave |
| one exam, 8 threads | **≈ 43 s** (52 s at 4, 49 s at 16) |
| refusal (three views) | HTTP 400, reason passed through to the screen |
| full application end to end | all six readers, Fatema moderate (58.97), every check passes |

Phase 5 (the honesty pass across all six arms) is next. Phase 6 (Gail) is not
needed for the mammogram, since Mirai works on our films.

The rest of this document is the audit as it was written, kept because the
reasoning is the useful part.

---

## 1. What was actually wrong

The premise going in was "Mirai needs a GPU, the cloud was slow and expensive".
Measurement says the picture is different, and the distinction matters because
it changes what we should build.

### The hardware

| | |
|---|---|
| CPU | Intel Core Ultra 5 125H, 18 cores |
| RAM | 15.5 GB |
| GPU | Intel Arc (integrated) — **no NVIDIA, no CUDA** |
| torch | `2.13.0+cpu`, `torch.cuda.is_available() == False` |

Any CUDA-only container is out on this machine. That is a hardware fact, not a
budget decision, and no amount of money changes it without different hardware.

### What the existing arms cost here (warm, measured)

| arm | model | time |
|---|---|---|
| `ecg_12lead` | 1-D CNN | 0.2 s |
| `dr_fundus` | ResNet-50 | 0.6 s |
| `tb_xray` | DenseNet-121 | 4.4 s |

So this machine already runs two real CNNs for the demo without complaint. The
ceiling for "acceptable in a background scoring task" is therefore well above
five seconds — the operator is already waiting on `tb_xray`.

### What Mirai-sized compute costs here (measured, random weights)

Mirai's image encoder is ResNet-18-based at 1664×2048 per view.

| backbone | per view | four views |
|---|---|---|
| **ResNet-18 (Mirai's)** | 1.24 s | **≈ 5.0 s** |
| ResNet-34 | 2.25 s | 9.0 s |
| DenseNet-121 | 3.33 s | 13.3 s |
| ResNet-50 | 4.03 s | 16.1 s |

**Mirai's own architecture is about as expensive as the chest arm we already
ship.** The compute was never the problem.

### Where the three minutes went

| stage | measured |
|---|---|
| DICOM decode | 0.02 s |
| our de-identification, 4 views | 0.7 s |
| **payload pushed over the network** | **105 MB** |

105 MB at a home upload speed of 10–25 Mbps is **35–90 seconds before the
server begins**. And nearly all of it is waste, because Mirai downsamples to
1664×2048 anyway:

| what we send | 4 views |
|---|---|
| native DICOM (what we do today) | 106 MB |
| RLE lossless DICOM | ≈ 36 MB |
| 1664×2048 16-bit PNG — what the model reads | **7.1 MB** |

A 15× payload reduction was available and we never took it. If we keep any
remote option, this is the first thing to fix.

### The teammate's server

`http://34.173.36.245:5000/serve` — connection times out, not a slow answer.
Gone, and we should stop depending on it.

---

## 2. The options

Four real ones. Two are confirmed obtainable and CPU-capable; one needs a
licence check; one is a fallback that needs no imaging at all.

### A. Mirai, run locally — **recommended**, and verified to be viable

The premise that Mirai needs a GPU is wrong. Every claim below was checked
against a primary source, not a search summary.

**We were looking at the wrong repository.** `yala/Mirai` is the 2019–21
generation: no weights in the repo, and the container behind a per-request gate
(the author restricted it over "concerns about improper use"). The maintained
line is **`reginabarzilaygroup/Mirai`** plus its serving layer `ark`, and it has
no gate at all.

| | verified |
|---|---|
| Licence | plain **MIT**, "Copyright (c) 2021 Massachusetts Institute of Technology and Massachusetts General Hospital". The README extends it to the trained model verbatim: *"Mirai (the trained model) and all code are released under the MIT license."* No commercial restriction, no citation clause. |
| Weights | `snapshots.zip`, **64,800,973 bytes**, HTTP 200, ungated GitHub release (v0.8.0), 677 downloads — **not** the 4.3 GB tar |
| Container | `mitjclinic/mirai:latest` — public, 1,610 pulls, 14 layers, **1.12 GB** |
| CPU | `PYTHON_VERSION=3.8.20`, `ARK_THREADS=4`, **no CUDA/NVIDIA env vars**, no `--gpus` in any run command. Legacy OncoServe hardcodes `'cuda': False` for the Mirai config. |
| Official requirements | 16 GB RAM, 15 GB disk, "Modern CPU", **"GPU (optional** but recommended for faster inference speed)"** |
| Documented runtime | the project's own example response shows `"runtime": "21.27s"` for a four-view exam; the wiki says 10–60 s |
| Demo data | `mirai_demo_data.zip`, 21.2 MB, ungated — real mammograms to validate against |

The 4.3 GB Dropbox tar is also still live (verified, `Content-Length:
4306372096`) but it is the old gated-era artefact and 25× larger for the same
model. Ignore it.

**Why Mirai and not the alternatives:** it is the only option that predicts
*future* risk over a time horizon (a C-index at 1–5 years). Every alternative in
this document detects *current* malignancy. Underwriting asks "what is the
chance of a claim in the next five years" — that is Mirai's question and nobody
else's. Swapping it for a detector would quietly change what the arm means.

**Two things to design around, both confirmed:**

1. **Python 3.8 hard pin.** `setup.cfg` in the maintained fork pins
   `python_requires = >=3.8, <3.9`, with `torch==1.9.0` whose wheels stop at
   cp39. It cannot go in our venv — `torch 1.9.0` has no cp312 wheel and
   `scipy==1.7.3` excludes 3.12 outright. **So it runs as a sidecar container
   speaking HTTP, never as a library.** That also keeps it clear of the
   env-sync trap in `docs/` and needs no second interpreter on the host.
2. **Risk factors are silently ignored when served.**
   [reginabarzilaygroup/Mirai#14](https://github.com/reginabarzilaygroup/Mirai/issues/14)
   (open, Sept 2026) — `run_model` hardcodes `risk_factor_vector = None`, so
   predictions are byte-identical with and without them. The served model is
   **image-only**.
   *This costs us nothing today*: our arm has never sent risk factors and
   `docs/MIRAI.md` has never claimed it did. But it fixes what we may claim —
   the arm reads the films, and the declared history reaches the score through
   the scoring rules, not through Mirai. The issue reporter also ran on CPU with
   `mitjclinic/mirai:latest`, which is the closest thing to a user confirmation
   that CPU works.

**Input constraints** (hard, and they shape the demo): exactly four
"For Presentation" views, one per laterality/view pair — `assert len(dicom_files)
== 4`. No "For Processing" images, no unilateral studies, no CAD annotations.
Trained only on Hologic Selenia; the authors state they have not tested other
manufacturers. Our demo films are CBIS-DDSM, so this needs checking.

**Not yet verified:** real CPU latency on *this* machine. The 21.27 s figure
does not say what hardware produced it, and the legacy container shipped
`gunicorn -t 360`, which hints the authors expected slow requests. Our current
arm budget is 60 s (commit f248c02) and may need raising.

### B. `ianpan/mammoscreen` — the fallback, verified and measured

Independently confirmed, not taken on trust:

- Hugging Face API: `"gated": false`, `"private": false`, licence
  **`apache-2.0`** — the most permissive of anything found.
- `modeling.py` line 187: **`device: str = "cpu"`** is the committed default of
  `forward()`. CPU is the documented path, not a workaround.
- DICOM-native: `load_image_from_dicom()` applies the VOI LUT and handles
  `MONOCHROME1` inversion via pydicom.
- `config.json`: 3 × `tf_efficientnetv2_s` at (2048×1024), (1920×1280),
  (1536×1536), averaged. 61 M params, `model.safetensors` ≈ 244 MB.
- Also returns 4-class **breast density** in the same forward pass.
- Reported AUROC **0.9451** (sd 0.002) on a held-out RSNA split — but see §3,
  because that is an internal split and the number does not travel.

**Measured cost on this CPU** (equivalent torchvision EfficientNetV2-S at the
three configured sizes, random weights):

| stage | time |
|---|---|
| one breast, all three backbones | 12.8 s |
| **full exam, both breasts** | **≈ 26 s** |

Slower than any arm we ship, and fine inside a background task. Note it takes
two views *per breast*, so it is called twice per exam rather than once over
four views — a change from how `mirai.py` is shaped today.

### C. `nyukat/GMIC` — the CPU-proven fallback

- Weights committed into the repo (5 × ≈ 60 MB), plain `git clone`, no gate.
- `run.sh` ships `DEVICE_TYPE='cpu'` as its committed default.
- Reported AUC 0.93 on NYU's internal dataset — **and 0.51 on CBIS-DDSM in
  independent evaluation.** See §3; this is the starkest example of the problem.
- **Licence: AGPL-3.0.** Viral and network-triggering. Acceptable for a capstone,
  but it should not enter a codebase anyone intends to commercialise without a
  deliberate decision. Flag before use.

### D. Gail / BCRAT — no imaging at all

The NCI's own breast-cancer risk tool. The logistic-regression coefficients are
published as data in the CRAN package `BCRA` (v2.1.2, from NCI DCEG), with
race/ethnicity-specific variants, so it can be reimplemented in Python honestly
and cited to source.

- Inputs: age, age at menarche, age at first live birth, number of first-degree
  relatives with breast cancer, number of prior biopsies, atypical hyperplasia,
  race/ethnicity. All of these are intake-form questions, not images.
- Reported AUC **0.64** (95% CI 0.61–0.65).

This is a far weaker discriminator than any imaging model and must not be
presented as a replacement. Its value is different: it works for every female
applicant, including the ones who bring no mammogram, and it is a useful foil —
0.64 against 0.9+ is the cleanest way to show that imaging earns its keep.

Tyrer-Cuzick, BOADICEA/CanRisk and BCSC were all investigated and are **not
viable for us**: Windows-only binary with no source, web API requiring
registration, and a request-gated SAS file respectively. Details are in the
research notes; none can be reimplemented from published coefficients the way
Gail can.

---

## 3. The number we are allowed to put on a slide

This is the most important finding in the audit and it is not about compute.

NYU's meta-repository (Stadnick et al., *Meta-repository of screening
mammography classifiers*, arXiv:2108.04800) re-ran five published models on
seven external datasets. Verified: the paper exists and does exactly this.
Out-of-distribution performance collapses:

| model | internal (reported) | CBIS-DDSM | CMMD |
|---|---|---|---|
| GMIC | 0.93 (NYU) | **0.51** | 0.80 |
| GLAM | — | 0.50 | 0.76 |
| DMV-CNN | 0.895 (NYU) | 0.54 | 0.79 |
| DMV-CNN (4 images) | — | 0.56 | 0.90 |
| End2end | — | 0.70 | 0.53 |

**GMIC's 0.51 on CBIS-DDSM is chance.** Against a headline of 0.93.

Two consequences, both binding on how we write this up:

1. **Every AUC we quote carries its dataset.** "GMIC reports 0.93 on NYU's
   internal data; independent evaluation on CBIS-DDSM gives 0.51." A bare 0.93
   is the same dataset trap that already bit the TB arm on the Kaggle set
   (`docs/TB.md`, `docs/SPEC.md` §9) — where normals and positives came from
   different hospitals and the model learned the hospital.
2. `mammoscreen`'s 0.9451 is an **internal RSNA split** with no independent
   external validation found. It inherits exactly the same caveat and is not
   comparable to the table above.

Presenting this honestly is a stronger capstone result than a big number would
be. It is a real finding about the field, we can demonstrate it, and it is the
kind of thing a panel remembers.

---

## 4. The plan

Phase 1 (this document) is done. The rest is ordered so that the thing most
likely to kill the approach is tested first and cheaply — if Mirai cannot run
here, we find out in an afternoon, not a fortnight.

### Phase 2 — prove it runs, before changing any of our code

Nothing in `apps/` is touched. The question is only: does this container answer
correctly, on this machine, in an acceptable time?

1. Start Docker Desktop (installed, 29.8.0, daemon currently stopped).
2. `docker pull mitjclinic/mirai:latest` (1.12 GB).
3. `docker run --rm -p 5000:5000 mitjclinic/mirai:latest` — no `--gpus`.
4. Fetch `mirai_demo_data.zip` (21.2 MB, ungated) and post its four views to
   `POST /dicom/files`. The project publishes an expected response, so this is a
   **correctness** check, not just a smoke test.
5. **Measure:** wall-clock per exam, cold and warm; RAM high-water mark;
   whether `ARK_THREADS` above 4 helps on 18 cores.

**Exit criteria.** Go if it returns the documented prediction within ~90 s using
under ~8 GB. If it is far slower, try `ARK_THREADS=8`; if still unusable, Option
B (`mammoscreen`, measured at ≈26 s here) is the fallback and the work in
Phase 3 is mostly shared.

### Phase 3 — make our films work, or find out they cannot

The risk that is specific to us, and it is not small.

1. Run our CBIS-DDSM demo films through the container.
2. Mirai requires exactly four "For Presentation" Hologic views and the authors
   state they have not tested other manufacturers. Our films are CBIS-DDSM and
   were given their view tags by a teammate's script
   (`Mirai/dcmMetadataAdder/script.py`), which also sets
   `Manufacturer = "MathWorks"` — so they are already not what the model
   expects.
3. If they are rejected or produce implausible output, decide between: sourcing
   four genuine Hologic presentation views, or moving to Option B, whose
   reported training set (RSNA + CBIS-DDSM) actually matches our films.

**This is the most likely failure point in the whole plan**, and it is about
our data rather than the model. Hence doing it before any integration.

### Phase 4 — replace the arm

Only once Phases 2–3 pass.

1. `MIRAI_URL` points at `http://localhost:5000/dicom/files`. The arm already
   has the shape for this; the API changed (field `dicom` repeated, plus a
   required `data` field; response `data.predictions["Year 1".."Year 5"]` rather
   than a flat `prediction` list), so the parsing changes.
2. **Shrink the payload.** Even to localhost, 106 MB per exam is waste: send
   what the model reads. Measured 106 MB → 7.1 MB. This is the fix that
   should have been made before we ever rented a GPU.
3. Raise `mirai_timeout_seconds` from 60 to whatever Phase 2 measured, plus
   headroom.
4. **Delete the stand-in**, and the `mirai_simulate` setting with it. The
   showcase requirement is no mocks; the stand-in was for a video recorded
   while the server was down and has no business in a real demonstration.
5. Tests: a real four-view exam through the container (marked so it skips when
   Docker is absent), the existing view-validation tests, and the arm's score
   mapping.

### Phase 5 — honesty pass across all six arms

The finding in §3 is not about the mammogram. Every arm quotes a number from a
paper, and at least one — the TB arm — has already been caught by exactly this
trap on a different dataset.

1. For each arm, state the metric **with the dataset it was measured on**, and
   where an independent external evaluation exists, state that too.
2. Add the meta-repository table to the write-up. GMIC 0.93 → 0.51 is the
   single most defensible point available to this project.
3. Check every claim in `docs/` against what the code does. The risk-factor
   issue above is the template: a reasonable-sounding claim that the
   implementation does not support.

### Phase 6 — the fallback, if Phase 3 rules out Mirai

Implement Gail/BCRAT from the published NCI coefficients as a no-imaging arm.
Cheap, honest, works for every female applicant including those who bring no
mammogram, and a useful foil at AUC 0.64 against imaging's 0.9+.

Worth doing eventually regardless — but it is a different measurement, not a
substitute for Mirai, and must never be presented as one.

---

## 5. Open items

Stated rather than guessed:

- ~~Mirai licence~~ — **answered**: plain MIT, covering the trained weights.
- ~~Mirai on CPU~~ — **answered**: supported, and the default. No code edit.
- **Mirai runtime on this machine** — still unmeasured. The project's own
  `21.27s` figure does not name its hardware, and our ResNet-18 estimate (≈5 s)
  is a floor for the encoder alone, not the full model with preprocessing.
  Phase 2 measures it.
- `mammoscreen` measured latency with **real weights** — the 26 s above is an
  architecture-equivalent estimate, and real preprocessing may add to it.
- GMIC absolute parameter count — only published relatively.
- NYU density model's accuracy — the abstract gives no number; needs the full PDF.
- RSNA 2023 winning pF1 — not found; do not cite a value.

---

## 6. Sources

- Mirai: Yala et al., *Sci Transl Med* 2021 · https://github.com/yala/Mirai ·
  https://github.com/yala/OncoServe_Public
- mammoscreen: https://huggingface.co/ianpan/mammoscreen
- GMIC: Shen et al., *Medical Image Analysis* 68 (2021) ·
  https://github.com/nyukat/GMIC
- DMV-CNN: Wu et al., *IEEE TMI* 2019 · arXiv:1903.08297 ·
  https://github.com/nyukat/breast_cancer_classifier
- Meta-repository: Stadnick et al., arXiv:2108.04800 ·
  https://github.com/nyukat/mammography_metarepository
- Gail/BCRAT: https://cran.r-project.org/web/packages/BCRA/BCRA.pdf ·
  https://dceg.cancer.gov/tools/risk-assessment/bcra/
- Density: Wu et al., ICASSP 2018 · arXiv:1711.03674 ·
  https://github.com/nyukat/breast_density_classifier
