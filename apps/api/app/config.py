"""Application settings, loaded from the repo-root `.env`.

Fields marked "Phase 1" are declared but not yet consumed anywhere. They exist
so the whole team shares one config surface and one `.env.example`, rather than
each person inventing their own env var names when they wire up their layer.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# app/config.py -> app -> api -> apps -> <repo root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_API_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Later files win, so a local apps/api/.env can override the shared root one.
        env_file=(_REPO_ROOT / ".env", _API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    app_name: str = "HomelanderAI API"
    version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    # ── API ──────────────────────────────────────────────────
    api_host: str = "127.0.0.1"
    api_port: int = 8000

    # Comma-separated rather than a JSON list: pydantic-settings parses list
    # fields as JSON, which makes CORS_ORIGINS=http://a,http://b fail confusingly.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── Phase 1: persistence ─────────────────────────────────
    database_url: str = "postgresql+psycopg://homelander:devpassword@localhost:5432/homelander"

    # ── Phase 1: jobs ────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Phase 1: object storage ──────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_bucket: str = "homelander-evidence"
    minio_secure: bool = False

    # ── Phase 1: auth ────────────────────────────────────────
    jwt_secret: str = "dev-only-do-not-use-in-any-real-deployment"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached so the `.env` file is read once per process."""
    return Settings()


settings = get_settings()
