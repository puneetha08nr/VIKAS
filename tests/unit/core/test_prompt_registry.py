from unittest.mock import AsyncMock, MagicMock, call

import pytest

from core.prompt_registry import PromptNotFoundError, PromptRegistry


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry()


def _db_with_scalar(value: object) -> AsyncMock:
    """Return a mock db whose execute() returns a result with scalar() == value."""
    result = MagicMock()
    result.scalar.return_value = value
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _db_with_fetchone(row: tuple | None) -> AsyncMock:
    """Return a mock db whose execute() returns a result with fetchone() == row."""
    result = MagicMock()
    result.fetchone.return_value = row
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


def _db_with_fetchall(rows: list[tuple]) -> AsyncMock:
    result = MagicMock()
    result.fetchall.return_value = rows
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)
    return db


# ── get ───────────────────────────────────────────────────────────────────────

async def test_get_returns_active_prompt(registry: PromptRegistry) -> None:
    db = _db_with_fetchone(("You are a keyword research specialist...",))

    template = await registry.get("keyword_research", db)

    assert template == "You are a keyword research specialist..."
    db.execute.assert_called_once()
    sql = str(db.execute.call_args[0][0])
    assert "active = true" in sql.lower() or "active" in sql


async def test_get_raises_prompt_not_found_when_missing(registry: PromptRegistry) -> None:
    db = _db_with_fetchone(None)

    with pytest.raises(PromptNotFoundError) as exc_info:
        await registry.get("nonexistent_agent", db)

    assert exc_info.value.agent_name == "nonexistent_agent"
    assert "nonexistent_agent" in str(exc_info.value)


async def test_get_queries_correct_agent_name(registry: PromptRegistry) -> None:
    db = _db_with_fetchone(("template text",))

    await registry.get("article_writer", db)

    _, params = db.execute.call_args[0]
    assert params["agent_name"] == "article_writer"


# ── set ───────────────────────────────────────────────────────────────────────

async def test_set_deactivates_old_and_creates_new(registry: PromptRegistry) -> None:
    # First execute: UPDATE (deactivate) — no return value needed
    # Second execute: SELECT MAX(version) → returns 2
    # Third execute: INSERT new row
    update_result = MagicMock()
    max_version_result = MagicMock()
    max_version_result.scalar.return_value = 2
    insert_result = MagicMock()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[update_result, max_version_result, insert_result]
    )

    version = await registry.set("keyword_research", "new template", db)

    assert version == 3
    assert db.execute.call_count == 3
    assert db.commit.called

    # First call should be the deactivation UPDATE
    first_sql = str(db.execute.call_args_list[0][0][0])
    assert "active = false" in first_sql.lower() or "false" in first_sql


async def test_set_returns_version_1_for_new_agent(registry: PromptRegistry) -> None:
    update_result = MagicMock()
    max_version_result = MagicMock()
    max_version_result.scalar.return_value = 0  # no existing versions
    insert_result = MagicMock()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[update_result, max_version_result, insert_result]
    )

    version = await registry.set("brand_new_agent", "my template", db)

    assert version == 1


async def test_set_passes_template_to_insert(registry: PromptRegistry) -> None:
    update_result = MagicMock()
    max_version_result = MagicMock()
    max_version_result.scalar.return_value = 0
    insert_result = MagicMock()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[update_result, max_version_result, insert_result]
    )

    await registry.set("my_agent", "the real template text", db)

    insert_params = db.execute.call_args_list[2][0][1]
    assert insert_params["template"] == "the real template text"
    assert insert_params["agent_name"] == "my_agent"


# ── rollback ──────────────────────────────────────────────────────────────────

async def test_rollback_switches_active_version(registry: PromptRegistry) -> None:
    find_result = MagicMock()
    find_result.fetchone.return_value = ("some-uuid",)  # version exists
    deactivate_result = MagicMock()
    activate_result = MagicMock()

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[find_result, deactivate_result, activate_result]
    )

    success = await registry.rollback("keyword_research", version=2, db=db)

    assert success is True
    assert db.execute.call_count == 3
    assert db.commit.called


async def test_rollback_returns_false_when_version_missing(registry: PromptRegistry) -> None:
    find_result = MagicMock()
    find_result.fetchone.return_value = None  # version does not exist

    db = AsyncMock()
    db.execute = AsyncMock(return_value=find_result)

    success = await registry.rollback("keyword_research", version=99, db=db)

    assert success is False
    # Should not attempt to deactivate/activate when version is missing
    assert db.execute.call_count == 1
    db.commit.assert_not_called()


async def test_rollback_passes_correct_params(registry: PromptRegistry) -> None:
    find_result = MagicMock()
    find_result.fetchone.return_value = ("uuid",)

    db = AsyncMock()
    db.execute = AsyncMock(
        side_effect=[find_result, MagicMock(), MagicMock()]
    )

    await registry.rollback("article_writer", version=3, db=db)

    # Third call activates target version
    activate_params = db.execute.call_args_list[2][0][1]
    assert activate_params["version"] == 3
    assert activate_params["agent_name"] == "article_writer"


# ── history ───────────────────────────────────────────────────────────────────

async def test_history_returns_all_versions_newest_first(registry: PromptRegistry) -> None:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    rows = [
        ("uuid-3", "keyword_research", 3, "template v3", True, now),
        ("uuid-2", "keyword_research", 2, "template v2", False, now),
        ("uuid-1", "keyword_research", 1, "template v1", False, now),
    ]
    db = _db_with_fetchall(rows)

    history = await registry.history("keyword_research", db)

    assert len(history) == 3
    assert history[0]["version"] == 3
    assert history[0]["active"] is True
    assert history[1]["version"] == 2
    assert history[2]["version"] == 1


async def test_history_returns_empty_list_for_unknown_agent(registry: PromptRegistry) -> None:
    db = _db_with_fetchall([])

    history = await registry.history("ghost_agent", db)

    assert history == []


async def test_history_entry_has_expected_keys(registry: PromptRegistry) -> None:
    from datetime import datetime, timezone

    rows = [("uuid-1", "seo_agent", 1, "tmpl", True, datetime.now(timezone.utc))]
    db = _db_with_fetchall(rows)

    history = await registry.history("seo_agent", db)

    entry = history[0]
    assert set(entry.keys()) == {"id", "agent_name", "version", "template", "active", "created_at"}
