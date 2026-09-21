"""Standard ModelResult schema and clinical entity models.

Conforms to docs/Model.md and the unified Homelander multi-model interface.
"""

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AssertionStatus(StrEnum):
    """Clinical assertion status according to ConText / NegEx ontology."""

    PRESENT = "PRESENT"
    NEGATED = "NEGATED"
    FAMILY_HISTORY = "FAMILY_HISTORY"
    HYPOTHETICAL = "HYPOTHETICAL"


class EntityResult(BaseModel):
    """A recognized clinical entity span with assertion metadata."""

    model_config = ConfigDict(populate_by_name=True)

    text: str = Field(..., description="The exact text span of the clinical entity")
    label: str = Field(..., description="Entity category/type (e.g., ENTITY, DISEASE, CHEMICAL)")
    assertion: str = Field(
        ...,
        description="Clinical assertion status: PRESENT, NEGATED, FAMILY_HISTORY, HYPOTHETICAL",
    )
    start_char: int = Field(..., description="Zero-based start character index in the source text")
    end_char: int = Field(..., description="Zero-based end character index in the source text")


class NLPRawOutput(BaseModel):
    """The raw output payload for clinical NLP model runs."""

    model_config = ConfigDict(populate_by_name=True)

    entities: list[EntityResult] = Field(default_factory=list)


class ModelResult(BaseModel):
    """Standard output schema returned by all Homelander model services."""

    model_config = ConfigDict(populate_by_name=True)

    model_id: str = Field(..., description="Unique identifier of the model (e.g. biobert, tb_xray)")
    status: Literal["success", "error", "unsupported_input"] = Field(
        default="success",
        description="Execution status of the model service",
    )
    risk_score: float | None = Field(
        default=None,
        description="Normalized risk score 0-100 if applicable",
    )
    label: str | None = Field(
        default=None,
        description="Top-level categorical label or summary finding if applicable",
    )
    confidence: float | None = Field(
        default=None,
        description="Confidence score 0-1 for top-level prediction if applicable",
    )
    raw_output: dict[str, Any] = Field(
        default_factory=dict,
        description="Model-specific payload containing raw predictions, entity spans, or heatmaps",
    )
