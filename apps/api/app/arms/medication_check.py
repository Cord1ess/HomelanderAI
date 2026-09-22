"""Medication check: what a note's prescriptions imply that the form did not declare.

An applicant who leaves diabetes off the form and attaches a discharge summary
that lists metformin has, in effect, disclosed it. Underwriters read
prescriptions for exactly this, and it is the one thing a clinical note says
reliably: drug names are spelt the same way everywhere, where diagnoses are
paraphrased, abbreviated or left out.

This arm reads a note, report or prescription as text, finds the medications
in it, looks up what each is prescribed for, and compares that with what the
applicant declared on the intake form. Each condition implied by a medication
and declared nowhere is reported as a question to ask, and the most serious of
them sets the arm's score.

What it is, and is not:

- **A dictionary, not a model.** `medications.json` lists generics, the brand
  names an applicant in Bangladesh is likely to write, and the conditions each
  is prescribed for, with a weight per condition. A drug that is not in the
  table is not seen. A misspelt one is not seen. Nothing is inferred beyond
  the table, so every flag can be traced to a row in it.
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

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.arms import ArmResult
from app.services.biobert import AssertionDetector

NAME = "medication_check"
VERSION = "1.0.0"

TABLE_PATH = Path(__file__).with_name("medications.json")
_TABLE: dict = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
CONDITIONS: dict[str, dict] = _TABLE["conditions"]
MEDICATIONS: list[dict] = _TABLE["medications"]

PREPROCESSING_VERSION = "utf8-text"
WEIGHT_HASH = f"table:sha256:{hashlib.sha256(TABLE_PATH.read_bytes()).hexdigest()[:16]}"
VALIDATION = (
    f"a curated table of {len(MEDICATIONS)} medications and {len(CONDITIONS)} conditions "
    "(BNF indications, MED-RT may_treat, DGDA-registered brands); exact-name matching, so an "
    "unlisted or misspelt drug is missed and nothing is inferred beyond the table. "
    "A disclosure check, not a diagnosis"
)

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


def find_mentions(text: str) -> list[Mention]:
    """Every medication named in the text, once per occurrence, with how it
    was asserted. Overlapping matches keep the longer name."""
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


def check(text: str, declared: dict) -> dict:
    """The arm's reading of one note against one form, as the details it stores."""
    mentions = find_mentions(text)
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
            }
        )

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

    flags = sorted(undisclosed.values(), key=lambda f: -f["points"])
    if flags:
        score = flags[0]["points"]
    elif explained:
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

    report = check(text, declared or {})
    if not report["medications"] and not report["excluded"]:
        # Nothing to compare: an honest "could not check" rather than a low
        # score that would read as reassurance.
        return ArmResult(
            score=None,
            error="no medication in the table was named in the note; nothing to check",
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
