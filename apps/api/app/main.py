"""FastAPI application entrypoint.

Run it from `apps/api`:

    uv run uvicorn app.main:app --reload

All routes live under `/api` so that the built frontend can be served from `/`
later without a path collision.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.logging_config import configure_logging, get_logger
from app.routers import health

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    Phase 1 wires the database engine, Redis pool and MinIO client in here and
    tears them down on the way out.
    """
    configure_logging()
    log.info(
        "api.startup",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        docs=f"http://{settings.api_host}:{settings.api_port}/docs",
    )
    yield
    log.info("api.shutdown")


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description=(
            "Decision-support API for life, health and critical-illness underwriting. "
            "Research software — not a medical device."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
    )

    # The Vite dev server proxies /api, so requests are same-origin in normal
    # development. This is here for anyone calling the API directly.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, prefix="/api")

    return application


app = create_app()
