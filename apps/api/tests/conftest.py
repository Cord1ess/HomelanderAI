"""Shared fixtures.

The database-backed tests create their own tenants and delete them afterwards,
so they leave no rows behind and never depend on `db/seed.sql` having been run.

Anyone working on the dashboard or the models has no Postgres — that is
deliberate (see pyproject.toml). Those tests skip rather than fail, so `npm run
check` stays meaningful for everyone.
"""

import asyncio
import uuid

import pytest

from app.core.security import hash_password


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

    async def make(name: str = "Test Carrier") -> dict:
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
                role=UserRole.SENIOR_UNDERWRITER,
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

    asyncio.run(cleanup())
