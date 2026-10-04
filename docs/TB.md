# TB Screening — how it works

A chest X-ray and a set of health questions go in. A risk score from 0 to 100
comes out, along with a tier, a heatmap, and a written reason for every part of
the number.

This is a **screening** tool. It never diagnoses anyone and never rejects
anyone. A high score means "a person should look at this", nothing more.

---

## The five steps

```
X-ray file
    │
    ▼
1. INTAKE          strip personal data, convert to PNG, record a hash
    │
    ▼
2. VISION MODEL    read the image -> 18 finding probabilities
    │
    ▼
3. TB SCORE        combine the 18 numbers -> one TB score (0-100)
    │
    ▼
4. HISTORY RULES   adjust that score using the declared health answers
    │
    ▼
5. TIER            low / moderate / elevated / insufficient evidence
```

Each step is a separate file and can be tested on its own.

---

## Step 1 — Intake

**File:** `apps/api/app/intake.py`

Two kinds of file are accepted:

- **DICOM** (`.dcm`), the format hospital scanners produce
- **Ordinary images** (`.png`, `.jpg`)

### Removing personal data

A DICOM file is two things: the picture, and a block of text attached to it.
That text routinely holds the patient's name, date of birth, patient ID, the
hospital name, and the referring doctor.

We do not edit that text block. **We throw the whole DICOM away and keep only a
PNG of the picture.** Information that is never stored cannot leak later.

A short list of medically useful details is copied out first and kept
separately: which body part, which view, and what kind of scanner. Nothing that
identifies a person.

Ordinary images are re-saved as PNG, which removes the hidden metadata that
phone cameras attach (including location).

### One thing this cannot fix

Some scanners print the patient's name directly onto the image itself, as part
of the picture. Removing text attached to the file does nothing about text drawn
into the pixels.

The system cannot detect that automatically, so when a DICOM declares it has
printed text, **the file is flagged for a person to check** rather than quietly
accepted.

### Fingerprint

Every stored file gets a SHA-256 hash — a short string calculated from its
contents. The same image always produces the same string; any change produces a
different one. This is what later proves which exact image produced which score.

---

## Step 2 — Reading the X-ray

**File:** `apps/api/app/arms/tb_xray.py`

The image goes through **TorchXRayVision**, a published chest X-ray model
(DenseNet-121, weights `densenet121-res224-all`).

It returns a probability from 0 to 1 for each of **18 findings**:

```
Atelectasis     Cardiomegaly    Consolidation   Edema
Effusion        Emphysema       Enlarged Cardiomediastinum
Fibrosis        Fracture        Hernia          Infiltration
Lung Lesion     Lung Opacity    Mass            Nodule
Pleural_Thickening              Pneumonia       Pneumothorax
```

**None of these is "tuberculosis".** This model was never trained to detect TB.
It describes what it sees in the lungs. Step 3 is what turns those descriptions
into a TB score.

The image must be prepared in a very specific way before the model sees it —
rescaled to a particular numeric range, cropped from the centre, and resized to
224×224. Getting this wrong does not produce an error; it produces confident
nonsense. That preparation code is not to be modified casually.

---

## Step 3 — Turning 18 findings into one TB score

**Files:** `apps/api/app/arms/tb_xray.py`, `apps/api/app/arms/tb_xray_model.json`

The 18 numbers are combined into a single TB score using weights that were
**learned from labelled data**, not chosen by hand.

Each finding has a weight. A positive weight means "more of this points toward
TB"; a negative weight means "more of this points away from TB". The findings
are multiplied by their weights, added up, and squashed into a 0–100 score.

The learned weights, largest influence first:

| Finding | Weight | Points toward |
|---|---|---|
| Lung Lesion | +1.509 | TB |
| Atelectasis | −1.249 | normal |
| Pneumothorax | +0.870 | TB |
| Nodule | +0.795 | TB |
| Fracture | +0.794 | TB |
| Pneumonia | +0.454 | TB |
| Fibrosis | −0.334 | normal |
| Pleural_Thickening | +0.306 | TB |

The remaining ten findings carry weights below 0.3 and contribute little.

### How the weights are stored

In `tb_xray_model.json` — a small readable file, about 1.5 KB. It contains the
18 weights, one constant, and the scaling numbers needed to normalise the
inputs.

It is plain text on purpose, so it can be read and reviewed like any other file.
Scoring is one multiplication and addition, so the machine-learning training
library is **not** needed to run the system — only to retrain it.

### Explaining the score

Alongside the score, the system records **how much each finding contributed**.
That is what lets the interface say which findings drove a particular result,
instead of showing an unexplained number.

---

## Step 4 — Adjusting for declared health history

**File:** `apps/api/app/scoring.py`

The X-ray score is only part of the picture. The answers given during intake
move it up or down.

| Condition | Change | Why |
|---|---|---|
| Previously treated for TB, **completed** treatment, **no** current symptoms | **−25** | Marks on the X-ray are old scarring, not active disease |
| Previously treated for TB **and** currently symptomatic | **+25** | Possible return of the disease |
| HIV positive | +15 | Large increase in risk; the illness often looks unusual |
| Coughing up blood | +12 | Strong warning sign |
| Two or more current symptoms | +10 | — |
| Diabetes | +10 | Roughly three times the TB risk |
| Someone in the household has had TB | +10 | Known exposure |
| Antibiotics taken without improvement | +10 | Suggests it is not ordinary pneumonia |
| Current or former smoker | +5 | Widens what else it could be |
| Age over 60 | +5 | Widens what else it could be |

The score is kept within 0 and 100 after adjustment.

**The first two rows are the important ones.** The same X-ray produces a *lower*
score for someone treated years ago who feels fine, and a *higher* score for
someone treated years ago who is coughing now. A model looking only at the image
cannot make that distinction, because it never sees the history.

Symptoms tracked: cough lasting over two weeks, weight loss, night sweats,
coughing blood, fever.

History tracked: prior TB, whether treatment was completed, diabetes, HIV,
household TB contact, antibiotics without improvement, smoking.

Every rule that fires records a plain-English sentence explaining itself. Those
sentences are shown to the underwriter.

### Adding a rule

The rules are a list in one file. A new condition is one new entry — no other
code changes.

---

## Step 5 — Tier

| Score | Tier |
|---|---|
| 0 – 30 | Low |
| 30.1 – 65 | Moderate |
| 65.1 – 100 | Elevated |
| no score | Insufficient evidence |

**Insufficient evidence** is used when no usable X-ray was provided, the file
could not be read, or the model failed. It is deliberately *not* scored as zero
— "we could not assess this" and "this person is low risk" are different
answers.

The cut-off points are configurable and are stored with each score, so an old
result can still be explained after the thresholds are changed.

**There is no reject tier, and there will not be one.** The highest tier routes
to a senior underwriter.

---

## The heatmap

For a reading above the low tier, the system draws the film the model read
with the regions the TB score depends on in red. It is **occlusion**: the film
is cut into a 7 x 7 grid, each region is greyed out in turn and the model run
again, and a region is as red as the score falls without it.

It replaced a Grad-CAM on the top-contributing finding which, tested against
the boxes radiologists drew round TB lesions on TBX11K films, was no better
than random. Occlusion found the box about four times in ten — better, and
honest about what the model leaned on, but not a lesion finder: this model
reads general findings, not TB itself. See [HEATMAPS.md](HEATMAPS.md).

If heatmap generation fails, the score is still returned. The picture supports
the result; it is not the result.

---

## How well it works

Trained and measured on the **Shenzhen** dataset: 662 chest X-rays from a single
hospital, 336 with TB and 326 without.

| Measure | Value |
|---|---|
| AUC | **0.877** (± 0.037) |
| Average score, TB X-rays | 73.7 |
| Average score, normal X-rays | 27.1 |

**AUC** means: pick one TB X-ray and one normal X-ray at random. AUC is how
often the TB one gets the higher score. 0.5 is a coin flip. 1.0 is perfect.
**0.877 means it ranks them correctly about 88% of the time.**

### Three limits to state honestly

**1. Its ranking travels to a new hospital; its cut-points do not.** The
0.877 comes from cross-validation on Shenzhen — fair, but every image is from
the same hospital and the same equipment. So the shipped model was run on
**Montgomery County, USA**: 138 films (58 TB, 80 normal) from another country,
other equipment and another decade, none seen in training. Same path as an
application — `intake.process_upload`, then `tb_xray.run` — and nothing
trained or tuned on them (`scripts/tb_external.py`):

| | AUC |
|---|---|
| Shenzhen, 5-fold CV (internal) | 0.877 ± 0.037 |
| **Montgomery, external** | **0.909** (95% CI 0.855–0.956) |

The model still puts TB above normal, as well as it did at home. But the scale
shifts:

| platform cut | sensitivity | specificity |
|---|---|---|
| score above 30 | 0.98 | 0.29 |
| score above 65 | 0.93 | 0.64 |

**71% of normal Montgomery films score above 30**, where every normal
Shenzhen demo film scores under 26. A different hospital's films sit higher on
the scale, so the tier an applicant lands in depends partly on where the film
was taken. The retina arm shows the same pattern (`docs/RETINA.md`).

The fix is to recalibrate the score on a *third* dataset. Tuning the cut-points
on Montgomery would turn the only external test into training data and make
0.909 meaningless, so it has not been done.

**Recalibration was tried on a third dataset and not shipped (2026-10-03).**
TBX11K (Chinese hospitals, not Shenzhen) confirmed the ranking — AUC 0.907 —
and the problem: half its healthy films reached senior review. Anchoring the
tier boundaries at the 90th and 98th percentiles of TBX11K's healthy films
(`scripts/tb_calibrate.py`) looked good on Montgomery (specificity at 30 rose
from 0.29 to 0.83) but failed on Shenzhen: TB films above the low tier fell
from 89% to 25%. TBX11K's healthy films simply read far higher than other
hospitals' (90th percentile at a probability of 0.96), so boundaries set there
move the error from false alarms to missed TB rather than removing it. The
score therefore stays the probability. No single boundary works everywhere —
the model's output shifts with the hospital:

| low-tier boundary (probability) | Shenzhen sens / spec | Montgomery sens / spec | TBX11K sens / spec |
|---|---|---|---|
| 0.3 (in use) | 0.89 / 0.67 | 0.98 / 0.29 | 0.99 / 0.15 |
| 0.5 | 0.79 / 0.84 | 0.93 / 0.50 | 0.96 / 0.35 |
| 0.7 | 0.66 / 0.92 | 0.90 / 0.69 | 0.94 / 0.57 |
| 0.9 | 0.42 / 0.99 | 0.86 / 0.80 | 0.84 / 0.82 |

Every boundary that cuts false alarms at Montgomery and TBX11K misses TB at
Shenzhen. For a TB screen a miss costs more than a second look, so the
sensitive boundary stays, with its false alarms stated. The honest fix is the
one the retina arm got: boundaries set on films from the hospitals that will
actually send them, checked on a second site before use. The script is kept
for that.

**2. Two weights do not match medical reasoning.** Fracture pushes *toward* TB,
and Fibrosis pushes *away* from it — but broken ribs are not a TB sign, and lung
scarring is classically associated with past TB. The model has likely latched
onto patterns that hold in this particular hospital's data and may not hold
elsewhere. The external AUC says the ranking survives this; the shifted scale
in point 1 may be where it shows instead.

**3. It is not a diagnosis.** Confirming TB requires a laboratory test on a
sputum sample. This system decides who is worth a closer look.

---

## Where everything lives

```
apps/api/app/
  intake.py                   step 1 — de-identify, convert, hash
  arms/
    tb_xray.py                steps 2 and 3 — read image, score it
    tb_xray_model.json        the learned weights
    __init__.py               the arm registry
  scoring.py                  step 4 and 5 — history rules, tiers
  pipeline.py                 runs all five steps in order
  audit.py                    tamper-evident record of what happened

scripts/
  fetch_tb_data.py            download the training data
  tb_experiment.py            retrain and measure the model

data/                         downloaded images (not in version control)
```

Adding a second condition later means adding one file under `arms/` and one line
in the registry. Nothing else changes.

---

## Running it

Install the vision libraries (about 2–3 GB; only needed to work on models):

```bash
cd apps/api
uv sync --extra vision
```

The rest of the system runs without this. When the libraries are absent the
X-ray step reports itself unavailable and the pipeline continues instead of
crashing.

Download the training images (about 3.6 GB, fetched in parallel):

```bash
python scripts/fetch_tb_data.py shenzhen
```

Retrain and re-measure:

```bash
python scripts/tb_experiment.py
```

The first run reads all 662 images and takes roughly 30 minutes. Results are
cached, so later runs finish in seconds. This prints the AUC and writes an
updated `tb_xray_model.json`.

Run the tests:

```bash
uv run pytest tests/                      # everything, a few minutes
uv run pytest tests/test_scoring.py       # rules only, under a second
```

---

## Things not to do

**Do not train on the Kaggle TB dataset.** It is assembled from three separate
sources, and 87% of its normal images come from one of them while its TB images
mostly come from the others. A model trained on it can separate the two groups
by recognising the equipment rather than the disease, and will report a very
high accuracy while being useless. Full detail in `SPEC.md` §9.

**Do not trust a very high accuracy figure.** On this task, above roughly 95%
usually means the model has found a shortcut in the data rather than learned
medicine.

**Do not change the image preparation code** in `tb_xray.py` without re-running
`tb_experiment.py`. Errors there do not raise exceptions; they silently degrade
the results.

**Report 0.909 (Montgomery, n=138) as the external figure and 0.877 as
internal.** Never tune anything on Montgomery: it is the only external set, and
the moment it informs a choice it stops being one. A retrained model is
unvalidated until `scripts/tb_external.py` has been run on it.
