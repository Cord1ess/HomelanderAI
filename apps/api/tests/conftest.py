"""Shared fixtures.

The database-backed tests create their own tenants and delete them afterwards,
so they leave no rows behind and never depend on `db/seed.sql` having been run.

Anyone working on the dashboard or the models has no Postgres — that is
deliberate (see pyproject.toml). Those tests skip rather than fail, so `npm run
check` stays meaningful for everyone.
"""

import asyncio
import os
import shutil
import uuid
from pathlib import Path

import pytest

# The tests use their own database, never the one the app runs on. They clean
# up their rows, but two things outlive a test in a shared database: the
# HL- reference sequence (sequences do not roll back, so every test applicant
# burned a number — the demo reached HL-001760 with 70 real applicants), and
# the evidence files written to disk. Set before anything imports the settings.
os.environ["DB_NAME"] = os.environ.get("TEST_DB_NAME", "homelander_test")

from app.core.security import hash_password  # noqa: E402


def _prepare_test_database() -> None:
    """Create the test database if it is missing, and bring it to head.

    Silent if Postgres is not running at all: the database tests then skip,
    which is the existing behaviour for anyone without Postgres.
    """
    try:
        import psycopg2
        from psycopg2 import sql

        from app.config import settings

        admin = psycopg2.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            dbname="postgres",
            connect_timeout=3,
        )
    except Exception:
        return
    admin.autocommit = True
    with admin.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (settings.db_name,))
        if cursor.fetchone() is None:
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.db_name)))
    admin.close()

    from alembic.config import Config

    from alembic import command

    api = Path(__file__).resolve().parents[1]
    config = Config(str(api / "alembic.ini"))
    config.set_main_option("script_location", str(api / "alembic"))
    command.upgrade(config, "head")


_prepare_test_database()


def _database_reachable() -> bool:
    async def check() -> bool:
        from sqlalchemy import text

        from app.db.session import engine

        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    return asyncio.run(check())


needs_database = pytest.mark.skipif(
    not _database_reachable(),
    reason="No database reachable — start Postgres and run `alembic upgrade head`",
)


@pytest.fixture
def carrier():
    """A throwaway tenant with one underwriter, deleted afterwards.

    Every tenant-owned table cascades from `tenants`, so deleting the tenant is
    enough to clean up applications, evidence, scores and audit rows.
    """
    created: list[uuid.UUID] = []

    async def make(name: str = "Test Carrier", role: str = "admin") -> dict:
        from app.db.session import AsyncSessionLocal
        from app.models import Tenant, User, UserRole

        async with AsyncSessionLocal() as db:
            tenant = Tenant(name=name, subscription_tier="standard")
            db.add(tenant)
            await db.flush()

            email = f"{uuid.uuid4().hex[:12]}@test.local"
            user = User(
                tenant_id=tenant.id,
                full_name="Test Underwriter",
                email=email,
                password_hash=hash_password("testpassword123"),
                # An administrator by default: it may take applications and
                # decide any case, so tests do not trip over the tier rules.
                # (It was a doctor until doctors stopped deciding policies.)
                # A test about who is refused passes the role it needs.
                role=UserRole(role),
            )
            db.add(user)
            await db.commit()
            created.append(tenant.id)
            return {"tenant_id": tenant.id, "email": email, "password": "testpassword123"}

    yield make

    async def cleanup() -> None:
        from sqlalchemy import delete, text

        from app.db.session import AsyncSessionLocal
        from app.models import Tenant

        if not created:
            return

        async with AsyncSessionLocal() as db:
            # Deleting the tenant cascades to audit_log, and the append-only
            # trigger refuses that delete — correctly, since real audit rows
            # must never be removable this way. Turning it off for the teardown
            # is the honest way to clean up after a test; if it ever failed to
            # come back on, `test_audit_rows_cannot_be_updated_or_deleted` is
            # what would notice.
            await db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_delete"))
            try:
                for tenant_id in created:
                    await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
                await db.commit()
            finally:
                await db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_delete"))
                await db.commit()

        # The rows cascade away with the tenant; its evidence on disk does not.
        from app.config import settings

        for tenant_id in created:
            shutil.rmtree(settings.data_dir / str(tenant_id), ignore_errors=True)

    asyncio.run(cleanup())
