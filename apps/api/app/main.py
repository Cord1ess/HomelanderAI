"""FastAPI application entrypoint.

Run it from `apps/api`:

    uv run uvicorn app.main:app --reload

All routes live under `/api` so that the built frontend can be served from `/`
later without a path collision.
"""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.routers import applications, auth, health, notifications

log = logging.getLogger(__name__)


def _warm_models() -> None:
    """Load the vision backbone so the first real application is not the one
    that pays for it.

    torchxrayvision fetches and unpickles the DenseNet weights on first use,
    which takes 20-30 seconds. Left lazy, that cost lands on whoever submits the
    first application after a restart — at a demo, that is the demo.

    On a thread, so the server accepts requests immediately and the model loads
    while somebody is still signing in. Failure is not fatal: without torch
    installed the arm reports itself unavailable and the pipeline degrades
    exactly as it is designed to.
    """
    try:
        from app.arms import tb_xray

        if not tb_xray.available():
            log.info("Vision arm unavailable (no torch); skipping warm-up.")
            return
        tb_xray._get_model()
        log.info("Vision arm ready.")
    except Exception as exc:
        log.warning("Could not warm the vision arm: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    threading.Thread(target=_warm_models, name="warm-models", daemon=True).start()
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Decision-support API for life, health and critical-illness underwriting. "
        "Research software — not a medical device."
    ),
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# The Vite dev server proxies /api, so requests are same-origin in normal
# development. This is here for anyone calling the API directly.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── database outages answer 503, never 500 ───────────────────────────────────
#
# The database runs on a different machine (docs/DEMO_SETUP.md), so it being
# unreachable is an ordinary operating condition, not a programming error. One
# handler covers every endpoint: adding a try/except to each of them would be
# the same code in eight places, and the ninth would be the one someone forgets.
#
# Note `TimeoutError` is a subclass of `OSError`, which is what a firewalled
# host produces — it drops the packet rather than refusing the connection.
@app.exception_handler(OSError)
@app.exception_handler(SQLAlchemyError)
async def _database_unreachable(_: Request, exc: Exception) -> JSONResponse:
    log.error("Database unreachable: %s: %s", type(exc).__name__, exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": (
                "Cannot reach the database. Check its address in .env, or sign "
                "in with the built-in admin account."
            )
        },
    )


app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(applications.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")

