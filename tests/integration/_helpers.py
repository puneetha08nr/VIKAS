from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@asynccontextmanager
async def org_session_for_test(engine, org_id: str):
    """Open an RLS-enforced session scoped to org_id.

    Uses the test engine (not the production singleton from db.session).
    SET ROLE drops superuser privileges so RLS policies actually fire —
    PostgreSQL superusers bypass RLS regardless of FORCE ROW LEVEL SECURITY.
    """
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    session = factory()
    try:
        await session.execute(text("SET ROLE vikas_app"))
        await session.execute(text(f"SET app.current_org_id = '{org_id}'"))
        yield session
    finally:
        try:
            await session.execute(text("RESET ROLE"))
        except Exception:
            pass
        await session.close()
