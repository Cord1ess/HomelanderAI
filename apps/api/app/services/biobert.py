"""BioBERT: the clinical-note reader's language model.

Two BioBERT v1.1 networks (Lee et al., *Bioinformatics* 2020 — BERT pretrained
on PubMed abstracts and PMC full text), each fine-tuned for biomedical named
entity recognition and published under Apache-2.0 by A. Alonso:

  drugs      `alvaroalon2/biobert_chemical_ner` — BC5CDR-chemicals + BC4CHEMD
  diseases   `alvaroalon2/biobert_diseases_ner` — BC5CDR-diseases + NCBI-disease

They read the note and mark every word that is part of a drug or a disease
name, from context rather than from a list: a misspelt "metfromin" or an
unlisted "empagliflozin" is found because of how it is written about, not
because it is in a table. What a drug is *for* is not something an NER model
knows, so the medication check still looks that up (`arms/medications.json`).

Each mention is then given an assertion — present, negated, family history,
hypothetical — by the clause rules below, so "no history of diabetes" and
"mother had breast cancer" do not count against the applicant.

How it reads:

- **Whole words.** BERT splits rare words into pieces ("metfromin" becomes
  `met ##f ##rom ##in`) and these models were trained on the label of each
  word's first piece, so a word takes that label and its whole span. Labelling
  pieces separately splits "atorvastatin" into "at" + "orvastatin".
- **Long notes in overlapping windows.** BERT reads at most 512 pieces at
  once. A discharge summary can be longer, so it is read in 512-piece windows
  that overlap by 128, and entities found twice are kept once.
- **Pinned and verified.** Each model is pinned to a commit
  (`biobert_models.json`) and its weights file is checked against a sha256
  every time it loads. The published files are PyTorch pickles; they are
  hash-checked before being opened and converted to safetensors, so nothing is
  unpickled at runtime.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings
from app.schemas.model import AssertionStatus, EntityResult, ModelResult, NLPRawOutput

logger = logging.getLogger(__name__)

PINS_PATH = Path(__file__).with_name("biobert_models.json")
PINS: dict[str, dict] = json.loads(PINS_PATH.read_text(encoding="utf-8"))["models"]
MODELS_DIR = settings.data_dir / "nlp" / "models"

# BERT's limit, and how far consecutive windows overlap so an entity on a
# window edge is seen whole in one of them.
_WINDOW = 512
_STRIDE = 128

# Non-clinical structural and grammatical tokens often picked up by generic biomedical models
NON_CLINICAL_STOP_ENTITIES: frozenset[str] = frozenset(
    {
        "patient",
        "pt",
        "pts",
        "mother",
        "father",
        "sister",
        "brother",
        "parent",
        "parents",
        "daughter",
        "son",
        "family",
        "family member",
        "family members",
        "doctor",
        "physician",
        "nurse",
        "history",
        "no history",
        "hx",
        "fhx",
        "examination",
        "physical examination",
        "assessment",
        "plan",
        "hospital",
        "clinic",
        "admission",
        "discharge",
        "consultation",
        "year old",
        "years old",
        "yo",
        "y/o",
        "male",
        "female",
        "man",
        "woman",
        "reports",
        "reported",
        "reporting",
        "diagnose",
        "diagnosed",
        "diagnosing",
        "diagnosis",
        "diagnoses",
        "treated",
        "treatment",
        "prescribed",
        "advised",
        "underwent",
        "evaluated",
        "evaluation",
        "noted",
        "noting",
        "denied",
        "denies",
        "denying",
        "presents",
        "presented",
        "presenting",
        "complains",
        "complained",
        "findings",
        "status",
        "negative",
        "positive",
        "normal",
        "abnormal",
        "rule out",
        "r/o",
        "return to",
        "ed",
        "er",
        "emergency department",
        "today",
        "yesterday",
        "tomorrow",
        "day",
        "days",
        "month",
        "months",
        "year",
        "years",
        "week",
        "weeks",
        "follow up",
        "follow-up",
        "note",
        "notes",
        # The disease model sometimes tags the word that introduces an allergy;
        # the allergy is the drug, read by the drug model.
        "allergic",
        "allergy",
        "allergies",
    }
)

# Prefix modifiers that NER models sometimes clump into the entity span
PREFIX_TRIGGERS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"^(?:rule\s+out|r/o|rules\s+out|ruled\s+out)\s+", re.IGNORECASE),
        AssertionStatus.HYPOTHETICAL,
    ),
    (
        re.compile(r"^(?:suspected|possible|probable|potential)\s+", re.IGNORECASE),
        AssertionStatus.HYPOTHETICAL,
    ),
    (
        re.compile(
            r"^(?:no\s+history\s+of|no\s+evidence\s+of|no\s+signs\s+of|negative\s+for|no|without|denies)\s+",
            re.IGNORECASE,
        ),
        AssertionStatus.NEGATED,
    ),
    (
        re.compile(
            r"^(?:family\s+history\s+of|fhx\s+of|fh\s+of|maternal\s+|paternal\s+)\s*",
            re.IGNORECASE,
        ),
        AssertionStatus.FAMILY_HISTORY,
    ),
]

# Patterns for assertion classification
FAMILY_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:family\s+history(?:\s+of)?|fhx(?:\s+of)?|fh(?:\s+of)?|family\s+hx(?:\s+of)?|"
        r"mother|maternal|father|paternal|sister|brother|parent|parents|grandmother|grandfather|"
        r"aunt|uncle|sibling|daughter|son|family\s+members?)\b",
        re.IGNORECASE,
    ),
]

NEGATED_FAMILY_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:no\s+family\s+history|negative\s+family\s+history|denies\s+family\s+history|"
        r"without\s+family\s+history|no\s+fhx|negative\s+fhx)\b",
        re.IGNORECASE,
    )
]

HYPOTHETICAL_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:rule\s+out|r/o|rules\s+out|evaluate\s+for|eval\s+for|suspected|possible|probable|"
        r"differential(?:\s+diagnosis)?|risk\s+of|concern\s+for|if(?:\s+patient|\s+symptoms|\s+pain|\s+fever)?|"
        r"should(?:\s+recur|\s+worsen|\s+develop)?|in\s+(?:the\s+)?event\s+of|as\s+needed\s+for|"
        r"return\s+(?:to\s+ed\s+)?if|potential|questionable|presumed|monitor\s+for)\b",
        re.IGNORECASE,
    ),
]

PRE_NEGATION_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:no|not|denies|denied|denying|negative\s+for|without|w/o|no\s+history\s+of|"
        r"no\s+evidence\s+of|no\s+signs\s+of|free\s+of|never\s+had|never\s+diagnosed\s+with|"
        r"absent|rules\s+out|ruled\s+out|unremarkable\s+for|resolved|has\s+no|shows\s+no)\b",
        re.IGNORECASE,
    ),
]

POST_NEGATION_TRIGGERS: list[re.Pattern] = [
    re.compile(
        r"\b(?:is\s+negative|was\s+negative|ruled\s+out|is\s+absent|was\s+absent|"
        r"unlikely|not\s+seen|unremarkable)\b",
        re.IGNORECASE,
    ),
]

# Conjunctions and punctuation that terminate modifier scope within a sentence
CLAUSE_DELIMITERS = re.compile(
    r"(?:[,;]\s+(?:but|however|although|yet|though|except|nevertheless)\s+|[;\n]+)",
    re.IGNORECASE,
)

class AssertionDetector:
    """Classifies entity assertions into PRESENT, NEGATED, FAMILY_HISTORY, or HYPOTHETICAL."""

    @staticmethod
    def split_into_clauses(text: str) -> list[tuple[int, int, str]]:
        """Split text into clause segments while tracking their character offsets."""
        clauses = []
        last_idx = 0
        for match in CLAUSE_DELIMITERS.finditer(text):
            start = match.start()
            end = match.end()
            if start > last_idx:
                clauses.append((last_idx, start, text[last_idx:start]))
            last_idx = end
        if last_idx < len(text):
            clauses.append((last_idx, len(text), text[last_idx:]))
        return clauses or [(0, len(text), text)]

    @classmethod
    def get_enclosing_clause(
        cls, sent_text: str, ent_start_in_sent: int, ent_end_in_sent: int
    ) -> tuple[str, str]:
        """Find the clause enclosing the entity span and extract pre/post text."""
        clauses = cls.split_into_clauses(sent_text)
        for c_start, c_end, clause_str in clauses:
            if c_start <= ent_start_in_sent and ent_end_in_sent <= c_end:
                pre = clause_str[: ent_start_in_sent - c_start]
                post = clause_str[ent_end_in_sent - c_start :]
                return pre, post

        # Fallback to entire sentence if boundaries don't cleanly align
        pre = sent_text[:ent_start_in_sent]
        post = sent_text[ent_end_in_sent:]
        return pre, post

    @classmethod
    def determine_assertion(
        cls,
        ent_text: str,
        sent_text: str,
        ent_start_in_sent: int,
        ent_end_in_sent: int,
        negex_flag: bool = False,
    ) -> str:
        """Determine assertion status based on ConText and negspaCy trigger patterns."""
        pre_text, post_text = cls.get_enclosing_clause(
            sent_text, ent_start_in_sent, ent_end_in_sent
        )

        # 1. Negated family history (e.g. "no family history of cancer")
        for pat in NEGATED_FAMILY_TRIGGERS:
            if pat.search(pre_text):
                return AssertionStatus.NEGATED

        # 2. Hypothetical / Uncertainty (e.g. "rule out", "evaluate for", "if", "suspected")
        for pat in HYPOTHETICAL_TRIGGERS:
            if pat.search(pre_text) or pat.search(post_text):
                return AssertionStatus.HYPOTHETICAL

        # 3. Family history (e.g. "mother had", "family history of", "paternal")
        for pat in FAMILY_TRIGGERS:
            if pat.search(pre_text) or pat.search(post_text):
                return AssertionStatus.FAMILY_HISTORY

        # 4. Negation: check pre-negation in clause, post-negation, or negex flag
        for pat in PRE_NEGATION_TRIGGERS:
            if pat.search(pre_text):
                return AssertionStatus.NEGATED

        for pat in POST_NEGATION_TRIGGERS:
            if pat.search(post_text):
                return AssertionStatus.NEGATED

        if negex_flag:
            return AssertionStatus.NEGATED

        # 5. Confirmed present finding
        return AssertionStatus.PRESENT


@dataclass
class Reader:
    """One loaded BioBERT NER network."""

    name: str
    entity: str
    tokenizer: Any
    model: Any


@dataclass(frozen=True)
class Span:
    """A drug or disease BioBERT found, as character offsets into the text."""

    text: str
    start: int
    end: int
    confidence: float


class ModelUnavailable(RuntimeError):
    """The weights are missing and could not be fetched, or do not match."""


_READERS: dict[str, Reader] = {}
_LOCK = threading.Lock()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def weights_path(name: str) -> Path:
    return MODELS_DIR / name / "model.safetensors"


def is_downloaded(name: str) -> bool:
    return weights_path(name).exists()


def ensure_downloaded(name: str) -> Path:
    """The model's folder, fetching and converting it first if it is missing.

    The pickle is hash-checked before it is opened, and opened with
    `weights_only=True` even then; what is kept is the safetensors copy.
    """
    spec = PINS[name]
    folder = MODELS_DIR / name
    weights = weights_path(name)
    if weights.exists():
        return folder

    folder.mkdir(parents=True, exist_ok=True)
    base = f"https://huggingface.co/{spec['repo']}/resolve/{spec['commit']}/"

    def get(file: str, target: Path) -> None:
        partial = target.with_suffix(target.suffix + ".part")
        request = urllib.request.Request(base + file, headers={"User-Agent": "homelander"})
        with urllib.request.urlopen(request, timeout=600) as response, open(partial, "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        partial.replace(target)

    logger.info("Fetching BioBERT %s from %s (431 MB, once)", name, spec["repo"])
    for small in ("config.json", "vocab.txt", "tokenizer_config.json", "special_tokens_map.json"):
        if not (folder / small).exists():
            get(small, folder / small)
    pickle = folder / "pytorch_model.bin"
    if not pickle.exists():
        get("pytorch_model.bin", pickle)
    if _sha256(pickle) != spec["pickle_sha256"]:
        pickle.unlink()
        raise ModelUnavailable(f"BioBERT {name}: downloaded weights do not match the pinned hash")

    import torch
    from safetensors.torch import save_file

    state = torch.load(pickle, map_location="cpu", weights_only=True)
    save_file({k: v.contiguous() for k, v in state.items()}, str(weights))
    pickle.unlink()
    return folder


def load_reader(name: str) -> Reader:
    """The named network, loaded once per process and verified every load."""
    with _LOCK:
        if name in _READERS:
            return _READERS[name]
        try:
            folder = ensure_downloaded(name)
        except ModelUnavailable:
            raise
        except Exception as exc:
            raise ModelUnavailable(f"BioBERT {name} could not be fetched: {exc}") from exc

        spec = PINS[name]
        if _sha256(weights_path(name)) != spec["safetensors_sha256"]:
            raise ModelUnavailable(
                f"BioBERT {name}: {weights_path(name)} does not match the pinned hash; "
                "delete it to re-download"
            )

        from transformers import AutoModelForTokenClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(folder)
        model = AutoModelForTokenClassification.from_pretrained(folder).eval()
        reader = Reader(name=name, entity=spec["entity"], tokenizer=tokenizer, model=model)
        _READERS[name] = reader
        return reader


def find(name: str, text: str) -> list[Span]:
    """Every drug (`drugs`) or disease (`diseases`) BioBERT finds in the text."""
    if not text or not text.strip():
        return []
    import torch

    reader = load_reader(name)
    tokenizer = reader.tokenizer
    full = tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)
    ids, all_offsets, all_words = full["input_ids"], full["offset_mapping"], full.word_ids()

    # Windows of content pieces, each wrapped in [CLS] ... [SEP] below. The
    # tokenizer's own overflow handling stops early on long input, so the cut
    # is made here, from one encoding of the whole note.
    content = _WINDOW - 2
    starts = list(range(0, max(len(ids) - _STRIDE, 1), content - _STRIDE)) or [0]
    windows = [(a, min(a + content, len(ids))) for a in starts]

    batch_ids, offsets, word_ids = [], [], []
    for a, b in windows:
        batch_ids.append([tokenizer.cls_token_id, *ids[a:b], tokenizer.sep_token_id])
        offsets.append([(0, 0), *all_offsets[a:b], (0, 0)])
        word_ids.append([None, *all_words[a:b], None])
    width = max(len(row) for row in batch_ids)
    mask = [[1] * len(row) + [0] * (width - len(row)) for row in batch_ids]
    batch_ids = [row + [tokenizer.pad_token_id] * (width - len(row)) for row in batch_ids]

    with torch.no_grad():
        probs = reader.model(
            input_ids=torch.tensor(batch_ids), attention_mask=torch.tensor(mask)
        ).logits.softmax(-1)
    labels = probs.argmax(-1).tolist()
    confidence = probs.max(-1).values.tolist()
    id2label = reader.model.config.id2label
    begin, inside = f"B-{reader.entity}", f"I-{reader.entity}"

    found: dict[tuple[int, int], Span] = {}
    for window in range(len(offsets)):
        # One entry per word: the first piece's label, the whole word's span.
        words: dict[int, list] = {}
        for pos, word in enumerate(word_ids[window]):
            if word is None:
                continue
            a, b = offsets[window][pos]
            if word not in words:
                words[word] = [a, b, id2label[labels[window][pos]], confidence[window][pos]]
            else:
                words[word][1] = b

        current: list | None = None
        for word in sorted(words):
            a, b, label, p = words[word]
            if label == begin or (label == inside and current is None):
                if current:
                    _keep(found, text, current)
                current = [a, b, p]
            elif label == inside:
                current[1] = b
                current[2] = min(current[2], p)
            else:
                if current:
                    _keep(found, text, current)
                current = None
        if current:
            _keep(found, text, current)

    # An entity seen whole in one window and cut at the edge of another: keep
    # the longest of any that overlap.
    spans = sorted(found.values(), key=lambda s: (s.start, -(s.end - s.start)))
    kept: list[Span] = []
    for span in spans:
        if kept and span.start < kept[-1].end:
            continue
        kept.append(span)
    return kept


def _keep(found: dict, text: str, run: list) -> None:
    start, end, p = run
    # The disease model sometimes takes the cue in front of a name into the
    # name itself: "Denies tuberculosis" as one entity. Left there, the cue
    # sits inside the span, the assertion check never sees it, and a denied
    # condition reads as present. Move it back out, in front of the span.
    moved = True
    while moved:
        moved = False
        for pattern, _ in PREFIX_TRIGGERS:
            # On the slice: `^` does not anchor at a `pos` offset.
            match = pattern.match(text[start:end])
            if match and match.end() < end - start:
                start, moved = start + match.end(), True
    found[(start, end)] = Span(text=text[start:end], start=start, end=end, confidence=round(p, 3))


class BioBERTClinicalNLPService:
    """Clinical entities in a note, with their assertion status.

    BioBERT finds the drug and disease names; `AssertionDetector` decides
    whether each is present, negated, family history or hypothetical.
    """

    MODEL_ID = "biobert"
    LABELS = {"drugs": "CHEMICAL", "diseases": "DISEASE"}

    def extract_entities(self, text: str) -> list[EntityResult]:
        if not text or not text.strip():
            return []
        results: list[EntityResult] = []
        for name, label in self.LABELS.items():
            for span in find(name, text):
                cleaned = span.text.lower().strip(" ,.;:-_()[]{}")
                if not cleaned or cleaned in NON_CLINICAL_STOP_ENTITIES or len(cleaned) < 2:
                    continue
                s_start, s_end = _sentence_around(text, span.start, span.end)
                sentence = text[s_start:s_end]
                results.append(
                    EntityResult(
                        text=span.text,
                        label=label,
                        assertion=AssertionDetector.determine_assertion(
                            ent_text=span.text,
                            sent_text=sentence,
                            ent_start_in_sent=span.start - s_start,
                            ent_end_in_sent=span.end - s_start,
                        ),
                        start_char=span.start,
                        end_char=span.end,
                    )
                )
        return sorted(results, key=lambda e: e.start_char)

    def predict(self, input_data: str | dict[str, Any]) -> ModelResult:
        text = (
            str(input_data.get("text", ""))
            if isinstance(input_data, dict)
            else str(input_data)
        )
        try:
            entities = self.extract_entities(text)
            return ModelResult(
                model_id=self.MODEL_ID,
                status="success",
                raw_output=NLPRawOutput(entities=entities).model_dump(),
            )
        except Exception as exc:
            logger.exception("BioBERT clinical NLP failed: %s", exc)
            return ModelResult(
                model_id=self.MODEL_ID,
                status="error",
                raw_output={"error": str(exc), "entities": []},
            )


# A sentence ends at . ! ? ; or a line break — clinical notes are terse.
_SENTENCE_END = re.compile(r"[.!?;]\s+|\n+")


def _sentence_around(text: str, start: int, end: int) -> tuple[int, int]:
    """(start, end) of the sentence containing a span."""
    s_start = 0
    for match in _SENTENCE_END.finditer(text, 0, start):
        s_start = match.end()
    following = _SENTENCE_END.search(text, end)
    return s_start, following.start() + 1 if following else len(text)
