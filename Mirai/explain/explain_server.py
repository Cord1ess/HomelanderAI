"""Where in the mammogram Mirai's five-year risk came from.

A second, small server in the authors' own image (`mitjclinic/mirai`), beside
the one that answers `/dicom/files`. Same model, same weights, same
preprocessing — `MiraiModel.run_model` does all of it — with one change: the
step that turns the four views into a risk also keeps what the network's last
convolutional block saw and how the five-year logit depended on it.

**The method is exact for this network.** Mirai's image encoder ends in a
global *max* pool: each of its 512 features is the value of one location on one
view, and every other location contributes nothing. So the five-year logit's
dependence on a location is gradient x activation at the locations that won
the max, summed over the features they supplied — not an estimate smoothed
over the image, which is what Grad-CAM would give and why it is not used here.
Only locations that pushed the risk up are drawn.

It was checked against occlusion (blur a patch, re-run Mirai, measure the fall
in the logit) before it shipped; see docs/HEATMAPS.md.

    POST /explain     multipart, four `dicom` parts, as /dicom/files
    -> {"data": {"predictions": {"Year 1": ...}}, "heatmap_png": base64, "views": [...]}

Python 3.8: that is what the image carries.
"""

import base64
import io
import json
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F
from flask import Flask, jsonify, request
from PIL import Image, ImageDraw

sys.path.insert(0, "/app/ark")
from models.base import ArgsDict
from onconet.models.mirai_full import MiraiModel

CONFIG = "/app/ark/api/configs/mirai.json"
app = Flask(__name__)


def _args():
    with open(CONFIG) as handle:
        args = ArgsDict(json.load(handle)["MODEL_ARGS"])
    args.cuda = False
    return args


def _attribute(store):
    """The patched `process_image_joint`: Mirai's own prediction, plus the map."""

    def joint(batch, model, calibrator, risk_factor_vector=None):
        model = model.cpu().eval()
        # Gradients are needed from the last block onward only. With the
        # weights frozen and the input not requiring grad, nothing below it
        # builds a graph, so this costs about what inference does.
        for p in model.parameters():
            p.requires_grad_(False)
        held = {}

        def cut(module, inputs, output):
            leaf = output.detach().requires_grad_(True)
            held["act"] = leaf
            return leaf

        hook = model.image_encoder._model.layer4_1.register_forward_hook(cut)
        try:
            with torch.enable_grad():
                logit, _, _ = model(batch["x"], None, batch)
                logit[0, 4].backward()
        finally:
            hook.remove()
        act, grad = held["act"].detach(), held["act"].grad.detach()
        store["map"] = (grad * act).sum(dim=1).numpy()  # (4, h, w), signed
        store["x"] = batch["x"][0].transpose(0, 1)[:, 0].numpy()  # (4, H, W)
        store["side"] = batch["side_seq"][0].tolist()  # 0 = R
        store["view"] = batch["view_seq"][0].tolist()  # 0 = CC
        # Exactly what Mirai reports: the calibrated probability for each year.
        probs = torch.sigmoid(logit).detach().cpu().numpy()
        return [
            float(calibrator[i].predict_proba(probs[0, i].reshape(-1, 1)).flatten()[1])
            for i in calibrator
        ]

    return joint


def _render(store) -> tuple:
    """The four views in the usual hanging order — right and left MLO above,
    right and left CC below, breasts back to back — with the map in red."""
    up = np.maximum(store["map"], 0.0)
    # No scipy in the image: a 5x5 Gaussian (sigma one cell) and the upscale in torch.
    ax = torch.arange(5, dtype=torch.float32) - 2
    g = torch.exp(-(ax ** 2) / 2.0)
    kernel = (g[:, None] * g[None, :] / g.sum() ** 2)[None, None]
    # One cell is 32 px; smooth by one cell so a single location reads as a
    # spot rather than a square. Scaled across the whole exam, so a quiet view
    # stays quiet next to a loud one.
    cells = torch.from_numpy(up.astype(np.float32))[:, None]
    smooth = F.conv2d(F.pad(cells, (2, 2, 2, 2), mode="replicate"), kernel)
    peak = float(smooth.max()) or 1.0
    tiles, shares = {}, []
    total = float(up.sum()) or 1.0
    for i in range(4):
        side = "R" if store["side"][i] == 0 else "L"
        view = "CC" if store["view"][i] == 0 else "MLO"
        x = store["x"][i].astype(np.float32)
        lo, hi = np.percentile(x, 1), np.percentile(x, 99.5)
        base = np.clip((x - lo) / (hi - lo + 1e-9), 0, 1)
        heat = F.interpolate(smooth[i : i + 1], size=x.shape, mode="bilinear", align_corners=False)
        heat = heat[0, 0].numpy() / peak
        alpha = np.clip((heat - 0.15) / 0.6, 0, 1)[..., None] * 0.75
        rgb = np.stack([base] * 3, -1) * (1 - alpha) + np.array([1.0, 0.15, 0.1]) * alpha
        image = Image.fromarray((rgb * 255).astype(np.uint8))
        # Mirai turns every view to face left. Turn the left breast back, so
        # the pair sits back to back as a radiologist hangs them.
        if side == "L":
            image = image.transpose(Image.FLIP_LEFT_RIGHT)
        image = image.resize((x.shape[1] // 4, x.shape[0] // 4))
        ImageDraw.Draw(image).text((8, 6), side + " " + view, fill=(255, 255, 255))
        tiles[(side, view)] = image
        shares.append({"view": side + " " + view, "share": round(float(up[i].sum()) / total, 3)})
    w, h = tiles[("R", "MLO")].size
    sheet = Image.new("RGB", (w * 2 + 6, h * 2 + 6), (0, 0, 0))
    for (side, view), image in tiles.items():
        sheet.paste(image, ((0 if side == "R" else w + 6), (0 if view == "MLO" else h + 6)))
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return buffer.getvalue(), shares


@app.route("/info", methods=["GET"])
def info():
    return jsonify(
        {"service": "mirai-explain", "method": "gradient x activation at max-pool winners"}
    )


@app.route("/explain", methods=["POST"])
def explain():
    started = time.time()
    files = request.files.getlist("dicom")
    if len(files) != 4:
        return jsonify({"message": f"four views are needed, got {len(files)}"}), 400
    store = {}
    model = MiraiModel(_args())
    # On this instance only: the server stays safe for the next request.
    model.process_image_joint = _attribute(store)
    try:
        report = model.run_model([io.BytesIO(f.read()) for f in files])
    except Exception as exc:  # noqa: BLE001 - the message reaches the screen
        return jsonify({"message": f"{type(exc).__name__}: {exc}"}), 400
    png, shares = _render(store)
    return jsonify(
        {
            # Shaped as ark's own answer, so the reader's parser reads both.
            "data": {"predictions": report["predictions"]},
            "heatmap_png": base64.b64encode(png).decode("ascii"),
            "views": shares,
            "runtime": round(time.time() - started, 1),
        }
    )
