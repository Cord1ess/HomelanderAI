"""The model test bench: run one model on one test, outside any application.

For the company owner to see what each model makes of a file (or of typed
blood values) before trusting it with a client: the score, the raw output,
the details and any heatmap, and how long it took. Nothing is stored, no
application is created and nobody is notified.

It runs the same arm functions the pipeline runs, so what is seen here is what
an application would get. One difference, on purpose: the pipeline refuses to
hand a model a kind of file it does not read; the bench runs it anyway and
says so plainly, because seeing a confidently wrong answer is part of testing.
"""

import asyncio
import json
import time
from base64 import b64encode
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.encoders import jsonable_encoder
from pydantic import Field

from app import evidence as evidence_kinds
from app import triage
from app.arms import ArmResult, arm_for_intake
from app.db.session import get_db
from app.deps import Principal, current_principal
from app.intake import IntakeError, process_upload
from app.models import Tenant, UserRole
from app.routers.applications import _thresholds_for
from app.schemas.auth import BaseSchema
from app.scoring import fuse, score

router = APIRouter(tags=["Model test bench"])


class BenchRunSchema(BaseSchema):
    file_name: str | None = None
    # What the platform thinks the file is, and whether this model reads that.
    identified_as: str | None = None
    model_reads_it: bool = True
    score: float | None = None
    raw_score: float | None = None
    error: str | None = None
    details: dict = Field(default_factory=dict)
    # Heatmaps and other pictures the model drew, as data URLs.
    images: list[str] = Field(default_factory=list)
    duration_ms: int


class BenchResultSchema(BaseSchema):
    model_id: str
    model_name: str
    version: str
    validation: str
    runs: list[BenchRunSchema] = Field(default_factory=list)
    # The readings fused as an application would fuse them, and the declared
    # answers applied: the overall score and tier this alone would give.
    fused_score: float | None = None
    crs: float | None = None
    tier: str | None = None


def _images(result: ArmResult) -> list[str]:
    out = []
    for data in result.artifacts.values():
        if isinstance(data, bytes) and data[:8] == b"\x89PNG\r\n\x1a\n":
            out.append("data:image/png;base64," + b64encode(data).decode())
        elif isinstance(data, bytes) and data[:3] == b"\xff\xd8\xff":
            out.append("data:image/jpeg;base64," + b64encode(data).decode())
    return out


def _safe(details: dict) -> dict:
    """JSON-safe details; anything odd becomes its text."""
    try:
        return jsonable_encoder(details, custom_encoder={bytes: lambda b: f"<{len(b)} bytes>"})
    except Exception:
        return {k: str(v) for k, v in details.items()}


def _age(born: str | None) -> int | None:
    if not born:
        return None
    try:
        d = date.fromisoformat(born)
    except ValueError:
        return None
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


@router.post(
    "/models/{model_id}/try",
    response_model=BenchResultSchema,
    summary="Run one model on a test, outside any application (owner only)",
)
async def try_model(
    model_id: str,
    files: list[UploadFile] = File(default=[]),
    values: str = Form(default="{}"),
    date_of_birth: str | None = Form(default=None),
    sex: str | None = Form(default=None),
    db=Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> BenchResultSchema:
    if principal.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The model test bench is for the company owner (an administrator).",
        )
    arm = arm_for_intake(model_id)
    if arm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such model.")
    if not arm.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{arm.name} is not available on this server right now.",
        )
    try:
        declared = json.loads(values or "{}")
        if not isinstance(declared, dict):
            raise ValueError
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The typed values could not be read.",
        ) from exc
    age = _age(date_of_birth)

    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        if upload.filename:
            uploads.append((upload.filename, await upload.read()))

    if arm.run_form is None and not uploads:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="This model reads a file. Add one to test it.",
        )

    def work() -> list[BenchRunSchema]:
        runs: list[BenchRunSchema] = []

        def timed(fn) -> tuple[ArmResult, int]:
            started = time.perf_counter()
            try:
                result = fn()
            except Exception as exc:  # a crash is a result worth seeing here
                result = ArmResult(score=None, error=f"The model failed: {exc}")
            return result, int((time.perf_counter() - started) * 1000)

        if arm.run_form is not None:
            result, ms = timed(lambda: arm.run_form(declared, age, sex))
            runs.append(_run(None, None, True, result, ms))
            return runs

        processed = []
        for name, raw in uploads:
            try:
                item = process_upload(raw, name)
            except IntakeError as exc:
                runs.append(
                    BenchRunSchema(
                        file_name=name, error=f"Could not read the file: {exc}", duration_ms=0
                    )
                )
                continue
            verdict = triage.classify(item.data, name, item.clinical_tags)
            processed.append((name, item, verdict.kind))

        if arm.run_set is not None:
            if processed:
                result, ms = timed(lambda: arm.run_set([item.data for _, item, _ in processed]))
                kinds = {k for _, _, k in processed}
                runs.append(
                    _run(
                        ", ".join(n for n, _, _ in processed),
                        ", ".join(sorted(evidence_kinds.label(k) for k in kinds)),
                        all(k in arm.accepts for k in kinds),
                        result,
                        ms,
                    )
                )
            return runs

        for name, item, kind in processed:
            result, ms = timed(lambda item=item: arm.read(item.data, declared))
            runs.append(_run(name, evidence_kinds.label(kind), kind in arm.accepts, result, ms))
        return runs

    runs = await asyncio.to_thread(work)

    usable = [r.score for r in runs if r.score is not None]
    fused = fuse(usable) if usable else None
    thresholds = _thresholds_for(await db.get(Tenant, principal.tenant_id))
    overall = score(fused, declared, age=age, thresholds=thresholds) if fused is not None else None

    return BenchResultSchema(
        model_id=model_id,
        model_name=arm.name,
        version=arm.version,
        validation=arm.validation,
        runs=runs,
        fused_score=round(fused, 1) if fused is not None else None,
        crs=overall.crs if overall else None,
        tier=overall.tier if overall else None,
    )


def _run(
    name: str | None, identified: str | None, reads: bool, result: ArmResult, ms: int
) -> BenchRunSchema:
    return BenchRunSchema(
        file_name=name,
        identified_as=identified,
        model_reads_it=reads,
        score=round(result.score, 1) if result.score is not None else None,
        raw_score=result.raw_score,
        error=result.error,
        details=_safe(result.details),
        images=_images(result),
        duration_ms=ms,
    )
