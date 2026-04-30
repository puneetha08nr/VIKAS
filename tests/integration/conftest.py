import os
import sys
import uuid
from pathlib import Path

# ── MUST run before any app module is imported ────────────────────────────────
# pydantic-settings reads DATABASE_URL at Settings() instantiation time.
# Overriding it here ensures the test process never touches the dev database.
_TEST_DB_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://vikas:vikas_dev@localhost:5432/vikas_test",
)
os.environ["DATABASE_URL"] = _TEST_DB_URL
os.environ.setdefault("MOCK_LLM", "true")

# Add this directory to sys.path so test files can 'from _helpers import ...'
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from _helpers import org_session_for_test  # noqa: F401 — re-exported for test files

_API_DIR = Path(__file__).parents[2] / "apps" / "api"
# Alembic requires a sync driver URL; asyncpg is only for the async ORM path.
_SYNC_TEST_DB_URL = _TEST_DB_URL.replace("postgresql+asyncpg://", "postgresql://")


# ── Session-scoped: migrate once for the entire pytest session ────────────────

@pytest.fixture(scope="session")
def apply_migrations() -> None:
    """Apply all Alembic migrations to vikas_test.

    The test database must already exist before running pytest.
    Create it once with: PGPASSWORD=vikas_dev createdb -h localhost -U vikas vikas_test
    """
    cfg = AlembicConfig(str(_API_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", _SYNC_TEST_DB_URL)
    cfg.set_main_option("script_location", str(_API_DIR / "db/migrations"))
    alembic_command.upgrade(cfg, "head")


# ── Function-scoped: one engine per test ─────────────────────────────────────

@pytest.fixture()
async def db_engine(apply_migrations):
    engine = create_async_engine(_TEST_DB_URL, echo=False, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def admin_db(db_engine):
    """Session with no RLS context — for organizations and prompts only.

    RLS is not enabled on organizations or prompts, so plain sessions suffice
    for setup. INSERTs into RLS-enabled tables are also unrestricted (no WITH CHECK
    clause) so admin_db can seed brand_voice rows too.
    """
    factory = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session


@pytest.fixture()
async def test_org(admin_db, db_engine):
    """Create a test organization and return its org_id (str).

    Seeds: organizations row, brand_voice row, keyword_research prompt
    (the prompt insert is idempotent — skipped if an active row already exists).
    """
    org_id = str(uuid.uuid4())

    await admin_db.execute(
        text(
            "INSERT INTO organizations (id, name, slug, supabase_user_id) "
            "VALUES (:id, :name, :slug, :suid)"
        ),
        {
            "id": org_id,
            "name": "Integration Test Org",
            "slug": f"test-{org_id[:8]}",
            "suid": str(uuid.uuid4()),
        },
    )

    # INSERT into brand_voice is unrestricted (RLS USING-only policy, no WITH CHECK).
    # brand_voice has no created_at; updated_at has a server default.
    await admin_db.execute(
        text(
            "INSERT INTO brand_voice (id, org_id) "
            "VALUES (gen_random_uuid(), :org_id)"
        ),
        {"org_id": org_id},
    )

    # Idempotent: skip if an active keyword_research prompt already exists
    await admin_db.execute(
        text(
            "INSERT INTO prompts (id, agent_name, version, template, active, created_at) "
            "SELECT gen_random_uuid(), 'keyword_research', 1, :tmpl, true, now() "
            "WHERE NOT EXISTS ("
            "    SELECT 1 FROM prompts "
            "    WHERE agent_name = 'keyword_research' AND active = true"
            ")"
        ),
        {"tmpl": "Return a JSON array of 5 keyword objects for the seed keyword."},
    )

    await admin_db.commit()
    return org_id
