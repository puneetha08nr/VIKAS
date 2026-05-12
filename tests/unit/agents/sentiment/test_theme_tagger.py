"""Unit tests for ThemeTaggerAgent and pattern matching helpers."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.sentiment.theme_tagger  # noqa: F401

from agents.sentiment.theme_tagger import ThemeTaggerAgent, _pattern_match
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_TAXONOMY = [
    {
        "theme_key": "water_supply",
        "label_en": "Water Supply",
        "label_ta": "",
        "description": "Issues with water provision",
        "patterns_en": ["water supply", "water shortage", "tap water"],
        "patterns_ta": [],
    },
    {
        "theme_key": "pension_delay",
        "label_en": "Pension Delay",
        "label_ta": "",
        "description": "Delayed pension disbursement",
        "patterns_en": ["pension delay", "pension payment", "old age pension"],
        "patterns_ta": [],
    },
]

_THEME_LLM_JSON = """{
  "matched_themes": [
    {"theme_key": "water_supply", "confidence": 0.85, "evidence_quote": "water shortage in our area"}
  ],
  "no_match_reason": ""
}"""


def _pending_mention(
    mid: str = "m1",
    body: str = "There is a severe water shortage in our area under the scheme.",
    source_weight: float = 1.0,
    lang: str = "en",
) -> dict:
    return {
        "id": mid,
        "org_id": ORG_ID,
        "matched_scheme": "amma_scheme",
        "matched_district": "madurai",
        "body_clean": body,
        "language": lang,
        "source_weight": source_weight,
    }


def _make_db(mentions: list, taxonomy: list | None = None) -> AsyncMock:
    _tax = taxonomy if taxonomy is not None else _TAXONOMY

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM theme_taxonomy" in sql:
            rows = []
            for t in _tax:
                row = MagicMock()
                row._mapping = t
                rows.append(row)
            result.fetchall.return_value = rows
        elif "FROM relevant_mentions" in sql:
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


def _make_ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID,
        params=params or {},
        config={}, db=db, llm=MagicMock(),
    )


# ── Pattern matching unit tests ───────────────────────────────────────────────

def test_pattern_match_finds_water_supply() -> None:
    hits = _pattern_match("tap water supply is unreliable", _TAXONOMY)
    keys = [h.theme_key for h in hits]
    assert "water_supply" in keys


def test_pattern_match_finds_pension_delay() -> None:
    hits = _pattern_match("the pension payment has not arrived", _TAXONOMY)
    keys = [h.theme_key for h in hits]
    assert "pension_delay" in keys


def test_pattern_match_case_insensitive() -> None:
    hits = _pattern_match("WATER SHORTAGE in the district", _TAXONOMY)
    keys = [h.theme_key for h in hits]
    assert "water_supply" in keys


def test_pattern_match_no_match_returns_empty() -> None:
    hits = _pattern_match("cricket match score yesterday", _TAXONOMY)
    assert hits == []


def test_pattern_match_multiple_themes_in_one_mention() -> None:
    hits = _pattern_match(
        "water shortage and pension delay reported in madurai", _TAXONOMY
    )
    keys = {h.theme_key for h in hits}
    assert "water_supply" in keys
    assert "pension_delay" in keys


def test_pattern_match_confidence_is_high() -> None:
    hits = _pattern_match("water supply problems", _TAXONOMY)
    assert all(h.confidence >= 0.85 for h in hits)


# ── Agent: pattern match succeeds, no LLM ────────────────────────────────────

@pytest.mark.asyncio
async def test_pattern_match_writes_themes_no_llm() -> None:
    m = _pending_mention(body="water supply shortage and pension payment delay reported under the scheme")
    db = _make_db([m])
    ctx = _make_ctx(db)
    llm = MagicMock()
    llm.complete = AsyncMock()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.theme_tagger.PromptRegistry"):
        result = await ThemeTaggerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["pattern_only"] == 1
    assert result.data["llm_fallback"] == 0
    llm.complete.assert_not_called()


# ── Agent: low pattern hits + high weight → LLM fallback ─────────────────────

@pytest.mark.asyncio
async def test_llm_fallback_for_high_weight_low_pattern_mention() -> None:
    m = _pending_mention(
        body="The beneficiaries are facing unexplained delays with their documents.",
        source_weight=0.9,
    )
    db = _make_db([m])
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=_THEME_LLM_JSON)
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.theme_tagger.PromptRegistry") as MockReg:
        MockReg.return_value.get = AsyncMock(
            return_value="THEME_TAXONOMY_JSON MENTION_TEXT SCHEME_NAME DISTRICT_NAME DETECTED_LANGUAGE"
        )
        result = await ThemeTaggerAgent().run(ctx)

    assert result.status == "success"
    assert result.data["llm_fallback"] == 1
    llm.complete.assert_called_once()


# ── Agent: low weight + low pattern → no LLM ─────────────────────────────────

@pytest.mark.asyncio
async def test_no_llm_for_low_weight_mention() -> None:
    m = _pending_mention(
        body="Unexplained document delays for beneficiaries.",
        source_weight=0.3,
    )
    db = _make_db([m])
    llm = MagicMock()
    llm.complete = AsyncMock()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={},
        config={}, db=db, llm=llm,
    )

    with patch("agents.sentiment.theme_tagger.PromptRegistry"):
        result = await ThemeTaggerAgent().run(ctx)

    assert result.status == "success"
    llm.complete.assert_not_called()


# ── Agent: empty taxonomy → warning, no crash ────────────────────────────────

@pytest.mark.asyncio
async def test_empty_taxonomy_returns_success_with_warning() -> None:
    db = _make_db([], taxonomy=[])
    result = await ThemeTaggerAgent().run(_make_ctx(db))
    assert result.status == "success"
    assert result.data.get("warning") == "taxonomy_empty"
