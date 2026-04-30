from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from config.settings import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.is_dev,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — plain session with no RLS context (use for admin/internal ops)."""
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def org_session(org_id: str) -> AsyncGenerator[AsyncSession, None]:
    """Context manager that opens a session and pins the PostgreSQL RLS variable for this org."""
    async with AsyncSessionLocal() as session:
        await session.execute(text(f"SET app.current_org_id = '{org_id}'"))
        yield session


async def get_org_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — RLS-scoped session.

    Requires auth middleware to set ``request.state.org_id`` before this
    dependency runs (e.g. from a verified JWT claim).
    """
    org_id: str = request.state.org_id
    async with org_session(org_id) as session:
        yield session
