# Mirai arm — how it works

A four-view screening mammogram goes in — right and left MLO, right and left
CC, as the DICOMs the machine wrote. Out comes the probability of a
breast-cancer diagnosis within one, two, three, four and five years, and the
five-year figure placed on the same 0–100 scale as every other arm.

The model is **Mirai** (Yala et al., *Science Translational Medicine* 2021,
MIT CSAIL): trained on 210,819 exams at MGH and validated on 128,793 exams
across MGH, Karolinska and Chang Gung Memorial Hospital, with a five-year
C-index of 0.76–0.81. MIT licence, covering the trained weights.

It runs **on this machine, on the CPU**, as the authors' own serving container.
No GPU and no cloud. See `docs/MAMMOGRAM_OPTIONS.md` for how we got here and
why the earlier remote server was the wrong design.

---

## Running it

```bash
npm run dev            # starts Mirai first (scripts/start-mirai.mjs), then the app
npm run mirai:up       # or just Mirai: docker compose up -d mirai
npm run mirai:logs     # watch it
```

`docker-compose.yml` runs `mitjclinic/mirai:v0.14.1` — the maintained image from
the authors' group (`reginabarzilaygroup/Mirai` with its `ark` serving layer),
pinned so the model cannot change underneath a demonstration. 3.7 GB on disk.
Docker Desktop must be running; if it is not, `npm run dev` says so and starts
everything else.

**Why a container and not a library:** Mirai pins Python 3.8 and torch 1.9.
torch 1.9 has no wheel for our Python 3.12, so it cannot share the API's
environment. The container ships its own.

### Measured on this machine

Intel Core Ultra 5 125H, 15.5 GB RAM, no NVIDIA GPU:

| `ARK_THREADS` | one four-view exam |
|---|---|
| 4 (image default) | 52 s |
| **8 (what we run)** | **43 s** |
| 16 | 49 s |

The authors note in their source that they have never seen a gain above 8.
Idle, the container uses about 830 MB of RAM.

## What goes in

**Files:** `apps/api/app/intake.py`, `apps/api/app/arms/mirai.py`

Four `.dcm` files, identified as mammograms by their `Modality = MG` tag. Mirai
arranges them by `ImageLaterality` (R/L) and `ViewPosition` (MLO/CC), so:

- All four views must be present, each once. Three files, or two right CCs, is
  an error with the missing or doubled view named — checked here, before
  anything is sent.
- A film without those tags cannot be placed. It is stored with a warning at
  intake and the arm says which files carried no tags.

**De-identification.** A mammogram has to reach Mirai as a DICOM, so it is
stored as one with everything removed except the pixels and the tags that
describe the image. Patient, physician, institution, dates and private tags
are gone before the file is written to disk. **Verified not to change the
answer:** the authors' demo exam gives identical risks, to four decimal
places, before and after.

## The call

`POST http://127.0.0.1:5000/dicom/files`, multipart, the four files each under
the field `dicom`, plus a required field `data` sent as `{}`. The answer:

```json
{"data": {"predictions": {"Year 1": 0.001, "Year 2": 0.0028, "Year 3": 0.0052,
                          "Year 4": 0.0084, "Year 5": 0.0115}},
 "message": null, "runtime": "43.10s", "statusCode": 200}
```

A refusal is HTTP 400 with the reason in `message` (for example *"Require
exactly 4 images, instead we got 3"*), and that reason is what the screen
shows. If nothing is listening, the screen says to run
`docker compose up -d mirai`. `MIRAI_URL` and `MIRAI_TIMEOUT_SECONDS` (180)
are settings.

## The score

The five-year risk, log-linear between two anchors:

| Five-year risk | Arm score | Meaning |
|---|---|---|
| 1.7% | 30 | an average woman of screening age; top of the low tier |
| 4.5% | 65 | about Mirai's high-risk decile; senior review |

The anchors are an underwriting judgement and sit at the top of
`arms/mirai.py`. The review panel shows all five yearly risks against the
average, the views read, and how long the model took.

## How we know it is right

`apps/api/tests/test_mirai.py` runs the real model when the container is up:

- The authors publish what Mirai returns for their own demo exam
  (`scripts/fetch_mirai_demo.py` fetches it). Run through our intake and our
  arm, it gives exactly `0.0298, 0.0483, 0.0684, 0.09, 0.1016`.
- Our demo films give `0.001 … 0.0115` every time — the same numbers the old
  remote server returned, so the local container reproduces it.

Without the container those tests skip and say why; the rest still run.

## Caveats

- **Image only.** The served model ignores clinical risk factors even when
  they are sent (reginabarzilaygroup/Mirai#14). We send none and claim none;
  the declared history reaches the score through the scoring rules.
- **Our demo films are not what Mirai was trained on.** They are CBIS-DDSM —
  digitised screen-film, 16-bit, re-tagged by a script — not the Hologic
  digital screening exams in Mirai's training set. The model accepts them and
  the answer is plausible, but no published validation covers them.
- Screening populations in the US, Sweden and Taiwan. **Not validated in
  South Asia**, and not validated on diagnostic (symptomatic) exams.
- A risk estimate, not a finding. For an exam above the low tier a heatmap is
  drawn by a second server in the same image (`Mirai/explain`, service
  `mirai-explain`): gradient x activation at the locations Mirai's max pool
  kept, checked against occlusion on the demo exam (see
  [HEATMAPS.md](HEATMAPS.md)). It is kept only when that server's risk equals
  the reader's exactly. It marks where the risk came from, not a lesion.
- The authors state the code is for research and not for clinical decisions.

## Files

    docker-compose.yml                the mirai service
    scripts/start-mirai.mjs           predev: starts it with npm run dev
    scripts/fetch_mirai_demo.py       the authors' demo exam, for the tests
    apps/api/app/arms/mirai.py        view check, the call, the score
    apps/api/app/intake.py            `_mammogram`: the de-identified DICOM
    apps/api/app/pipeline.py          set arms: one run over all files of a kind
    apps/api/tests/test_mirai.py
