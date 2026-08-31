"""FastAPI application entrypoint.

Run it from `apps/api`:

    uv run uvicorn app.main:app --reload

All routes live under `/api` so that the built frontend can be served from `/`
later without a path collision.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, health

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

app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")

