"""Unit tests for BrandVoiceKeeperAgent."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.knowledge.brand_voice_keeper  # noqa: F401 — triggers @register

from agents.knowledge.brand_voice_keeper import BrandVoiceKeeperAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_DEFAULT_VOICE = ("friendly", ["AI", "automation"], ["spam", "cheap"], {"max_sentences": 3})


def _make_db(
    existing_voice: tuple | None = None,
    content_stats: list | None = None,
) -> AsyncMock:
    """
    existing_voice: (tone, vocabulary, banned_phrases, style_rules) or None (no row)
    content_stats:  list of (status, count) rows
    """
    content_stats = content_stats or []

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM brand_voice" in sql:
            result.fetchone.return_value = existing_voice
            result.fetchall.return_value = []
        elif "FROM content_items" in sql:
            result.fetchone.return_value = None
            result.fetchall.return_value = content_stats
        elif "INSERT INTO brand_voice" in sql:
            upserted = MagicMock()
            result.fetchone.return_value = upserted
        else:
            result.fetchone.return_value = None
            result.fetchall.return_value = []
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params=params or {},
        config={},
        db=db,
        llm=MagicMock(),
    )


# ── No existing row, no params ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_existing_no_params_returns_success() -> None:
    db = _make_db(existing_voice=None)
    ctx = _make_ctx(db)

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.status == "success"
    assert result.data["tone"] == ""
    assert result.data["vocabulary_terms"] == 0
    assert result.data["banned_phrases"] == 0


@pytest.mark.asyncio
async def test_no_existing_with_params_writes_new_row() -> None:
    db = _make_db(existing_voice=None)
    ctx = _make_ctx(db, params={
        "tone": "friendly",
        "vocabulary": ["AI", "automation"],
        "banned_phrases": ["spam"],
        "style_rules": {"max_sentences": 3},
    })

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.status == "success"
    assert result.data["tone"] == "friendly"
    assert result.data["vocabulary_terms"] == 2
    assert result.data["banned_phrases"] == 1
    assert result.data["style_rules"] == 1
    assert db.flush.called


# ── Existing row, params override ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_params_override_existing_tone() -> None:
    existing = ("old tone", ["old"], [], {})
    db = _make_db(existing_voice=existing)
    ctx = _make_ctx(db, params={"tone": "new tone"})

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.data["tone"] == "new tone"


@pytest.mark.asyncio
async def test_existing_voice_preserved_when_no_params() -> None:
    existing = _DEFAULT_VOICE  # (tone, vocab, banned, style)
    db = _make_db(existing_voice=existing)
    ctx = _make_ctx(db)

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.data["tone"] == "friendly"
    assert result.data["vocabulary_terms"] == 2
    assert result.data["banned_phrases"] == 2
    assert result.data["style_rules"] == 1


# ── Content stats ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_content_stats_reported() -> None:
    db = _make_db(
        existing_voice=_DEFAULT_VOICE,
        content_stats=[("approved", 5), ("published", 12)],
    )
    ctx = _make_ctx(db)

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.data["content_approved"] == 5
    assert result.data["content_published"] == 12


@pytest.mark.asyncio
async def test_no_content_stats_returns_zeros() -> None:
    db = _make_db(existing_voice=None, content_stats=[])
    ctx = _make_ctx(db)

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.data["content_approved"] == 0
    assert result.data["content_published"] == 0


# ── DB write ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_called_with_correct_org_id() -> None:
    db = _make_db(existing_voice=None)
    ctx = _make_ctx(db, params={"tone": "bold"})

    await BrandVoiceKeeperAgent().run(ctx)

    upsert_calls = [
        c for c in db.execute.call_args_list
        if "INSERT INTO brand_voice" in str(c[0][0])
    ]
    assert len(upsert_calls) == 1
    assert upsert_calls[0][0][1]["org_id"] == ORG_ID


# ── Tokens ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tokens_used_is_zero() -> None:
    db = _make_db(existing_voice=None)
    ctx = _make_ctx(db)

    result = await BrandVoiceKeeperAgent().run(ctx)

    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
