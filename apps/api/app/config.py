"""Application settings, loaded from the repo-root `.env`.

Every field here is read by code that exists today. Add new settings alongside
the code that consumes them, not ahead of it.
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

    app_name: str = "HomelanderAI API"
    version: str = "0.1.0"
    environment: str = "development"

    # Comma-separated rather than a JSON list: pydantic-settings parses list
    # fields as JSON, which makes CORS_ORIGINS=http://a,http://b fail confusingly.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── Database ──────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://homelander:devpassword@localhost:5432/homelander"

    # ── Auth ──────────────────────────────────────────────────
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
