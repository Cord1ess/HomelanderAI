# Heatmaps: what each one shows, and how we know it is not noise

Every reader that looks at an image or a signal can draw where its reading
came from. A heatmap is easy to draw and easy to trust, and both of those are
problems: a map that looks plausible can be unrelated to what the model did.
So each one here was tested against something it could fail, and the method
that ships is the one that passed. Measured on 2026-10-03; the scripts are in
the last section.

Three rules hold for every reader:

1. **A map is drawn only to explain a reading above the low tier.** Below it
   there is nothing to explain, and a map scaled to its own brightest point
   would paint noise as if it meant something. The screen says why no map
   was drawn.
2. **The arm says what its map shows.** The caption under each map comes from
   the arm (`details.heatmap.note`), not from a generic sentence in the page.
3. **The map supports the reading, never the reverse.** If drawing it fails,
   the score stands and the screen says the map could not be drawn.

## How a map is tested

- **Occlusion** is the reference: hide one part of the input, run the model
  again, and measure how far the output falls. It is slow — one model run per
  part — but it is what the model actually did, by definition.
- **Deletion**: hide the parts a map marks and, separately, the same amount at
  random. A map worth drawing makes the output fall much further.
- **Localisation**, where experts have marked the disease: how much of the map
  falls on the marked areas compared with their share of the image, and how
  often the map's brightest point lands on one ("pointing game").

## 12-lead ECG — lead flattening (changed)

**What it used to draw:** the gradient of the reported abnormality's
probability with respect to the signal, summed over leads, as bands across
the time axis.

**What was wrong.** On CODE-test true positives (12 tracings per class, 6
classes), flattening the 10% of the time axis that map marked lowered the
probability *no more than flattening a random 10%* for right and left bundle
branch block, sinus bradycardia and sinus tachycardia (for tachycardia it did
less). Scrambling the network's last layer left the map almost unchanged
(rank correlation 0.86-0.90 with the original), so it was tracing where the
signal had energy, not the evidence. On a normal tracing it was the gradient
of a probability near zero, stretched to full brightness.

**Why not another time-axis map.** For right bundle branch block and atrial
fibrillation, no single 0.25 s window of any lead removed even 4% of the
probability; for left bundle branch block the best one removed 23%, where
flattening whole leads removed up to 65%. The network reads these findings
from every beat, so a map along the time axis would mostly mark noise.
Integrated gradients did beat random (2-4 times the fall), but named V1 as the
top lead for every class, which is generic rather than evidence.

**What ships:** each lead is flattened in turn and the network run again; the
share of the reported abnormality's probability that disappears is that
lead's weight, tinted on its row and printed beside it. Measured, not
estimated, and it reads like a cardiologist would expect:

| Tracing | Leads carrying the finding |
|---|---|
| Right bundle branch block | V1 29%, I 20%, II 10% |
| Left bundle branch block | I 65%, II 50%, V1 40%, V6 14% |
| Atrial fibrillation | no lead above 3%: the irregular rhythm is in all of them, and the caption says so |

Cost: twelve extra network runs in one batch, well under a second. Drawn only
when an abnormality is reported.

## Retina — SmoothGrad (changed)

**What it used to draw:** the head's weights over the backbone's 16 x 16 grid
of features — exact for the score, since the score is the average of those
cells, but each cell is 32 px of a 512 px photograph.

**What was wrong.** Exact for the score is not the same as pointing at the
disease. On IDRiD's 81 photographs with expert lesion masks
(microaneurysms, haemorrhages, hard and soft exudates), its brightest point
landed on a lesion in about half of them, and its heat on lesions was only
1.3 times their share of the retina. On healthy eyes it still lit 11% of the
retina.

**Compared on 14 IDRiD photographs (lesions dilated 8 px):**

| Method | Heat on lesions (x their area) | Brightest point on a lesion | Logit fall, top 5% blurred (random 5%) |
|---|---|---|---|
| Grid map (old) | 1.38 | 36% | 0.84 (0.04) |
| Occlusion, 32 px patches | 1.43 | 29% | 2.69 (0.11) |
| **SmoothGrad, gradient x input** | **1.75** | **86%** | **1.70 (-0.02)** |

**What ships:** SmoothGrad — the gradient of the referable logit times the
pixels, averaged over 16 noisy copies, blurred by 4 px, seeded so one
photograph always gets one map (two independent runs agree at rank
correlation 0.90-0.95). Drawn as a ring round each marked spot with a light
tint inside, so the lesion it marks stays visible. About 20-30 s on a laptop
CPU, only for readings above the low tier.

## Mammogram — new

Mirai previously drew nothing. It now has a map, served by a small second
server in the authors' own image (`Mirai/explain`, compose service
`mirai-explain`): same model, same weights, same preprocessing.

**Method.** Mirai's image encoder ends in a global *max* pool: each of its 512
features is the value at one location of one view. The map is gradient x
activation at those locations — which location supplied each feature, weighted
by how much that feature raised the five-year logit. Textbook Grad-CAM was
rejected first: it averages gradients over the whole view, which a max pool
does not do.

**Checked against occlusion** on the authors' demo exam (5-year risk 10.2%):
each 256 px patch of each view blurred in turn, Mirai re-run, 135 patches. Of
the map's five strongest patches, 3 sit on or next to one of occlusion's five
strongest; a random choice manages 0.8 on average (95th percentile 2). The
strongest spot it draws, on the left CC view, is where occlusion found the
largest single effect (blurring it lowers the five-year logit by 0.65). Over
all 135 patches the rank agreement is weak (0.1-0.25 across variants), because most patches change
nothing and their order is noise: the map is right about where the strongest
evidence is, and should not be read finely beyond that. One exam is thin
evidence; it is what this machine could run (occlusion took an hour).

**Safeguard.** The reader asks for the map only above the low tier, and keeps
it only if the explain server's risk equals the reader's to the last digit —
a map of a different number would be worse than none. If the server is down,
the risk stands and the screen says the map is missing.

## Chest X-ray — occlusion (changed)

**What it used to draw:** Grad-CAM (eigen-smoothed) on the one finding that
contributed most to the TB score.

**What was wrong.** Tested on TBX11K films that read as TB, against the boxes
radiologists drew round the TB lesions (the boxes cover about 9% of a film),
that map was indistinguishable from random:

| Method | Brightest point in a box | Heat in the boxes (x their area) | Films |
|---|---|---|---|
| Grad-CAM on the top finding (old) | 8-13% | 0.88-0.91 | 13 and 15 |
| Grad-CAM on the TB logit itself | 15% | 1.19 | 13 |
| SmoothGrad on the TB logit | 27% | 1.26 | 15 |
| **Occlusion, 7 x 7 regions** | **38%** | **1.79** | 13 |

(Chance is the boxes' share of the film: about 9% and 1.0.) The deletion test
used for the retina does not work on radiographs: greying out 5% of scattered
pixels changes the film's texture so much that even a random 5% moves the TB
logit by about 5, so it was not used to rank these.

**What ships:** occlusion. The 224 px film the model reads is cut into a
7 x 7 grid; each region is greyed out in turn, 49 films in one batch, and a
region is as red as the TB logit falls without it, with a ring round the
strongest. If no region lowers it by 0.05, no map is drawn and the screen
says the reading comes from the film as a whole. About 10-20 s on a quiet
laptop CPU, only above the low tier.

**Limit, said on the screen.** Even the best map found the radiologist's box
about four times in ten. The TB model reads eighteen general findings
(consolidation, nodules, effusion...) and combines them; it was never trained
to find TB lesions, so what it leans on is not always where a radiologist
would point. The caption says so.

## Reproducing

    # accuracy of every reader, through the real intake path
    apps/api/.venv/Scripts/python.exe scripts/validate_models.py all

    # the survival model's peers (see docs/MORTALITY.md)
    apps/api/.venv/Scripts/python.exe scripts/survival_peers.py

The heatmap experiments themselves were run as one-off scripts against the
same arms and datasets: CODE-test (ECG), IDRiD segmentation masks (retina,
CC-BY-4.0, `data/dr/raw/idrid_segmentation.zip`), TBX11K boxes (chest,
CC-BY-4.0, `data/tbx11k/`, fetched by HTTP range reads of the Kaggle archive
so only the films needed come down), and the Mirai demo exam.
