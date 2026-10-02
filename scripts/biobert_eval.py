"""Measure the two BioBERT NER models on the BC5CDR test split.

    uv run --directory apps/api python ../../scripts/biobert_eval.py

BC5CDR (Li et al., Database 2016) is 1,500 PubMed abstracts annotated by hand
for chemicals and diseases; the test split is 500 of them, 5,865 sentences.
Both models were fine-tuned around it, so this is their own benchmark — the
honest framing is "how well does the model do the task it was trained for",
not "how well does it read a Bangladeshi discharge summary". No labelled set of
those exists.

The drug model's author published no figures at all; the disease model's
author published test F1 0.858. This measures both the same way, so the
platform quotes numbers it produced itself.

Scoring is strict entity-level, the convention in the BioNER literature: a
predicted entity counts only if its start, end and type all match a gold one.
Each word takes the label of its first sub-word piece — the same rule the
platform uses — so this measures what ships.

The test file is fetched once into data/nlp/bc5cdr/ (gitignored).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

DATA = ROOT / "data" / "nlp" / "bc5cdr"
SOURCE = "https://huggingface.co/datasets/tner/bc5cdr/resolve/main/dataset/"
# tner's tag ids, from its label.json.
GOLD = {0: "O", 1: "B-Chemical", 2: "B-Disease", 3: "I-Disease", 4: "I-Chemical"}


def fetch() -> list[dict]:
    DATA.mkdir(parents=True, exist_ok=True)
    test = DATA / "test.json"
    if not test.exists():
        urllib.request.urlretrieve(SOURCE + "test.json", test)
    return [json.loads(line) for line in test.read_text(encoding="utf-8").splitlines() if line]


def entities(tags: list[str], kind: str) -> set[tuple[int, int]]:
    """(first word, last word) of every entity of one kind, from BIO tags."""
    out, start = set(), None
    for i, tag in enumerate([*tags, "O"]):
        if tag == f"B-{kind}" or (tag == f"I-{kind}" and start is None):
            if start is not None:
                out.add((start, i - 1))
            start = i
        elif tag != f"I-{kind}":
            if start is not None:
                out.add((start, i - 1))
            start = None
    return out


def predict(reader, sentences: list[list[str]], batch: int = 32) -> list[list[str]]:
    """Word-level BIO for pre-tokenised sentences, first-piece rule."""
    import torch

    out: list[list[str]] = []
    for i in range(0, len(sentences), batch):
        chunk = sentences[i : i + batch]
        enc = reader.tokenizer(
            chunk, is_split_into_words=True, truncation=True, max_length=512,
            padding=True, return_tensors="pt",
        )
        with torch.no_grad():
            labels = reader.model(**enc).logits.argmax(-1).tolist()
        for row, words in enumerate(chunk):
            tags = ["O"] * len(words)
            seen = set()
            for pos, w in enumerate(enc.word_ids(row)):
                if w is None or w in seen:
                    continue
                seen.add(w)
                tags[w] = reader.model.config.id2label[labels[row][pos]]
            out.append(tags)
    return out


def score(gold: list[list[str]], pred: list[list[str]], gkind: str, pkind: str) -> dict:
    tp = fp = fn = 0
    for g, p in zip(gold, pred, strict=True):
        ge, pe = entities(g, gkind), entities(p, pkind)
        tp += len(ge & pe)
        fp += len(pe - ge)
        fn += len(ge - pe)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4),
        "gold_entities": tp + fn, "true_positives": tp,
    }


def main() -> int:
    from app.services.biobert import load_reader

    rows = fetch()
    sentences = [r["tokens"] for r in rows]
    gold = [[GOLD[t] for t in r["tags"]] for r in rows]
    print(f"BC5CDR test: {len(rows)} sentences\n")

    results = {}
    for name, gkind, pkind in (("drugs", "Chemical", "CHEMICAL"), ("diseases", "Disease", "DISEASE")):
        reader = load_reader(name)
        t0 = time.time()
        pred = predict(reader, sentences)
        results[name] = score(gold, pred, gkind, pkind)
        r = results[name]
        print(f"{name:9} P {r['precision']:.3f}  R {r['recall']:.3f}  F1 {r['f1']:.3f}  "
              f"({r['gold_entities']} gold entities, {time.time() - t0:.0f}s)")

    (DATA / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
