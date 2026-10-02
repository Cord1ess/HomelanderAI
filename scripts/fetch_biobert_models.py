"""Download the two BioBERT models the clinical-note reader runs.

    python scripts/fetch_biobert_models.py

Both are BioBERT v1.1 (Lee et al., Bioinformatics 2020) fine-tuned for
biomedical named-entity recognition by A. Alonso, Apache-2.0, ungated:

  drugs      alvaroalon2/biobert_chemical_ner
             fine-tuned on BC5CDR-chemicals and BC4CHEMD
  diseases   alvaroalon2/biobert_diseases_ner
             fine-tuned on BC5CDR-diseases and NCBI-disease

Each is pinned to a commit and its weights to a sha256, checked *before* the
PyTorch pickle is opened — an unpickle runs arbitrary code, so nothing that
does not match is ever loaded. The tensors are then re-saved as safetensors,
so the API never unpickles anything at runtime.

Lands in data/nlp/models/, which is gitignored: about 860 MB, once.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "nlp" / "models"

MODELS = {
    "drugs": {
        "repo": "alvaroalon2/biobert_chemical_ner",
        "commit": "b57181cea10a3943c35cf31bb375ff9217886730",
        "sha256": "d33a0abdf138c713c38f9333abafea255e5a0a50ed0390a0ab43f95b86f8ae85",
    },
    "diseases": {
        "repo": "alvaroalon2/biobert_diseases_ner",
        "commit": "0a4ed7dd4fd3e6db7229e5b801b70eefcb253759",
        "sha256": "87fe36f411970978003b90ead891057c31b0adcb32e5338dda79d745aa57965c",
    },
}
SMALL_FILES = ("config.json", "vocab.txt", "tokenizer_config.json", "special_tokens_map.json")


def url(repo: str, commit: str, name: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/{commit}/{name}"


def download(source: str, target: Path) -> None:
    partial = target.with_suffix(target.suffix + ".part")
    request = urllib.request.Request(source, headers={"User-Agent": "homelander"})
    with urllib.request.urlopen(request, timeout=600) as response, open(partial, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    partial.replace(target)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(name: str, spec: dict) -> dict:
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    weights = folder / "model.safetensors"
    print(f"{name}: {spec['repo']} @ {spec['commit'][:12]}")

    for small in SMALL_FILES:
        if not (folder / small).exists():
            download(url(spec["repo"], spec["commit"], small), folder / small)

    if not weights.exists():
        pickle = folder / "pytorch_model.bin"
        if not pickle.exists():
            print("  downloading weights (431 MB) ...")
            download(url(spec["repo"], spec["commit"], "pytorch_model.bin"), pickle)
        got = sha256(pickle)
        if got != spec["sha256"]:
            pickle.unlink()
            raise RuntimeError(f"weights hash mismatch: expected {spec['sha256']}, got {got}")

        import torch
        from safetensors.torch import save_file

        # weights_only: tensors and nothing else, even though the hash matched.
        state = torch.load(pickle, map_location="cpu", weights_only=True)
        save_file({k: v.contiguous() for k, v in state.items()}, str(weights))
        pickle.unlink()
        print(f"  converted to safetensors ({weights.stat().st_size / 1e6:.0f} MB)")

    return {"repo": spec["repo"], "commit": spec["commit"], "safetensors_sha256": sha256(weights)}


def main() -> int:
    pins = {}
    for name, spec in MODELS.items():
        try:
            pins[name] = fetch(name, spec)
        except Exception as exc:
            print(f"  FAILED: {type(exc).__name__}: {exc}")
            return 1
    (OUT / "pins.json").write_text(json.dumps(pins, indent=2) + "\n", encoding="utf-8")
    for name, pin in pins.items():
        print(f"  {name:9} safetensors sha256 {pin['safetensors_sha256']}")
    print("done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
