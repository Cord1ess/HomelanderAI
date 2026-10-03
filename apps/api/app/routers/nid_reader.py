"""Reading an NID card at intake: a photo in, the name, birth date and number out.

Stores nothing. The operator sees what was read beside the card and confirms
it; the image itself is sent again with the application and stored there.
"""

import asyncio
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import Field

from app import nid
from app.deps import Principal, current_principal
from app.models import UserRole
from app.schemas.auth import BaseSchema

router = APIRouter(tags=["NID"])

MAX_BYTES = 10 * 1024 * 1024


class NidReadSchema(BaseSchema):
    number: str | None = None
    name: str | None = None
    date_of_birth: date | None = None
    confidence: float | None = None
    missing: list[str] = Field(default_factory=list)
    lines: list[str] = Field(default_factory=list)


@router.post("/nid/read", response_model=NidReadSchema, summary="Read an NID card photo")
async def read_card(
    image: UploadFile = File(...),
    principal: Principal = Depends(current_principal),
) -> NidReadSchema:
    if principal.role == UserRole.MEDICAL_PROFESSIONAL.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Intake is not a doctor's."
        )
    if not nid.available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The NID reader is not installed on this server. Type the details in.",
        )
    raw = await image.read()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Send a photo of the front of the card, up to 10 MB.",
        )
    try:
        reading = await asyncio.to_thread(nid.read, raw)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="That image could not be read as a card. Try a sharper, straight-on photo.",
        ) from exc
    return NidReadSchema(
        number=reading.number,
        name=reading.name,
        date_of_birth=reading.date_of_birth,
        confidence=reading.confidence,
        missing=reading.missing,
        lines=reading.lines,
    )
