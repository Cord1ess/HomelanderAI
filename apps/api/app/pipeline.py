"""Evaluate one application: evidence in, score and tier out.

Deliberately knows nothing about the database, HTTP, or where files live. It
takes bytes and returns a result object, which makes the whole pipeline testable
without Postgres running.

Persistence is the caller's job. When the schema changes in docs/DATABASE.md
land, a thin layer writes `Evaluation` into `model_runs`, `sub_scores`,
`explanation_artifacts` and `composite_scores` — none of the logic here changes.
"""

from dataclasses import dataclass, field

from app.arms import ARMS, ArmResult
from app.intake import IntakeError, ProcessedFile, process_upload
from app.scoring import INSUFFICIENT, Adjustment, ScoreResult, Thresholds, score

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
) -> Evaluation:
    """Run the pipeline over uploaded evidence.

    `files` is a list of (raw bytes, filename). Never raises — every failure
    becomes an `insufficient_evidence` evaluation carrying the reason, because
    an underwriter with an error page is worse off than one with an honest
    "cannot assess".
    """
    t = thresholds or Thresholds()
    errors: list[str] = []
    processed: list[ProcessedFile] = []

    # 1. De-identify and normalise. Unreadable files are recorded and skipped
    #    rather than aborting the whole application.
    for raw, filename in files:
        try:
            processed.append(process_upload(raw, filename))
        except IntakeError as exc:
            errors.append(f"{filename or 'file'}: {exc}")

    if not processed:
        errors.append("No readable evidence was provided")
        return _insufficient(errors, t, processed)

    # 2. Run the vision arm over every image. Phase 1 has one arm; the loop is
    #    over the registry so adding an arm needs no change here.
    runs: list[ArmRun] = []
    for arm in ARMS.values():
        if not arm.available():
            errors.append(f"{arm.name}: unavailable")
            continue
        for item in processed:
            result = arm.run(item.data)
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

    usable = [r for r in runs if r.result.usable]
    if not usable:
        return _insufficient(errors, t, processed, runs)

    # 3. Highest score governs. A concerning finding on one film must not be
    #    averaged away by a clean one — screening escalates on the worst view.
    vision_score = max(r.result.score for r in usable)

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
