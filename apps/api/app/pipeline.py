"""Evaluate one application: evidence in, score and tier out.

Deliberately knows nothing about the database, HTTP, or where files live. It
takes bytes and returns a result object, which makes the whole pipeline testable
without Postgres running.

Persistence is the caller's job. When the schema changes in docs/DATABASE.md
land, a thin layer writes `Evaluation` into `model_runs`, `sub_scores`,
`explanation_artifacts` and `composite_scores` — none of the logic here changes.
"""

from dataclasses import dataclass, field

from app.arms import ArmResult, arms_for, form_arms, set_arms
from app.evidence import EvidenceKind, label
from app.intake import IntakeError, ProcessedFile, process_upload
from app.scoring import INSUFFICIENT, Adjustment, ScoreResult, Thresholds, fuse, score

# Mirrors application_status in the schema.
STATUS_SCORED = "scored"
STATUS_INSUFFICIENT = "insufficient_evidence"


@dataclass
class ArmRun:
    """One arm's execution against one piece of evidence."""

    arm_name: str
    arm_version: str
    evidence_hash: str
    result: ArmResult

    @property
    def failed(self) -> bool:
        return not self.result.usable


@dataclass
class Evaluation:
    status: str
    crs: float | None
    tier: str
    runs: list[ArmRun] = field(default_factory=list)
    adjustments: list[Adjustment] = field(default_factory=list)
    thresholds: Thresholds = field(default_factory=Thresholds)
    processed_files: list[ProcessedFile] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def artifacts(self) -> dict[str, bytes]:
        """Every explanation artifact produced, keyed `<arm>.<name>`."""
        return {
            f"{run.arm_name}.{name}": data
            for run in self.runs
            for name, data in run.result.artifacts.items()
        }


def evaluate(
    files: list[tuple[bytes, str]],
    declared_history: dict | None = None,
    age: int | None = None,
    thresholds: Thresholds | None = None,
    kinds: dict[str, EvidenceKind] | None = None,
    sex: str | None = None,
    models_requested: list[str] | None = None,
) -> Evaluation:
    """Run the pipeline over uploaded evidence.

    `files` is a list of (raw bytes, filename).

    `kinds` maps a processed file's content hash to what the evidence is, as
    confirmed by the operator on the intake review screen. Files missing from
    it are stored but not scored: an unclassified file handed to an arbitrary
    model is how a retina model comes to report 98.8 on a chest X-ray.

    `models_requested` is the list of intake-form panels the operator chose.
    Arms that read the form rather than a file run only when their panel is
    among them, so an application with a chest X-ray alone is not told that
    nine blood values are missing.

    Never raises. Every failure becomes an `insufficient_evidence` evaluation
    carrying the reason, because an underwriter with an error page is worse off
    than one with an honest "cannot assess".
    """
    t = thresholds or Thresholds()
    errors: list[str] = []
    processed: list[ProcessedFile] = []
    requested = set(models_requested or [])
    form_readers = [a for a in form_arms() if a.intake_id in requested]

    # 1. De-identify and normalise. Unreadable files are recorded and skipped
    #    rather than aborting the whole application.
    for raw, filename in files:
        try:
            processed.append(process_upload(raw, filename))
        except IntakeError as exc:
            errors.append(f"{filename or 'file'}: {exc}")

    if not processed and not form_readers:
        errors.append("No readable evidence was provided")
        return _insufficient(errors, t, processed)

    # 2. Run each arm over the evidence it can actually read.
    #
    # This used to be every arm over every file, which is the same thing as
    # asking an eye specialist to read a chest X-ray. They do not decline: the
    # retina model returns 98.8 out of 100 on a lung, with no error, because it
    # has never seen one and has no way to say so. Since the highest score
    # governs, that fabricated number won on every application containing a
    # chest film.
    #
    # `kinds` is what the operator confirmed on the review screen. When it is
    # absent — an older caller, or a file whose kind was never established —
    # the arm is skipped rather than guessed at, and the reason is recorded.
    runs: list[ArmRun] = []
    for item in processed:
        kind = kinds.get(item.content_hash) if kinds else None

        if kind is None:
            errors.append("Evidence was not classified, so no model was run on it")
            continue

        readers = arms_for(kind)
        if not readers:
            # Ordinary for a lab report or a note: stored, shown to the
            # underwriter, and read by a person until a model exists for it.
            errors.append(f"{label(kind)}: no model reads this kind of evidence yet")
            continue

        for arm in readers:
            if arm.run_set is not None:
                continue  # below, once over every file of its kind
            if not arm.available():
                errors.append(f"{arm.name}: unavailable")
                continue
            result = arm.read(item.data, declared_history or {})
            runs.append(
                ArmRun(
                    arm_name=arm.name,
                    arm_version=arm.version,
                    evidence_hash=item.content_hash,
                    result=result,
                )
            )
            if result.error:
                errors.append(f"{arm.name}: {result.error}")

    # The arms that read all the files of a kind together: Mirai wants the four
    # views of one mammogram, not four separate readings of one view each.
    for arm in set_arms():
        members = [
            item for item in processed if kinds and kinds.get(item.content_hash) in arm.accepts
        ]
        if not members:
            continue
        if not arm.available():
            errors.append(f"{arm.name}: unavailable")
            continue
        result = arm.run_set([item.data for item in members])
        runs.append(
            ArmRun(
                arm_name=arm.name,
                arm_version=arm.version,
                evidence_hash=members[0].content_hash,
                result=result,
            )
        )
        if result.error:
            errors.append(f"{arm.name}: {result.error}")

    # The arms that read the form. Their "evidence" is what the operator typed,
    # so the input signature recorded against the run is a hash of that.
    for arm in form_readers:
        if not arm.available():
            errors.append(f"{arm.name}: unavailable")
            continue
        result = arm.run_form(declared_history or {}, age, sex)
        runs.append(
            ArmRun(
                arm_name=arm.name,
                arm_version=arm.version,
                evidence_hash=str(result.details.get("input_hash", "")),
                result=result,
            )
        )
        if result.error:
            errors.append(f"{arm.name}: {result.error}")

    usable = [r for r in runs if r.result.usable]
    if not usable:
        return _insufficient(errors, t, processed, runs)

    # 3. Every usable reading counts, with diminishing returns (scoring.fuse).
    #    A concerning reading is never averaged away by a clean one, and a
    #    second concerning reading adds to the first rather than being ignored,
    #    but no number of positives turns into a certainty on its own.
    vision_score = fuse([r.result.score for r in usable])

    scored: ScoreResult = score(vision_score, declared_history, age=age, thresholds=t)

    return Evaluation(
        status=STATUS_SCORED,
        crs=scored.crs,
        tier=scored.tier,
        runs=runs,
        adjustments=scored.adjustments,
        thresholds=t,
        processed_files=processed,
        errors=errors,
    )


def _insufficient(
    errors: list[str],
    thresholds: Thresholds,
    processed: list[ProcessedFile],
    runs: list[ArmRun] | None = None,
) -> Evaluation:
    return Evaluation(
        status=STATUS_INSUFFICIENT,
        crs=None,
        tier=INSUFFICIENT,
        runs=runs or [],
        thresholds=thresholds,
        processed_files=processed,
        errors=errors,
    )
