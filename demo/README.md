# Demo dataset

`test/` and `clients/` hold five applicants each, low risk to elevated — drop a
whole folder into the intake form and nothing needs typing. See
`docs/DEMO_SETUP.md` for what each one reads as, and for the `MIRAI_SIMULATE`
switch to use when the mammogram server is down.

The rest of this file is about the twenty chest X-rays below.

---

# Chest X-rays for the showcase

Twenty films from the **Shenzhen** chest X-ray set: ten without tuberculosis and
ten with it. Every one has been scored through the same code the API runs, and
every one lands in the tier its label implies.

Use these for the demo. Do **not** use the images in
`Reference/Nirnoy/assets/samples/` — see "Why not the other folder" below.

---

## `01-normal/` — no tuberculosis

Expected tier: **low** (score 0–30).

| File | Vision score | Tier |
|---|---|---|
| `normal-01-shenzhen-0197_0.png` | 1.2 | low |
| `normal-02-shenzhen-0039_0.png` | 6.5 | low |
| `normal-03-shenzhen-0225_0.png` | 8.9 | low |
| `normal-04-shenzhen-0208_0.png` | 10.3 | low |
| `normal-05-shenzhen-0213_0.png` | 11.7 | low |
| `normal-06-shenzhen-0143_0.png` | 13.1 | low |
| `normal-07-shenzhen-0156_0.png` | 14.3 | low |
| `normal-08-shenzhen-0221_0.png` | 16.4 | low |
| `normal-09-shenzhen-0092_0.png` | 19.1 | low |
| `normal-10-shenzhen-0118_0.png` | 25.5 | low |

## `02-tuberculosis/` — tuberculosis present

Expected tier: **elevated** (score above 65).

| File | Vision score | Tier |
|---|---|---|
| `tb-01-shenzhen-0648_1.png` | 100.0 | elevated |
| `tb-02-shenzhen-0403_1.png` | 99.5 | elevated |
| `tb-03-shenzhen-0336_1.png` | 98.7 | elevated |
| `tb-04-shenzhen-0479_1.png` | 97.1 | elevated |
| `tb-05-shenzhen-0634_1.png` | 94.9 | elevated |
| `tb-06-shenzhen-0568_1.png` | 92.6 | elevated |
| `tb-07-shenzhen-0467_1.png` | 90.6 | elevated |
| `tb-08-shenzhen-0337_1.png` | 86.2 | elevated |
| `tb-09-shenzhen-0531_1.png` | 81.2 | elevated |
| `tb-10-shenzhen-0619_1.png` | 75.1 | elevated |

The file name keeps its Shenzhen id (`shenzhen-0197_0` is `CHNCXR_0197_0.png`),
so any result can be traced back to the source image. `manifest.json` holds the
same numbers in machine-readable form.

---

## What these scores are

The number above is the **vision score alone** — the chest X-ray on its own,
with no declared history. The score an underwriter sees is the vision score plus
the history rules, so the same film can land in a different tier once symptoms,
prior TB, diabetes and so on are entered. That is the point of the product, and
it is worth demonstrating deliberately:

Use **`tb-10-shenzhen-0619_1.png`** for this. Its vision score is 75.1, which
sits close enough to the cut-points that the history actually moves it across
them. Submit the same file three times, changing only the declared history —
these numbers are measured, not illustrative:

| Declared history | Rule that fires | Score | Tier | Recommendation |
|---|---|---|---|---|
| Nothing | — | 75.1 | elevated | Senior review |
| Prior TB, treatment completed, no symptoms | −25 `prior_tb_scarring` | 50.1 | **moderate** | Standard with adjustment |
| Prior TB **and** a current cough | +25 `prior_tb_relapse` | 100.0 | elevated | Senior review |

One image, three different recommendations, because the same shadow on a lung
means healed scarring or an active relapse depending on something no image model
can see.

Do not use `tb-01` for this — it scores 100, so subtracting 25 still leaves it
`elevated` and the tier never visibly changes.

---

## Honest note on selection

These twenty were **chosen because the model gets them right**. Across the whole
Shenzhen set the model is not perfect:

| | Images | Land in the expected tier |
|---|---|---|
| No tuberculosis | 326 | 220 (67%) |
| Tuberculosis | 336 | 234 (70%) |

So roughly a third of films fall outside the tier their label implies. Picking a
random file from `data/shenzhen/` during a live demo is a real risk. That is not
a bug — it is a model with an AUC of 0.877 rather than 1.0, and the tier
cut-points (30 and 65) are placeholders that have not been tuned against any
cost model.

The scores here are also spread across each band rather than being the ten most
extreme, so the demo shows the model working without pretending it is certain.

## A note on when these numbers were true

The scores above are what the **chest model alone** produces, and since the
routing fix of 2026-09-21 they are also what the platform reports. Before that
fix, the platform ran every model over every file and took the highest score,
and the retina model — which has never seen a lung — scored these same films at
81 to 99. So an application built from this folder used to be reported as
elevated risk regardless of which file was chosen. If a demo recording predates
that fix, its numbers are wrong; re-run it.

## Why not the other folder

`Reference/Nirnoy/assets/samples/` is the Kaggle TB set, and on it this model is
**inverted** — normals average 74 and TB films average 38. Kaggle's normal
images come mostly from a different hospital than its TB images, so a model
trained on Shenzhen reads the source rather than the disease. See `docs/SPEC.md`
§9 and `docs/TB.md`.

## Provenance

Shenzhen chest X-ray set (Shenzhen No. 3 People's Hospital / U.S. National
Library of Medicine), public and de-identified. Fetched by
`scripts/fetch_tb_data.py`. The `_0` / `_1` suffix on the original filename is
the ground-truth label.

`data/` is gitignored — medical images are never committed (`docs/SPEC.md` §9).
Regenerate this folder on another machine by fetching Shenzhen and re-running
the selection.
