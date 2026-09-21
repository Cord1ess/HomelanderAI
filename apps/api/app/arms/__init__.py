"""Model arms.

An arm is a function that reads evidence and returns an `ArmResult`. The
registry is a dict. That is the whole extension mechanism — adding an arm is a
new module plus one entry in `ARMS`.

Deliberately not here: no base class, no factory, no plugin loader, no dynamic
discovery. A dataclass and a dict do everything those would, without the
indirection (docs/DESIGN_POLICY.md §2, §7).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app.evidence import EvidenceKind


@dataclass
class ArmResult:
    """What every arm returns.

    `score` is 0-100, or None when the arm could not produce a usable reading.
    None is not zero: a missing score means "cannot assess", which sends the
    application to `insufficient_evidence` rather than scoring it as low risk.
    """

    score: float | None
    raw_score: float | None = None
    details: dict = field(default_factory=dict)
    artifacts: dict[str, bytes] = field(default_factory=dict)
    error: str | None = None

    @property
    def usable(self) -> bool:
        return self.score is not None


@dataclass(frozen=True)
class Arm:
    name: str
    version: str
    arm_type: str  # matches the model_arm_type enum in the database
    # Which panel on the intake form feeds this arm. The form and the model use
    # different names on purpose — `cxr_lung` is the evidence the operator
    # attaches, `tb_xray` is the model that reads it, and one chest X-ray could
    # feed several models later. Keeping the link here means the two names can
    # never drift apart silently, which is exactly what happened when the router
    # matched a form id against this dict's keys and quietly found nothing.
    intake_id: str
    # The kinds of evidence this arm can actually read, as EvidenceKind values.
    #
    # An arm has no way to recognise a document it was never trained on: the
    # retina model handed a chest X-ray returns 98.8 out of 100, with no error,
    # because it has never seen a lung and cannot say so. The pipeline runs
    # every arm over every file, so without this the highest score on any
    # application was whichever model was most confidently wrong.
    #
    # This is the backstop. Even if routing sends the wrong file to the wrong
    # arm, the arm refuses rather than inventing a number.
    accepts: frozenset[str]
    # Everything the model_arms row needs, so the registry in code is the one
    # source of truth and a seed file cannot drift out of sync with it.
    preprocessing_version: str
    weight_hash: str
    # How the arm was tested, in one line. Every screen that shows a score also
    # shows this, so the caveat cannot be left behind in a document.
    validation: str
    run: Callable[[bytes], ArmResult]
    available: Callable[[], bool]


# Imported at the bottom on purpose: tb_xray and dr_fundus do `from app.arms
# import ArmResult`, and by this point ArmResult is defined, so there is no cycle.
from app.arms import dr_fundus, tb_xray  # noqa: E402


def arms_for(kind: EvidenceKind | str) -> list[Arm]:
    """Every arm that can read this kind of evidence.

    A list, not one arm: a chest X-ray could feed both a tuberculosis screen and
    a cardiovascular one later, and nothing about that should need a change
    here. Returns empty for kinds nothing reads yet, which is an ordinary
    answer rather than an error.
    """
    return [a for a in ARMS.values() if kind in a.accepts]


def arm_for_intake(intake_id: str) -> Arm | None:
    """The arm fed by one intake-form panel, or None if nothing reads it.

    Most panels on the form have no model behind them yet; that is not an error,
    the evidence is simply stored and not scored.
    """
    return next((a for a in ARMS.values() if a.intake_id == intake_id), None)


ARMS: dict[str, Arm] = {
    tb_xray.NAME: Arm(
        name=tb_xray.NAME,
        version=tb_xray.VERSION,
        arm_type="vision",
        intake_id="cxr_lung",
        accepts=frozenset({EvidenceKind.CHEST_XRAY}),
        preprocessing_version=tb_xray.PREPROCESSING_VERSION,
        weight_hash=tb_xray.WEIGHT_HASH,
        validation=tb_xray.VALIDATION,
        run=tb_xray.run,
        available=tb_xray.available,
    ),
    dr_fundus.NAME: Arm(
        name=dr_fundus.NAME,
        version=dr_fundus.VERSION,
        arm_type="vision",
        # The form's panel is still called `eyepacs`, after the dataset the
        # original idea document named. It is an id stored on past applications,
        # not a claim about the model, so it stays.
        intake_id="eyepacs",
        accepts=frozenset({EvidenceKind.FUNDUS}),
        preprocessing_version=dr_fundus.PREPROCESSING_VERSION,
        weight_hash=dr_fundus.WEIGHT_HASH,
        validation=dr_fundus.VALIDATION,
        run=dr_fundus.run,
        available=dr_fundus.available,
    ),
}
