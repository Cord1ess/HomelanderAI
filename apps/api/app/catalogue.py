"""The model menu shown on the intake form.

This list lives here rather than in the dashboard because whether a model
actually runs is a fact about the backend, and the form was previously offering
seven models as though all seven worked. Only one does. An operator ticking
"Mirai" and attaching a mammogram got no score, no error, and no explanation.

`status` is derived from the arm registry, never written by hand — an arm that
is implemented becomes available here the moment it is registered, and one that
is removed stops claiming to work.
"""

from dataclasses import dataclass

from app.arms import arm_for_intake


@dataclass(frozen=True)
class CatalogueEntry:
    id: str
    label: str
    # The evidence the operator attaches, in their words.
    evidence: str
    # What it screens for. "Chest X-ray" is a file; "tuberculosis" is the answer.
    screens_for: str


# Ordered as the form should show them: the one that works first.
CATALOGUE: list[CatalogueEntry] = [
    CatalogueEntry(
        id="cxr_lung",
        label="Chest X-ray",
        evidence="Chest X-ray (.dcm, .png, .jpg)",
        screens_for="Tuberculosis",
    ),
    CatalogueEntry(
        id="mirai",
        label="Mammogram",
        evidence="Mammogram, 4 views (.dcm)",
        screens_for="Breast cancer risk",
    ),
    CatalogueEntry(
        id="ham10000",
        label="Skin lesion",
        evidence="Lesion photograph (.png, .jpg)",
        screens_for="Skin cancer",
    ),
    CatalogueEntry(
        id="eyepacs",
        label="Retinal photo",
        evidence="Fundus photograph (.png, .jpg)",
        screens_for="Diabetic retinopathy",
    ),
    CatalogueEntry(
        id="biobert",
        label="Clinical notes",
        evidence="Physician note (.pdf, .txt)",
        screens_for="History extracted from written notes",
    ),
    CatalogueEntry(
        id="xgboost",
        label="Lifestyle and measurements",
        evidence="No upload — answered on the form",
        screens_for="Actuarial risk from demographics",
    ),
    CatalogueEntry(
        id="neuro",
        label="Brain MRI",
        evidence="Brain MRI (.dcm)",
        screens_for="Neurodegenerative change",
    ),
]


def as_dicts() -> list[dict]:
    """The catalogue with each entry's real status attached."""
    entries = []
    for entry in CATALOGUE:
        arm = arm_for_intake(entry.id)
        entries.append(
            {
                "id": entry.id,
                "label": entry.label,
                "evidence": entry.evidence,
                "screens_for": entry.screens_for,
                "available": arm is not None,
                "arm_name": arm.name if arm else None,
                "arm_version": arm.version if arm else None,
                # Straight from the arm, so a retrained model updates the
                # caveat on the form without anyone remembering to.
                "validation": arm.validation if arm else None,
            }
        )
    return entries
