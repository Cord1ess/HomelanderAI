"""Liveness endpoint.

Deliberately reports only on the API process itself. Once Postgres is wired up
in Phase 1, add a separate `/api/health/dependencies` that pings it — keep this
one cheap so it stays a true liveness probe.
"""

import time
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter(tags=["system"])

_PROCESS_START = time.monotonic()


class HealthResponse(BaseModel):
    status: Literal["ok"] = Field(description="Always 'ok' — a failure means no response at all.")
    service: str = Field(description="Human-readable service name.")
    version: str = Field(description="API version.")
    environment: str = Field(description="development | staging | production")
    uptime_seconds: float = Field(description="Seconds since this process started.")

    model_config = {
        "json_schema_extra": {
            "example": {
                "status": "ok",
                "service": "HomelanderAI API",
                "version": "0.1.0",
                "environment": "development",
                "uptime_seconds": 12.34,
            }
        }
    }


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(time.monotonic() - _PROCESS_START, 3),
    )
