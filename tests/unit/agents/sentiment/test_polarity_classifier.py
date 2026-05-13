"""Unit tests for PolarityClassifierAgent and its JSON parsers."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.sentiment.polarity_classifier  # noqa: F401

from agents.sentiment.polarity_classifier import (
    PolarityClassifierAgent,
    _parse_batch,
    _parse_polarity,
    _prompt_hash,
)
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_EN_POLARITY_JSON = """{
  "polarity": "negative",
  "polarity_score": -0.72,
  "confidence": 0.88,
  "reasoning": "Complaint about delayed payments.",
  "contains_sarcasm": false,
  "is_about_scheme": true
}"""

_BATCH_JSON = """[
  {"id": "m1", "polarity": "positive", "polarity_score": 0.6, "confidence": 0.8, "is_about_scheme": true},
  {"id": "m2", "polarity": "neutral", "polarity_score": 0.0, "confidence": 0.9, "is_about_scheme": true}
]"""


def _make_ctx(db: AsyncMock, llm_response: str = _EN_POLARITY_JSON) -> AgentContext:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=llm_response)
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={},
        config={},
        db=db,
        llm=llm,
    )


def _pending_mention(
    mid: str = "m1",
    lang: str = "en",
    vader_score: float | None = 0.0,
    vader_confidence: float | None = 0.5,
    body: str = "This scheme delayed our payment for three months.",
) -> dict:
    return {
        "id": mid,
        "org_id": ORG_ID,
        "source": "newsapi",
        "matched_scheme": "amma_scheme",
        "matched_district": "madurai",
        "body_clean": body,
        "language": lang,
        "vader_score": vader_score,
        "vader_confidence": vader_confidence,
    }


def _make_db(mentions: list) -> AsyncMock:
    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM relevant_mentions" in sql:
            rows = []
            for m in mentions:
                row = MagicMock()
                row._mapping = m
                rows.append(row)
            result.fetchall.return_value = rows
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


# ── Parser unit tests ─────────────────────────────────────────────────────────

def test_parse_polarity_happy_path() -> None:
    out = _parse_polarity(_EN_POLARITY_JSON)
    assert out.polarity == "negative"
    assert out.polarity_score == pytest.approx(-0.72)
    assert out.confidence == pytest.approx(0.88)
    assert out.contains_sarcasm is False
    assert out.is_about_scheme is True


def test_parse_polarity_strips_markdown_fences() -> None:
    wrapped = f"```json\n{_EN_POLARITY_JSON}\n```"
    out = _parse_polarity(wrapped)
    assert out.polarity == "negative"


def test_parse_polarity_invalid_returns_neutral_default() -> None:
    out = _parse_polarity("not json at all")
    assert out.polarity == "neutral"
    assert out.confidence == pytest.approx(0.5)


def test_parse_polarity_clamps_invalid_enum_to_neutral() -> None:
    out = _parse_polarity('{"polarity": "unknown", "polarity_score": 0.0, "confidence": 0.5}')
    assert out.polarity == "neutral"


def test_parse_batch_happy_path() -> None:
    out = _parse_batch(_BATCH_JSON)
    assert len(out.items) == 2
    assert out.items[0].id == "m1"
    assert out.items[0].polarity == "positive"
    assert out.items[1].polarity == "neutral"


def test_parse_batch_empty_returns_empty() -> None:
    out = _parse_batch("[]")
    assert out.items == []


def test_parse_batch_skips_invalid_items() -> None:
    # "yes" is not a valid polarity literal — Pydantic validation fails → item dropped
    bad = '[{"id": "x1", "polarity": "yes", "polarity_score": "bad", "confidence": 0.5, "is_about_scheme": true}]'
    out = _parse_batch(bad)
    assert len(out.items) == 0


def test_prompt_hash_length() -> None:
    h = _prompt_hash("some template text")
    assert len(h) == 16


def test_prompt_hash_deterministic() -> None:
    assert _prompt_hash("template") == _prompt_hash("template")


# ── Agent: VADER fast-path (no LLM) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_vader_fast_path_skips_llm() -> None:
    m = _pending_mention(lang="en", vader_score=0.8, vader_confidence=0.92)
    db = _make_db([m])
    llm = MagicMock()
    llm.complete = AsyncMock()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params={"vader_threshold": 0.85},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.polarity_classifier.PromptRegistry"):
        result = await PolarityClassifierAgent().run(ctx)

    assert result.status == "success"
    assert result.data["vader"] == 1
    assert result.data["haiku_en"] == 0
    assert result.data["sonnet_ta"] == 0
    llm.complete.assert_not_called()


# ── Agent: English LLM path ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_english_low_confidence_calls_llm() -> None:
    m = _pending_mention(lang="en", vader_score=0.1, vader_confidence=0.4)
    db = _make_db([m])
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_EN_POLARITY_JSON)
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params={"vader_threshold": 0.85},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.polarity_classifier.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(return_value="SCHEME_NAME DISTRICT_NAME SOURCE_TYPE MENTION_TEXT")
        result = await PolarityClassifierAgent().run(ctx)

    assert result.status == "success"
    assert result.data["haiku_en"] == 1
    llm.complete.assert_called_once()


# ── Agent: Tamil mention → Sonnet path ───────────────────────────────────────

@pytest.mark.asyncio
async def test_tamil_mention_uses_sonnet_tier() -> None:
    m = _pending_mention(lang="ta", vader_score=None, vader_confidence=None)
    db = _make_db([m])
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_EN_POLARITY_JSON)
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.polarity_classifier.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(
            return_value="SCHEME_NAME DISTRICT_NAME SOURCE_TYPE DETECTED_LANGUAGE MENTION_TEXT"
        )
        result = await PolarityClassifierAgent().run(ctx)

    assert result.status == "success"
    assert result.data["sonnet_ta"] == 1
    # LLM called with tier="standard"
    call_kwargs = llm.complete.call_args
    assert call_kwargs.kwargs.get("tier") == "standard"


# ── Agent: empty pending → success ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_pending_returns_success() -> None:
    db = _make_db([])
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={},
        config={}, db=db, llm=MagicMock(),
    )
    result = await PolarityClassifierAgent().run(ctx)
    assert result.status == "success"
    assert result.data["processed"] == 0


# ── Agent: batch path triggered when >= 5 short mentions ─────────────────────

@pytest.mark.asyncio
async def test_batch_path_triggered_for_five_short_mentions() -> None:
    mentions = [
        _pending_mention(mid=f"m{i}", lang="en", vader_confidence=0.3, body="Short mention text here.")
        for i in range(5)
    ]
    db = _make_db(mentions)
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_BATCH_JSON[:100] + "[]")
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={"vader_threshold": 0.85},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.polarity_classifier.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(
            return_value="SCHEME_NAME DISTRICT_NAME MENTION_BATCH_JSON"
        )
        result = await PolarityClassifierAgent().run(ctx)

    assert result.status == "success"
    # batch path was triggered (LLM called once for the batch)
    assert llm.complete.call_count >= 1
