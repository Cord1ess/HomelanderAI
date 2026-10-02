"""Medication check: what a clinical note says that the form did not declare.

An applicant who leaves diabetes off the form and attaches a discharge summary
that lists metformin has, in effect, disclosed it. Underwriters read
prescriptions for exactly this, and it is the one thing a clinical note says
reliably: drug names are spelt the same way everywhere, where diagnoses are
paraphrased, abbreviated or left out.

This arm reads a note, report or prescription as text and compares what it
says with what the applicant declared on the intake form, in two ways:

- **Medications.** BioBERT (`app.services.biobert`) finds the drug names in
  the note from context, so a misspelt "metfromin" or an unlisted
  "empagliflozin" is still found. `medications.json` then says what each is
  prescribed for — something a language model does not know — and the table's
  own name list runs beside BioBERT, because BioBERT learned from PubMed and
  misses brand names like Glucophage. Every medication records which of the two
  found it.
- **Stated conditions.** BioBERT also finds disease names. One that is present
  — "known case of hypertension", not "no history of hypertension" — and
  matches a condition the form did not declare is flagged at full weight: a
  diagnosis written in the note is stronger evidence than one inferred from a
  prescription.

Each condition implied or stated and declared nowhere is reported as a question
to ask, and the most serious of them sets the arm's score.

What it is, and is not:

- **BioBERT finds; the table decides.** A drug BioBERT finds that is not in the
  table is shown to the underwriter and adds nothing to the score, because
  nothing says what it is for. A misspelling is matched to the table only when
  BioBERT has already called the word a drug, so an ordinary word can never be
  stretched into one. Every flag traces to a row in the table.
- **Assertion-aware.** "Allergic to metformin", "mother takes metformin" and
  "consider metformin if HbA1c rises" do not count; the same clause rules the
  chest arm's clinical-note service uses decide that. "Stopped metformin last
  year" does count: a condition that needed treatment is still a condition.
- **Ambiguity is priced in.** Aspirin may be prevention or a stent; bisoprolol
  may be blood pressure or a heart attack. A medication with several
  indications is marked ambiguous and its points are halved, and any one of
  its conditions being declared explains it.
- **Not de-identified.** The note names its patient; it is shown only to the
  underwriter holding the case, and the arm stores sentences, not the note.

The score is a prompt for a question, not a probability of disease. A note
whose medications are all declared or all immaterial scores in the low tier;
one that implies an undeclared tuberculosis course does not.
"""

import difflib
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.arms import ArmResult
from app.services import biobert
from app.services.biobert import AssertionDetector, Span

NAME = "medication_check"
VERSION = "2.0.0-biobert"

TABLE_PATH = Path(__file__).with_name("medications.json")
_TABLE: dict = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
CONDITIONS: dict[str, dict] = _TABLE["conditions"]
MEDICATIONS: list[dict] = _TABLE["medications"]

PREPROCESSING_VERSION = "utf8-text"
WEIGHT_HASH = (
    f"table:sha256:{hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest()[:16]};"
    f"biobert:{biobert.PINS['drugs']['safetensors_sha256'][:12]}"
    f"+{biobert.PINS['diseases']['safetensors_sha256'][:12]}"
)
# From scripts/biobert_eval.py on the BC5CDR test split. The disease figure
# reproduces the model author's own (0.858), which is how we know the split was
# held out and that this code reads the model the way it was trained.
VALIDATION = (
    "BioBERT v1.1 named-entity recognition (Lee 2020; drug and disease models by Alonso, "
    "Apache-2.0), measured by us on the BC5CDR test set (5,865 sentences): drugs F1 0.905 "
    "(precision 0.939, recall 0.874), diseases F1 0.859 (author's own 0.858). What each drug "
    f"is prescribed for comes from a curated table of {len(MEDICATIONS)} medications and "
    f"{len(CONDITIONS)} conditions (BNF, MED-RT, DGDA brands). Measured on PubMed abstracts, "
    "NOT on Bangladeshi clinical notes. A disclosure check, not a diagnosis"
)

# A misspelling is accepted as a listed drug at this similarity or above, and
# only for a word BioBERT has called a drug. 0.85 takes "metfromin" (0.89) and
# "atorvastatn" (0.96) and refuses "metoprolol" for "metformin" (0.63).
_SPELLING = 0.85

# A medication found but declared nowhere and prescribed for nothing material
# still shows the note was read; it sits at the bottom of the low tier.
_NOTHING_MATERIAL = 5.0
_ALL_EXPLAINED = 10.0
_AMBIGUOUS_FACTOR = 0.5

# What stops a mention from counting for the applicant. The clinical-note
# service's negation, family and hypothetical triggers do most of the work;
# these are the medication-specific ones it does not know.
_ALLERGY = re.compile(
    r"\b(?:allerg(?:y|ic|ies)\s+to|intoleran(?:t|ce)\s+(?:to|of)|reaction\s+to)\b", re.I
)
_PAST = re.compile(
    r"\b(?:stopped|discontinued|ceased|came\s+off|no\s+longer\s+(?:on|taking|takes)|"
    r"previously\s+(?:on|took|taking)|was\s+on|used\s+to\s+take|completed)\b",
    re.I,
)

# Sentence ends. Clinical notes are terse: a line break is a boundary too.
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\n+")

# Short all-capitals names (INH, PTU, GTN) are matched only as written; in
# lower case they are ordinary words.
_CASE_SENSITIVE = re.compile(r"^[A-Z0-9/-]{2,5}$")

# The word after a drug name that makes it a measurement or a mechanism, not
# a prescription: "insulin resistance", "lithium level".
_NOT_A_PRESCRIPTION = re.compile(
    r"^\s*(?:resistance|level|levels|sensitivity|antibod|receptor)", re.I
)

# "As needed" is how an inhaler is prescribed, not a hypothetical. Blanked to
# spaces before the assertion rules see it, so offsets stay put.
_PRN = re.compile(r"\b(?:as\s+needed(?:\s+for)?|when\s+required|prn|sos)\b", re.I)


@dataclass
class Mention:
    term: str
    generic: str
    start: int
    end: int
    sentence: str
    assertion: str  # PRESENT, PAST, NEGATED, FAMILY_HISTORY, HYPOTHETICAL
    # Which reader found it: "biobert", "table", or both. A misspelling BioBERT
    # found and the table matched by similarity is "biobert" with `spelling`.
    found_by: set[str] = field(default_factory=set)
    spelling: bool = False


@dataclass
class Stated:
    """A disease BioBERT found written in the note."""

    term: str
    conditions: list[str]
    sentence: str
    assertion: str


def available() -> bool:
    return True


# ── the table, compiled ──────────────────────────────────────────────────────


def _compile() -> tuple[re.Pattern, re.Pattern, dict[str, dict]]:
    """Two alternations — case-insensitive names and the short capitalised
    ones — longest first, so 'insulin glargine' wins over 'insulin'."""
    by_generic = {row["generic"]: row for row in MEDICATIONS}
    loose: dict[str, str] = {}
    strict: dict[str, str] = {}
    for row in MEDICATIONS:
        for name in [row["generic"], *row.get("brands", [])]:
            (strict if _CASE_SENSITIVE.match(name) else loose)[name] = row["generic"]

    def pattern(names: dict[str, str], flags: int) -> re.Pattern:
        ordered = sorted(names, key=len, reverse=True)
        body = "|".join(re.escape(n) for n in ordered)
        return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", flags)

    loose_pattern = pattern(loose, re.IGNORECASE)
    strict_pattern = pattern(strict, 0)
    lookup = {name.lower(): generic for name, generic in loose.items()}
    lookup.update({name: generic for name, generic in strict.items()})
    return loose_pattern, strict_pattern, {**lookup, **{g: g for g in by_generic}}


_LOOSE, _STRICT, _GENERIC_OF = _compile()
_ROW: dict[str, dict] = {row["generic"]: row for row in MEDICATIONS}


def _generic_for(term: str) -> str:
    return _GENERIC_OF.get(term, _GENERIC_OF.get(term.lower(), term.lower()))


# Names long enough that a near-miss is a misspelling rather than another word.
_SPELLABLE = sorted(n for n in _GENERIC_OF if len(n) >= 6 and n == n.lower())


def table_name_for(term: str) -> tuple[str | None, bool]:
    """(generic, by_spelling) for a word BioBERT called a drug, or (None, False)."""
    if term in _GENERIC_OF or term.lower() in _GENERIC_OF:
        return _generic_for(term), False
    close = difflib.get_close_matches(term.lower(), _SPELLABLE, n=1, cutoff=_SPELLING)
    if close:
        return _GENERIC_OF[close[0]], True
    return None, False


# ── matching a BioBERT disease span to a condition ───────────────────────────


def _phrase(words: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(words)}(?![A-Za-z0-9])", re.IGNORECASE)


_CONDITION_WORDS = [
    (key, _phrase(w)) for key, spec in CONDITIONS.items() for w in spec.get("mentioned_as", [])
]
_CONDITION_ABBREVIATIONS = {
    a: key for key, spec in CONDITIONS.items() for a in spec.get("abbreviations", [])
}


def conditions_named(term: str) -> list[str]:
    """The table's conditions a disease mention names. "Diabetic nephropathy"
    names two; "cough" names none."""
    if term.strip() in _CONDITION_ABBREVIATIONS:
        return [_CONDITION_ABBREVIATIONS[term.strip()]]
    found: list[str] = []
    for key, pattern in _CONDITION_WORDS:
        if key not in found and pattern.search(term):
            found.append(key)
    return found


# ── reading the note ─────────────────────────────────────────────────────────


def sentences(text: str) -> list[tuple[int, int]]:
    """(start, end) of each sentence in the text."""
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        if match.start() > start:
            spans.append((start, match.start()))
        start = match.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _assertion(term: str, sentence: str, start: int, end: int) -> str:
    before = sentence[:start]
    if _ALLERGY.search(before):
        return "NEGATED"
    cleaned = _PRN.sub(lambda m: " " * len(m.group(0)), sentence)
    status = AssertionDetector.determine_assertion(term, cleaned, start, end)
    if status == "PRESENT" and _PAST.search(before):
        return "PAST"
    return status


def _sentence_of(spans: list[tuple[int, int]], start: int) -> tuple[int, int]:
    for s_start, s_end in spans:
        if s_start <= start < s_end:
            return s_start, s_end
    return 0, 0


def find_mentions(
    text: str, drug_spans: list[Span] | None = None
) -> tuple[list[Mention], list[dict]]:
    """Every medication in the text, once per occurrence, with how it was
    asserted and which reader found it — and the drugs BioBERT found that the
    table does not list."""
    found = _table_mentions(text)
    unlisted: list[dict] = []
    sentence_spans = sentences(text)
    for span in drug_spans or []:
        same = next((m for m in found if m.start < span.end and span.start < m.end), None)
        if same:
            same.found_by.add("biobert")
            continue
        s_start, s_end = _sentence_of(sentence_spans, span.start)
        sentence = text[s_start:s_end]
        if _NOT_A_PRESCRIPTION.match(text[span.end :]):
            continue
        assertion = _assertion(span.text, sentence, span.start - s_start, span.end - s_start)
        generic, by_spelling = table_name_for(span.text)
        if generic is None:
            unlisted.append(
                {
                    "as_written": span.text,
                    "assertion": assertion,
                    "sentence": sentence.strip()[:240],
                }
            )
            continue
        found.append(
            Mention(
                term=span.text,
                generic=generic,
                start=span.start,
                end=span.end,
                sentence=sentence.strip(),
                assertion=assertion,
                found_by={"biobert"},
                spelling=by_spelling,
            )
        )
    return sorted(found, key=lambda m: m.start), unlisted


def stated_conditions(text: str, disease_spans: list[Span]) -> tuple[list[Stated], list[dict]]:
    """Diseases BioBERT found written in the note: those that name a
    condition in the table, and everything else it found (symptoms, mostly),
    which is shown but never scored."""
    stated: list[Stated] = []
    other: list[dict] = []
    sentence_spans = sentences(text)
    for span in disease_spans:
        if span.text.lower().strip(" ,.;:-_()[]{}") in biobert.NON_CLINICAL_STOP_ENTITIES:
            continue
        s_start, s_end = _sentence_of(sentence_spans, span.start)
        sentence = text[s_start:s_end]
        assertion = _assertion(span.text, sentence, span.start - s_start, span.end - s_start)
        named = conditions_named(span.text)
        if named:
            stated.append(Stated(span.text, named, sentence.strip()[:240], assertion))
        else:
            other.append({"as_written": span.text, "assertion": assertion})
    return stated, other


def _table_mentions(text: str) -> list[Mention]:
    """The table's names, matched exactly. Overlapping matches keep the longer."""
    found: list[Mention] = []
    for s_start, s_end in sentences(text):
        sentence = text[s_start:s_end]
        taken: list[tuple[int, int]] = []
        matches = list(_LOOSE.finditer(sentence)) + list(_STRICT.finditer(sentence))
        for match in sorted(matches, key=lambda m: (m.start(), -(m.end() - m.start()))):
            if any(a < match.end() and match.start() < b for a, b in taken):
                continue
            if _NOT_A_PRESCRIPTION.match(sentence[match.end() :]):
                continue
            taken.append((match.start(), match.end()))
            term = match.group(0)
            found.append(
                Mention(
                    term=term,
                    generic=_generic_for(term),
                    start=s_start + match.start(),
                    end=s_start + match.end(),
                    sentence=sentence.strip(),
                    assertion=_assertion(term, sentence, match.start(), match.end()),
                    found_by={"table"},
                )
            )
    return found


# ── what the form said ───────────────────────────────────────────────────────


def _lookup(declared: dict, path: str):
    value = declared
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def declared_conditions(declared: dict) -> set[str]:
    """The conditions the intake form's answers amount to declaring."""
    out: set[str] = set()
    for key, spec in CONDITIONS.items():
        for rule in spec.get("declared_by", []):
            value = _lookup(declared, rule["key"])
            if "equals" in rule:
                hit = value == rule["equals"]
            elif "not" in rule:
                hit = value not in (None, "", False, rule["not"])
            else:
                hit = bool(value)
            if hit:
                out.add(key)
                break
    return out


def asked_on_form(condition: str) -> bool:
    return bool(CONDITIONS[condition].get("declared_by"))


# ── the check ────────────────────────────────────────────────────────────────


def check(
    text: str,
    declared: dict,
    drug_spans: list[Span] | None = None,
    disease_spans: list[Span] | None = None,
) -> dict:
    """The arm's reading of one note against one form, as the details it stores.

    `drug_spans` and `disease_spans` are what BioBERT found in the text; the
    caller runs the models, so this stays a pure function of its inputs.
    """
    mentions, unlisted = find_mentions(text, drug_spans)
    stated, other_findings = stated_conditions(text, disease_spans or [])
    declared_set = declared_conditions(declared)

    # One entry per generic that counts for the applicant.
    counted: dict[str, list[Mention]] = {}
    for mention in mentions:
        if mention.assertion in ("PRESENT", "PAST"):
            counted.setdefault(mention.generic, []).append(mention)

    medications: list[dict] = []
    undisclosed: dict[str, dict] = {}
    explained: list[str] = []
    immaterial: list[str] = []
    for generic, hits in counted.items():
        row = _ROW.get(generic, {"generic": generic, "conditions": []})
        conditions = list(row.get("conditions", []))
        ambiguous = bool(row.get("ambiguous"))
        known = [c for c in conditions if c in declared_set]
        missing = [c for c in conditions if c not in declared_set]
        if not conditions:
            status = "immaterial"
            immaterial.append(generic)
        elif known:
            status = "explained"
            explained.append(generic)
        else:
            status = "undisclosed"
            for condition in missing:
                spec = CONDITIONS[condition]
                points = spec["weight"] * (_AMBIGUOUS_FACTOR if ambiguous else 1.0)
                entry = undisclosed.setdefault(
                    condition,
                    {
                        "condition": condition,
                        "label": spec["label"],
                        "medications": [],
                        "points": 0.0,
                        "asked_on_form": asked_on_form(condition),
                    },
                )
                entry["medications"].append(generic)
                # Two unambiguous drugs for one condition do not add up; the
                # least ambiguous of them sets the points.
                entry["points"] = max(entry["points"], round(points, 1))
        medications.append(
            {
                "generic": generic,
                "atc": row.get("atc"),
                "as_written": sorted({h.term for h in hits}),
                "assertion": "PAST" if all(h.assertion == "PAST" for h in hits) else "PRESENT",
                "conditions": conditions,
                "condition_labels": [CONDITIONS[c]["label"] for c in conditions],
                "declared": known,
                "ambiguous": ambiguous,
                "status": status,
                "note": row.get("note"),
                "sentence": hits[0].sentence[:240],
                "found_by": sorted(set().union(*(h.found_by for h in hits))),
                "spelling": any(h.spelling for h in hits),
            }
        )

    # A condition written in the note, present, and declared nowhere. Full
    # weight: the note says it outright, where a medication only implies it.
    stated_present = [x for x in stated if x.assertion in ("PRESENT", "PAST")]
    for item in stated_present:
        for condition in item.conditions:
            if condition in declared_set:
                continue
            spec = CONDITIONS[condition]
            entry = undisclosed.setdefault(
                condition,
                {
                    "condition": condition,
                    "label": spec["label"],
                    "medications": [],
                    "points": 0.0,
                    "asked_on_form": asked_on_form(condition),
                },
            )
            entry.setdefault("stated", [])
            if item.term not in entry["stated"]:
                entry["stated"].append(item.term)
            entry["points"] = max(entry["points"], float(spec["weight"]))

    excluded = [
        {
            "generic": m.generic,
            "as_written": m.term,
            "assertion": m.assertion,
            "sentence": m.sentence[:240],
        }
        for m in mentions
        if m.assertion not in ("PRESENT", "PAST")
    ]
    conditions_in_note = [
        {
            "as_written": x.term,
            "conditions": x.conditions,
            "labels": [CONDITIONS[c]["label"] for c in x.conditions],
            "assertion": x.assertion,
            "declared": all(c in declared_set for c in x.conditions),
            "sentence": x.sentence,
        }
        for x in stated
    ]

    flags = sorted(undisclosed.values(), key=lambda f: -f["points"])
    if flags:
        score = flags[0]["points"]
    elif explained or stated_present:
        score = _ALL_EXPLAINED
    else:
        score = _NOTHING_MATERIAL

    order = {"undisclosed": 0, "explained": 1, "immaterial": 2}
    medications.sort(key=lambda m: (order[m["status"]], m["generic"]))
    return {
        "score": round(float(score), 2),
        "medications": medications,
        "undisclosed": flags,
        "explained": sorted(explained),
        "immaterial": sorted(immaterial),
        "excluded": excluded,
        "unlisted": unlisted,
        "conditions_in_note": conditions_in_note,
        "other_findings": other_findings,
        "declared_conditions": sorted(declared_set),
        "declared_labels": [CONDITIONS[c]["label"] for c in sorted(declared_set)],
        "characters": len(text),
        "sentences": len(sentences(text)),
    }


def run_with_form(raw: bytes, declared: dict) -> ArmResult:
    """Read one stored note against the applicant's declared history. Never raises."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ArmResult(score=None, error="the stored note is not UTF-8 text")
    if not text.strip():
        return ArmResult(score=None, error="the note is empty")

    # BioBERT reads the note. If it cannot, the check is refused rather than
    # run on the table alone under the same name: a reading that says BioBERT
    # must have had BioBERT in it.
    try:
        drug_spans = biobert.find("drugs", text)
        disease_spans = biobert.find("diseases", text)
    except biobert.ModelUnavailable as exc:
        return ArmResult(score=None, error=f"BioBERT could not be loaded: {exc}")

    report = check(text, declared or {}, drug_spans, disease_spans)
    report["biobert"] = {
        "drugs_found": len(drug_spans),
        "diseases_found": len(disease_spans),
        "models": {
            name: f"{spec['repo']}@{spec['commit'][:12]}" for name, spec in biobert.PINS.items()
        },
    }
    if not (report["medications"] or report["excluded"] or report["conditions_in_note"]
            or report["unlisted"]):
        # Nothing to compare: an honest "could not check" rather than a low
        # score that would read as reassurance.
        return ArmResult(
            score=None,
            error="BioBERT found no medication or condition in the note; nothing to check",
            details={**report, "scorer": f"{NAME} v{VERSION}", "validation": VALIDATION},
        )

    digest = hashlib.sha256(
        raw + json.dumps(declared or {}, sort_keys=True, default=str).encode()
    ).hexdigest()
    score = report.pop("score")
    return ArmResult(
        score=score,
        raw_score=score / 100.0,
        details={
            **report,
            "scorer": f"{NAME} v{VERSION}",
            "table_version": _TABLE["version"],
            "validation": VALIDATION,
            "input_hash": digest,
        },
    )
