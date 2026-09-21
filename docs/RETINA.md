# Retinopathy Screening — how it works

A colour photograph of the back of the eye goes in. A risk score from 0 to 100
comes out, with a five-point severity grade, a heatmap, and a statement of how
well the model has been tested.

This is a **screening** tool. It never diagnoses anyone and never rejects
anyone. A high score means "a person should look at this", nothing more.

Diabetic retinopathy matters to an underwriter for a reason that has little to
do with eyesight: it is damage to small blood vessels that can be *photographed*.
The same damage is happening in the kidneys, nerves and heart, where it cannot.
An applicant with referable retinopathy has diabetes that has been poorly
controlled for years, whatever the questionnaire says.

---

## What this replaced

The previous retina arm (`eyepacs_dr.py`) described itself as a ResNet-50
pretrained on 35,126 EyePACS images and validated on APTOS 2019 at 0.942 AUC.
None of that was true. It imported no neural network. It counted dark pixels and
bright pixels and passed the counts through a formula, and the 0.942 appeared
nowhere except in the file that stated it.

Measured on ten real photographs with published grades, it scored a
proliferative eye — the most severe grade there is, haemorrhages plainly
visible — at **17.5**, below two healthy eyes (19.8 and 25.2), and missed a
moderate case entirely. The same ten through the arm described here:

| Photograph | True grade | Old score | New score |
|---|---|---|---|
| 13_left | 0 none | 19.8 | PENDING |
| 17_left | 0 none | 25.2 | PENDING |
| 15_right | 2 moderate | 9.3 | PENDING |
| 16_left | 4 proliferative | 17.5 | PENDING |
| 16_right | 4 proliferative | 38.0 | PENDING |

Those ten are **not validation** — see "Which numbers are honest" below. They
are the fixed point the old arm failed on, nothing more.

---

## The five steps

```
fundus photograph
    │
    ▼
1. INTAKE          strip metadata, convert to PNG, record a hash   (shared with TB)
    │
    ▼
2. FRAMING         find the lit disc, pad to a square, resize to 512
    │
    ▼
3. BACKBONE        FLAIR ResNet-50, frozen -> 2,048 features
    │
    ▼
4. HEAD            our logistic regression -> probability of referable DR
    │
    ▼
5. HISTORY + TIER  declared diabetes history adjusts it; low / moderate / elevated
```

### Step 2 — Framing

**File:** `apps/api/app/arms/fundus.py`

A fundus camera photographs a disc of retina onto a black rectangle. The disc is
cropped out, **padded to a square, never stretched**, and resized. Many cameras
clip the top and bottom of the disc, so its bounding box is wider than tall;
resizing that straight to a square would turn every round microaneurysm into an
oval, which is what the old arm did.

Framing also **refuses** what is not a colour fundus photograph: a frame that is
almost entirely black, a greyscale image, or one too dark to read. A grading
model handed a chest X-ray does not decline. It answers, and the answer looks
like a real one — the old arm returned 98.8 on a lung. Triage and `Arm.accepts`
stop that first; this is the backstop. The thresholds were measured, not
guessed: across PENDING real photographs from four datasets, PENDING were
refused.

### Step 3 — The backbone

**FLAIR** (Silva-Rodríguez et al., *Medical Image Analysis* 2025), Apache-2.0. A
ResNet-50 pretrained on 288,307 fundus photographs from 37 public datasets. We
use its vision tower unchanged and frozen. It turns out to be a stock torchvision
ResNet-50 with the classifier removed, so no FLAIR code is needed to run it.

The weights are 533 MB, so they are not in the repository. The arm downloads
them on first use, the way torchxrayvision does for the chest model, and
**refuses a file that does not match its pinned SHA-256**. Weights that changed
underneath us would make every stored score unattributable.

Why frozen, and not fine-tuned: measured on this project's hardware, a ResNet-50
trains at 0.9 images a second. Ten epochs over even a small dataset is eleven
hours. Extracting features is one inference pass per image, and is cached.

### Step 4 — The head

**Files:** `apps/api/app/arms/dr_fundus.py`, `dr_fundus_model.json`

Two logistic regressions over the 2,048 features, trained by
`scripts/dr_experiment.py`:

- **Referable or not.** This sets the score: the probability, times 100, that
  the photograph shows ICDR grade 2 (moderate) or worse. That is the decision
  every regulated screening system is judged on, which is why it is the one with
  published numbers to compare against.
- **The five-point grade** — none, mild, moderate, severe, proliferative. Shown
  to the underwriter. It does not set the score.

Trained on **DDR**: 12,522 gradable photographs from 147 hospitals and 42 camera
types across China, with the official train/valid/test split restored.
Regularisation was chosen on the validation split — never on the test split, and
never on an external set.

As with the chest model, the weights are plain JSON and scoring needs only
numpy. scikit-learn trains the head; it is not needed to run it.

### Step 5 — History and tier

Shared with the chest arm (`scoring.py`). Three rules read the retina panel:
diabetes for over ten years (+15), for five to ten (+8), and hypertension
alongside it (+10).

---

## The heatmap

The score is an average over a 16×16 grid. That is not an approximation: the
head is a linear layer on features that are themselves an average over that
grid, so *weights · activations*, cell by cell, **is** the score, taken apart by
location. The overlay draws those cells. A test checks that they add back up to
the score to four decimal places.

Grad-CAM reduces to exactly this for a network of this shape, which is why the
artifact is filed as one. Computing it directly needs no backward pass, and has
none of Grad-CAM's smoothing to go wrong: the first version, built on the
library, highlighted the black corner of the frame.

It is cyan rather than the chest arm's red, because a retina is already red and
haemorrhages are the darkest red in it.

It earns its place. One healthy eye among the samples scores 42, in the moderate
band. The map shows why: the model is reacting to a hazy bright artefact at the
edge of the photograph, not to a lesion. An underwriter can see that and
discount it. Without the map they could not.

---

## Which numbers are honest

This is the retina equivalent of the Kaggle TB trap, and it is easy to fall into.

**FLAIR was pretrained on DDR, APTOS, EyePACS and the IDRiD training set — with
their grades.** The backbone has seen those photographs *and the answers*. A
score on any of them says nothing about a new patient.

The size of the effect, measured here on identical code:

| IDRiD photographs | Referable-DR AUC |
|---|---|
| All 516 (413 of them seen in pretraining) | PENDING |
| The 103 FLAIR never saw | PENDING |

So only results on data the backbone never saw are reported as validation, the
model file names exactly which results those are (`validated_on`), and a test
fails if the sentence shown beside a score quotes anything else.

The ten EyePACS sample photographs in `samples/retina/` are in the same
position: FLAIR has seen EyePACS. They prove the arm runs end to end on real
camera output. They are not evidence of accuracy and must never be reported as
such.

---

## How well it works

PENDING — results table

### Against the published systems

| System | Setting | Referable-DR result |
|---|---|---|
| Gulshan et al., *JAMA* 2016 | Messidor-2 | AUC 0.990 |
| Ting et al., *JAMA* 2017 | 10 external sets | AUC 0.889 – 0.983 |
| IDx-DR pivotal trial (Abràmoff 2018), FDA-cleared | primary care, n=900 | sens 87.2% / spec 90.7% |
| EyeArt pivotal trial (Ipp 2021), FDA-cleared | — | sens 95.5% / spec 85.0% |
| Voets 2019, public-data replication of Gulshan | EyePACS → Messidor-2 | AUC 0.951 → **0.853** |
| Lee 2021, seven commercial systems | real-world VA data | sensitivity 51% – 86% |

Those systems were fine-tuned end to end on hundreds of thousands of images
graded by panels of ophthalmologists. This one is a frozen backbone and a
logistic regression trained on a laptop CPU.

### Which backbone, and why

PENDING — comparison table

---

## Limits to state honestly

**1. It has never been tested on the people it would be used on.** Every dataset
here is a diabetic screening population, where a third to a half of photographs
are referable. Among insurance applicants the rate is a few percent. Sensitivity
and specificity carry over; **the chance that a flagged applicant actually has
retinopathy does not**, and will be far lower. This is a change of population
*and* of purpose, the same limit SPEC §10 names for every arm.

**2. Thresholds travel worse than rankings.** AUC measures whether diseased eyes
score above healthy ones, and that holds up across hospitals. The platform,
though, acts at fixed scores of 30 and 65, and the same score does not mean the
same thing on every camera. Read the operating points in the table above, not
just the AUC.

**3. Mild retinopathy is the weak spot**, as it is for every system. One or two
microaneurysms are a few pixels across. The score targets grade 2 and above
partly for that reason.

**4. Photograph quality matters, and is not yet checked.** DeepDRiD's own graders
called about half its photographs poor; the table above shows what that costs.
Framing refuses the unreadable, but a blurry photograph that is still
recognisably a retina is scored like any other.

**5. One photograph of one eye.** Screening programmes grade two fields of both
eyes and take the worse. The pipeline's "highest score governs" rule does the
second half of that if both eyes are uploaded.

**6. Macular oedema is not assessed.** It is the other half of a real screening
referral. IDRiD and DeepDRiD carry labels for it, so it is within reach.

**7. It is not a diagnosis.** That takes an ophthalmologist and a dilated exam.

---

## What was considered and not used

**A commercial API.** There is no usable one. Every regulated system — EyeArt,
LumineticsCore (IDx-DR), AEYE, Google's ARDA, RetCAD — is sold under contract,
not self-serve, and all of them mean sending an applicant's retinal photograph
to a third party, which the platform exists to avoid. The one genuinely callable
option, community models on Roboflow, is unvalidated hobby work with
undocumented training data.

**RETFound**, the best-known retina foundation model. Its official weights are
gated. An independent benchmark found that frozen, it transfers *worse* than an
ImageNet network (0.697 referable AUC from APTOS to Messidor-2).

**MedGemma** and other medical language-vision models. They generate text; they
do not produce a calibrated probability, and the model card reports 65–77%
five-class accuracy on EyePACS.

**Fine-tuning.** Eleven hours per run on this hardware. With a GPU it is the
obvious next step and would probably be worth several points of AUC.

**Messidor-2**, the standard external benchmark, and one FLAIR never saw. ADCIS
prohibits redistribution, so the mirrors that exist are not legitimate and were
not used. Request it at <https://www.adcis.net/en/third-party/messidor2/>; the
adjudicated grades (Krause 2018) are public. **This is the single most valuable
next step**, the retina counterpart of Montgomery for TB.

---

## Licences

| Thing | Licence | Note |
|---|---|---|
| FLAIR weights and code | Apache-2.0 | Commercial use permitted |
| DDR | MIT per its GitHub repository | Images reached through a community mirror; grade counts verified against the paper |
| IDRiD | CC BY 4.0 | The only dataset here with a fully clean licence |
| DeepDRiD | CC BY-SA 4.0 | |
| APTOS 2019 | Kaggle competition rules | Test only, never redistributed |
| RETFound-Green | Non-commercial research only; bars any industry involvement | Comparison only. **Not shipped**, and its library (`timm`) is not a dependency |

---

## Where everything lives

```
apps/api/app/arms/
  fundus.py                   step 2 — framing, and refusing what is not a fundus photo
  dr_fundus.py                steps 3 and 4 — backbone, head, heatmap
  dr_fundus_model.json        the head's weights and every metric quoted here

scripts/
  fetch_dr_data.py            download the datasets and the backbone weights
  dr_experiment.py            train the head, test it externally, write the model file

data/dr/                      downloaded images and cached features (not in version control)
```

---

## Running it

```bash
cd apps/api && uv sync --extra vision --extra nlp     # see README on why both
python scripts/fetch_dr_data.py                       # about 13 GB, no account needed
python scripts/dr_experiment.py train flair           # first run: about 90 minutes on CPU
```

Features are cached under `data/dr/features/`, so every later run takes seconds.
To re-run the comparison that chose the backbone:

```bash
uv pip install timm                                   # comparison backbones only
python scripts/dr_experiment.py compare
```

Tests:

```bash
apps/api/.venv/Scripts/python.exe -m pytest tests/test_dr_fundus.py tests/test_fundus.py
```

Those that load the backbone skip themselves when torch or the weights file is
absent, so the suite stays green for anyone not working on models.

---

## Things not to do

**Do not train on APTOS.** The resolution of an APTOS image predicts its label by
itself — about 91% on DR versus no DR, measured on 500 images — because
different clinics used different cameras and saw different patients. It is the
Kaggle TB trap again. It is safe as a *test* set only because a model that never
trained on it cannot have learned the shortcut.

**Do not report a number from DDR, APTOS, EyePACS or the IDRiD training set.**
FLAIR has seen them with their grades.

**Do not trust a very high figure.** Above roughly 0.97 on this task, with this
method, means the backbone has seen the test set.

**Do not add ImageNet normalisation.** FLAIR was trained on raw 0–1 pixels. The
usual mean and standard deviation do not raise an error; they silently produce
confident nonsense.

**Do not change `fundus.py` without re-running `dr_experiment.py`.** The head was
fitted to features from photographs framed exactly this way.
