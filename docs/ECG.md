# ECG arm — how it works

A 12-lead ECG goes in as the signal the machine exported. Out come two things:
which of six rhythm and conduction abnormalities the tracing shows, at the
thresholds the authors themselves used, and an ECG age — how old the heart
reads, against how old the applicant is. The first sets the arm's score. The
second is shown beside it and never touches the score.

Both networks are published, peer-reviewed, and downloaded rather than trained
here. What this repository adds is a faithful port, the operating thresholds,
an honest measure of how good each network is on its own public test set, and
the plumbing that gets a CSV from an ECG machine into them.

---

## What goes in

**The signal, not a picture of it.** An ECG machine, a Holter app or a hospital
system exports the tracing as a CSV: one column per lead, one row per sample,
in millivolts. That file is what the intake accepts (`.csv`, `.txt`, `.tsv`).

A scanned or photographed printout is refused. The standard 3×4 strip holds
about 2.5 seconds of each lead at a fidelity that loses the small deflections
these networks read, and the networks were trained on ten seconds of every
lead. Digitising the strip would produce a confident reading of the wrong
thing; saying "send the export" is more useful.

**File:** `apps/api/app/ecg.py`

What the parser insists on, and why:

| Requirement | Why it is not guessed |
|---|---|
| All twelve leads, matched by name (`I`/`DI`/`lead I`, `aVR`, `V1` …) | The networks take twelve channels in a fixed order; eleven is a different input. |
| The sampling rate — a `time` column, or a line such as `fs=500` | A wrong rate stretches or squeezes every QRS complex. A tracing sampled at 500 Hz but read as 400 Hz has a heart rate 20% too low, and the network cannot tell. |
| Millivolts (values in the hundreds are read as microvolts and converted, with a note) | The networks' unit is 0.1 mV; a file in the wrong unit is a tracing ten or a thousand times too large. |
| At least five seconds | Less is not enough signal to say anything about rhythm. |

Anything short of that is refused with the reason, and the operator sees it at
intake as they would an unreadable image.

**What is stored.** The tracing is resampled to 400 Hz, cut or zero-padded to
4096 samples (10.24 s) exactly as the training data was prepared, and saved as
a plain 12×4096 float array (`.npy`). Nothing else from the file survives: an
export's comment line often carries the patient's name and the recording date,
and the stored form has no header to keep them in. The review screen asks for
a picture, so the array is drawn on the way out.

---

## Reading 1: six abnormalities

**Paper:** Ribeiro AH et al., *Automatic diagnosis of the 12-lead ECG using a
deep neural network*, Nature Communications 2020.
**Weights:** Zenodo 3765717, CC-BY-4.0. **Training data:** CODE, 2.3 million
ECGs from the Telehealth Network of Minas Gerais, Brazil.

The six classes are first-degree AV block (1dAVb), right and left bundle
branch block (RBBB, LBBB), sinus bradycardia (SB), atrial fibrillation (AF)
and sinus tachycardia (ST). In the paper the network matched or beat
cardiology residents on all six.

### The port

The network was published as a Keras/TensorFlow model. The API runs PyTorch,
so `app/arms/ecg_nets.py` defines the same architecture and
`scripts/fetch_ecg_models.py` converts the published arrays once. Two details
make a port of this kind silently wrong, and both are reproduced: TensorFlow's
"same" padding puts the odd sample on the right where PyTorch centres it, and
Keras's batch normalisation uses ε = 10⁻³ where PyTorch's default is 10⁻⁵.

The check is the authors' own test set. CODE-test (Zenodo 3765780) ships 827
tracings, the cardiologists' labels, and the decisions the authors' network
made on each one (`annotations/dnn.csv`). The converted network is compared
with those decisions on every run of the fetch script and refused if any
class falls under 99% agreement:

| Class | Agreement with the authors' decisions | AUC vs cardiologists | F1 at the threshold |
|---|---|---|---|
| 1dAVb | 99.6% | 0.994 | 0.84 |
| RBBB | 100% | 0.999 | 0.94 |
| LBBB | 100% | 1.000 | 1.00 |
| SB | 99.9% | 0.997 | 0.86 |
| AF | 99.8% | 0.997 | 0.78 |
| ST | 99.9% | 0.999 | 0.95 |

Those F1 figures are within a few points of the paper's Table 1, which is
what a correct port should give.

### The thresholds are not 0.5

The network keeps its probabilities low even when it is right: a left bundle
branch block it is certain of may come out at 0.2. The authors chose a
threshold per class on a validation set; the paper does not print them, but
their decisions on CODE-test do, and the value that reproduces those
decisions was recovered for each class:

| 1dAVb | RBBB | LBBB | SB | AF | ST |
|---|---|---|---|---|---|
| 0.116 | 0.088 | 0.056 | 0.366 | 0.476 | 0.102 |

An abnormality is **reported** when its probability reaches its threshold.
Reading these at 0.5 would miss most bundle branch blocks; the review screen
draws each probability against its own threshold so the underwriter can see
where the line is.

### The score

Each abnormality has a weight in `ecg_12lead_model.json`, out of 100:

| AF | LBBB | RBBB | 1dAVb | SB | ST |
|---|---|---|---|---|---|
| 100 | 90 | 60 | 50 | 35 | 35 |

A reported abnormality puts the arm's score at its weight; the highest
governs, as it does across arms. Atrial fibrillation and a left bundle branch
block go straight to senior review on their own: the first carries a stroke
risk that needs anticoagulation and a cardiologist's letter, the second is
rarely benign. A right bundle branch block or first-degree block is common and
usually harmless but changes the questions to ask. Sinus brady- and
tachycardia are usually situational — an athlete, a nervous applicant — so
they are only a prompt.

With nothing reported the score stays under 30, rising towards it as the
closest probability approaches its threshold, so a tracing that nearly
crossed a line reads differently from one that was nowhere near.

The weights are an underwriting judgement, not a published finding. They are
in a JSON file so they can be argued about without touching code.

### The picture

The gradient of the reported class's probability with respect to the input,
summed over leads and smoothed to a quarter of a second, shades the tracing
where the network's decision was sensitive. It is the ECG's counterpart to the
chest arm's heatmap and carries the same caveat: it shows where the network
looked, not what a cardiologist would point at.

---

## Reading 2: ECG age

**Paper:** Lima EM et al., *Deep neural network-estimated electrocardiographic
age as a mortality predictor*, Nature Communications 2021.
**Weights:** Zenodo 4892365, CC-BY-4.0 (PyTorch; loaded strictly into the
authors' own network definition, vendored under its MIT licence).

The network was trained to guess a person's age from the tracing alone. The
interesting part is when it is wrong: in 1.56 million patients, those whose
ECG read more than eight years older than they were had 1.79× the mortality
of those whose ECG age matched, after adjusting for the usual risk factors.
It is the same idea as the mortality arm's phenotypic age, read from a
different organ.

### What it does here, and what it does not

Our run of the published weights on CODE-test gives a mean absolute error of
**11.6 years** (r = 0.60), against the paper's 8.4 on its own held-out data,
and the errors are systematic: it reads adults in their twenties about
fifteen years older and the over-80s about ten years younger. A raw gap of
"ECG age minus age" would flag every young applicant.

So the gap is measured against what the model reads for a typical person of
that age — a straight-line fit on CODE-test, `expected = 0.54 × age + 30.1`
— and only a gap past the paper's eight years is called notable. Even then it
is a prompt to look at the tracing and the history, and **it never enters the
score**. The imprecision is printed on the review screen next to the number.

---

## Setup

Needs the `vision` extra (torch, safetensors) and, for the one-time
conversion, the `train` extra (h5py reads the Keras file):

```bash
cd apps/api
uv sync --extra vision --extra train
cd ../..
python scripts/fetch_ecg_models.py
```

That downloads the two weight archives and the test set (about 800 MB, once,
into the gitignored `data/ecg/`), converts both networks to safetensors,
writes their sha256 into `apps/api/app/arms/ecg_12lead_model.json`, runs the
port check above, and writes fifteen CODE-test tracings out as demo CSVs in
`data/ecg/demo/` — two per abnormality, where the cardiologists and the
network agree, plus three normals. Those are what to upload when showing the
arm; `manifest.json` beside them says what each one is.

The arm loads the converted files strictly and refuses one whose hash has
changed. Without them it reports itself unavailable, like the other arms.

## Files

    apps/api/app/ecg.py                      reading, storing and drawing a tracing
    apps/api/app/arms/ecg_nets.py            the two networks, defined so the weights load by name
    apps/api/app/arms/ecg_12lead.py          the arm: thresholds, weights, saliency, ECG age
    apps/api/app/arms/ecg_12lead_model.json  classes, thresholds, weights, validation, weight pins
    scripts/fetch_ecg_models.py              download, convert, check, demo tracings
    apps/api/tests/test_ecg.py

## Caveats, in one place

- Brazilian training data, Brazilian test data. **Not validated in South
  Asia**, and the arm says so on every reading.
- Six abnormalities, not a full ECG read. A normal score here means none of
  the six was found, not that the ECG is normal — ischaemic changes, QT
  prolongation and hypertrophy are outside the model.
- The weights are ours, not the paper's. The paper reports probabilities;
  what they should mean for an insurance application is a judgement made in
  `ecg_12lead_model.json`.
- ECG age is imprecise on the public data (MAE 11.6 years) and is shown as a
  prompt against a typical reading for the applicant's age, never scored.
- A reported abnormality is a reason to obtain the cardiologist's report, not
  a diagnosis. Nothing here decides anything.
