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
    # To use a database on another machine, change DB_HOST to that machine's IP.
    # That is the only line you need to touch.
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "homelander"
    db_password: str = "devpassword"
    db_name: str = "homelander"
    # How long to wait for the database to answer before giving up.
    #
    # A firewalled machine does not refuse the connection, it drops the packet,
    # so without a timeout the client waits on the operating system's default —
    # measured at 21 seconds on this network. An underwriter watching a spinner
    # for 21 seconds concludes the application is broken, which is a worse
    # outcome than a fast, clear failure. On a LAN a real connection takes
    # milliseconds.
    db_connect_timeout_seconds: int = 5

    # ── Evidence storage ──────────────────────────────────────
    # Uploaded evidence is written to ./data at the repo root, not to an object
    # store. One machine, a few MB per application, and the files must not
    # leave it — a bucket would be infrastructure we do not need
    # (docs/DESIGN_POLICY.md §9). Already gitignored.
    data_dir: Path = _REPO_ROOT / "data"

    # ── Auth ──────────────────────────────────────────────────
    jwt_secret: str = "dev-only-do-not-use-in-any-real-deployment"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30

    # ── Built-in admin sign-in ────────────────────────────────
    # Username `admin`, password `admin123`. Works with no database at all, so
    # a demo survives the database machine being unreachable.
    #
    # Ready to use in development with no setup. It is ignored entirely outside
    # development, and clearing ADMIN_PASSWORD switches it off.
    admin_username: str = "admin"
    admin_password: str = "admin123"
    admin_display_name: str = "Administrator"
    admin_company_name: str = "Demo Insurance Co."

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def database_url(self) -> str:
        """Assembled from the parts above so only DB_HOST has to change."""
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def admin_login_enabled(self) -> bool:
        """Development only, and only while a password is set.

        The environment check is what stops this following the code into a real
        deployment; clearing the password is how you switch it off by hand.
        """
        return self.is_development and bool(self.admin_password)



@lru_cache
def get_settings() -> Settings:
    """Cached so the `.env` file is read once per process."""
    return Settings()


settings = get_settings()
