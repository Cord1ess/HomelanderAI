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
    run: Callable[[bytes], ArmResult]
    available: Callable[[], bool]


# Imported at the bottom on purpose: tb_xray does `from app.arms import
# ArmResult`, and by this point ArmResult is defined, so there is no cycle.
from app.arms import tb_xray  # noqa: E402

ARMS: dict[str, Arm] = {
    tb_xray.NAME: Arm(
        name=tb_xray.NAME,
        version=tb_xray.VERSION,
        arm_type="vision",
        run=tb_xray.run,
        available=tb_xray.available,
    ),
}
