# Mirai arm — how it works

A four-view screening mammogram goes in — right and left MLO, right and left
CC, as the DICOMs the machine wrote. Out comes the probability of a
breast-cancer diagnosis within one, two, three, four and five years, and the
five-year figure placed on the same 0–100 scale as every other arm.

The model is **Mirai** (Yala et al., *Science Translational Medicine* 2021,
MIT CSAIL): a deep network trained on 210,819 exams at MGH and validated on
128,793 exams across MGH, Karolinska and Chang Gung Memorial Hospital, with a
five-year AUC of 0.76–0.81 and equal accuracy across races. It runs on a
teammate's server as the published OncoServe container
(`2D_Mammo_Cancer_Mirai`); nothing about the model lives in this repository.

---

## What goes in

**Files:** `apps/api/app/intake.py`, `apps/api/app/arms/mirai.py`

Four `.dcm` files uploaded on the "Mammogram" panel. Mirai arranges them by
their `ImageLaterality` (R/L) and `ViewPosition` (MLO/CC) tags, so:

- All four views must be present, each once. Three files, or two right CCs,
  is an error with the missing or doubled view named — not a wrong answer
  from the server.
- A film without those tags cannot be placed. It is stored with a warning
  at intake and the arm says which files carried no tags. The teammate's
  `Mirai/dcmMetadataAdder/script.py` writes them onto files that lack them.

**De-identification.** Every other DICOM in this system is discarded and kept
only as a PNG. A mammogram has to reach Mirai as a DICOM, so it is stored as
one with everything removed except the pixels and the tags that describe the
image (modality, manufacturer, laterality, view, geometry, windowing). Patient,
physician, institution, dates and private tags are gone before the file is
written to disk, and `PatientIdentityRemoved = YES` marks it. That is the file
that leaves this machine. The review screen draws it as a PNG on the way out.

## The call

`POST {MIRAI_URL}` as `multipart/form-data`, the four files under the field
`dicom`. The server answers:

```json
{"prediction": [0.0010, 0.0028, 0.0052, 0.0084, 0.0115], "model_name": "2D_Mammo_Cancer_Mirai", "msg": "OK", ...}
```

the cumulative risk at one to five years. Four 25 MB films and a CPU inference
take about three minutes; the call runs in the background scoring task with a
fifteen-minute timeout. `MIRAI_URL` (default: the teammate's server) and
`MIRAI_TIMEOUT_SECONDS` are settings; an empty URL makes the arm unavailable
and the intake form says so.

## The score

The five-year risk, log-linear between two anchors:

| Five-year risk | Arm score | Meaning |
|---|---|---|
| 1.7% | 30 | an average woman of screening age; top of the low tier |
| 4.5% | 65 | about Mirai's high-risk decile; senior review |

The anchors are an underwriting judgement and sit at the top of
`arms/mirai.py`. The review panel shows all five yearly risks against the
average, the views that were read, and the server's model version.

## Caveats

- Screening populations in the US, Sweden and Taiwan. **Not validated in
  South Asia**, and not validated on diagnostic (symptomatic) exams.
- A risk estimate, not a finding: Mirai does not say where on the film it
  looked, so there is no heatmap.
- The model is remote. If the server is down the arm reports that and the
  application scores on its other evidence.

## Files

    apps/api/app/arms/mirai.py     view check, the call, the score
    apps/api/app/intake.py         `_mammogram`: the de-identified DICOM
    apps/api/app/pipeline.py       set arms: one run over all files of a kind
    apps/api/tests/test_mirai.py
    Mirai/Test/                    four test films (gitignored) and the tag script
