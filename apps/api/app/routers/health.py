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


class DatabaseHealth(BaseModel):
    connected: bool
    target: str = Field(description="host:port/database being dialled, password removed.")
    detail: str | None = Field(default=None, description="Why the connection failed.")
    admin_login_enabled: bool = Field(
        description="Whether the built-in admin sign-in works while the database is down."
    )


# What each failure actually means, in the order they are checked. The raw
# exception text is kept on the end because it is what someone would search for,
# but the sentence in front of it is the part that gets the demo working again.
_CAUSES: tuple[tuple[str, str], ...] = (
    (
        "timeout",
        "Timed out. The machine is on the network but nothing answered on this "
        "port — almost always its firewall, or PostgreSQL not running.",
    ),
    (
        "refused",
        "Connection refused. PostgreSQL is not running, or it is only listening "
        "on its own machine (set listen_addresses = '*').",
    ),
    (
        "password",
        "The password was rejected. Check DB_PASSWORD against the database.",
    ),
    (
        "does not exist",
        "The database or role does not exist. Check DB_NAME and DB_USER.",
    ),
    (
        "no route to host",
        "No route to the machine. The two are not on the same network.",
    ),
)


def _explain(exc: Exception) -> str:
    """Turn a driver error into something an operator can act on.

    `[WinError 121] The semaphore timeout period has expired` is accurate and
    tells nobody what to do about it.
    """
    raw = f"{type(exc).__name__}: {exc}"
    haystack = raw.lower()

    for needle, explanation in _CAUSES:
        if needle in haystack:
            return f"{explanation} ({raw})"[:300]

    return raw[:300]


def _safe_target(url: str) -> str:
    """host:port/database, with the credentials stripped so this is safe to show."""
    tail = url.rsplit("@", 1)[-1]
    return tail or "unknown"


@router.get(
    "/health/database",
    response_model=DatabaseHealth,
    summary="Can the API reach the database?",
)
async def health_database() -> DatabaseHealth:
    """Always answers 200, even when the database is unreachable — the point is
    to report the state, not to fail. Use it when the database lives on another
    machine and you need to know whether this one can see it."""
    from sqlalchemy import text

    from app.db.session import engine

    target = _safe_target(settings.database_url)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as exc:
        return DatabaseHealth(
            connected=False,
            target=target,
            detail=_explain(exc),
            admin_login_enabled=settings.admin_login_enabled,
        )

    return DatabaseHealth(
        connected=True,
        target=target,
        admin_login_enabled=settings.admin_login_enabled,
    )


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        uptime_seconds=round(time.monotonic() - _PROCESS_START, 3),
    )
