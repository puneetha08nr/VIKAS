"""Unit tests for ThreatAssessorAgent."""
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.competitor.threat_assessor  # noqa: F401

from agents.competitor.threat_assessor import ThreatAssessorAgent, _depth_score
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_KEYWORDS = [("ai marketing",), ("seo automation",), ("content strategy",)]

_CONTENT = [
    # id, url, word_count, body
    ("cc-1", "https://comp.com/ai", 2500,
     "We use AI marketing and seo automation to dominate the market."),
    ("cc-2", "https://comp.com/seo", 800,
     "Our content strategy drives organic growth."),
    ("cc-3", "https://comp.com/other", 300,
     "Completely unrelated plumbing guide."),
]


def _row(*values: object) -> MagicMock:
    row = MagicMock()
    row.__getitem__ = lambda self, i: values[i]
    return row


def _make_db(kw_rows=None, content_rows=None) -> AsyncMock:
    kw_rows = [_row(kw) for (kw,) in (_KEYWORDS if kw_rows is None else kw_rows)]
    content_rows = [_row(*c) for c in (_CONTENT if content_rows is None else content_rows)]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "FROM keywords" in sql:
            result.fetchall.return_value = kw_rows
        elif "FROM competitor_content" in sql and "SELECT id" in sql:
            result.fetchall.return_value = content_rows
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    return db


def _ctx(db: AsyncMock) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )


# ── depth_score formula ───────────────────────────────────────────────────────

def test_depth_score_over_2000() -> None:
    assert _depth_score(2001) == 10.0


def test_depth_score_over_1000() -> None:
    assert _depth_score(1500) == 7.0


def test_depth_score_over_500() -> None:
    assert _depth_score(700) == 4.0


def test_depth_score_500_or_below() -> None:
    assert _depth_score(500) == 2.0
    assert _depth_score(0) == 2.0


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status() -> None:
    db = _make_db()
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.status == "success"


async def test_scores_all_content_rows() -> None:
    db = _make_db()
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.data["total_scored"] == 3


async def test_keywords_used_count() -> None:
    db = _make_db()
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.data["keywords_used"] == 3


async def test_threat_score_formula_high_overlap_deep_content() -> None:
    # cc-1: word_count=2500→depth=10, matches "ai marketing"+"seo automation"=2→overlap=2
    # threat = (2 * 0.6) + (10 * 0.4) = 1.2 + 4.0 = 5.2
    db = _make_db(content_rows=[("cc-1", "u", 2500, "ai marketing and seo automation")])
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.data["avg_threat_score"] == pytest.approx(5.2, abs=0.01)


async def test_threat_score_formula_no_overlap_thin_content() -> None:
    # word_count=200→depth=2, 0 keyword matches→overlap=0
    # threat = (0 * 0.6) + (2 * 0.4) = 0.8
    db = _make_db(content_rows=[("cc-1", "u", 200, "plumbing and roofing")])
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.data["avg_threat_score"] == pytest.approx(0.8, abs=0.01)


async def test_keyword_overlap_capped_at_10() -> None:
    # 15 keyword matches should still give overlap_score = 10 (cap)
    many_keywords = [(f"keyword {i}",) for i in range(15)]
    body = " ".join(f"keyword {i}" for i in range(15))
    db = _make_db(
        kw_rows=many_keywords,
        content_rows=[("cc-1", "u", 2500, body)],
    )
    result = await ThreatAssessorAgent().run(_ctx(db))
    # threat = (10 * 0.6) + (10 * 0.4) = 10.0
    assert result.data["avg_threat_score"] == pytest.approx(10.0, abs=0.01)


async def test_match_is_case_insensitive() -> None:
    # "AI MARKETING" in body should match "ai marketing" keyword
    db = _make_db(content_rows=[("cc-1", "u", 600, "AI MARKETING IS GREAT")])
    result = await ThreatAssessorAgent().run(_ctx(db))
    # overlap=1→score=1, depth(600)=4, threat=(1*0.6)+(4*0.4)=0.6+1.6=2.2
    assert result.data["avg_threat_score"] == pytest.approx(2.2, abs=0.01)


# ── DB writes ─────────────────────────────────────────────────────────────────

async def test_update_written_for_every_row() -> None:
    db = _make_db()
    await ThreatAssessorAgent().run(_ctx(db))
    updates = [
        c for c in db.execute.call_args_list
        if "UPDATE competitor_content" in str(c[0][0])
    ]
    assert len(updates) == 3


async def test_update_uses_correct_content_id() -> None:
    db = _make_db(content_rows=[("cc-42", "u", 100, "ai marketing")])
    await ThreatAssessorAgent().run(_ctx(db))
    updates = [
        c for c in db.execute.call_args_list
        if "UPDATE competitor_content" in str(c[0][0])
    ]
    assert updates[0][0][1]["id"] == "cc-42"


async def test_flush_called() -> None:
    db = _make_db()
    await ThreatAssessorAgent().run(_ctx(db))
    assert db.flush.called


# ── Edge cases ────────────────────────────────────────────────────────────────

async def test_no_unscored_content_returns_success() -> None:
    db = _make_db(content_rows=[])
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["total_scored"] == 0
    assert "message" in result.data


async def test_no_validated_keywords_gives_zero_overlap() -> None:
    # No keywords → all overlap scores = 0; depth still computed from word_count
    db = _make_db(
        kw_rows=[],
        content_rows=[("cc-1", "u", 1200, "some content here")],
    )
    result = await ThreatAssessorAgent().run(_ctx(db))
    # threat = (0 * 0.6) + (7 * 0.4) = 2.8
    assert result.data["avg_threat_score"] == pytest.approx(2.8, abs=0.01)


async def test_tokens_zero_no_llm() -> None:
    db = _make_db()
    result = await ThreatAssessorAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0
