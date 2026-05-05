"""Unit tests for PreferenceLearnerAgent."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.ops.preference_learner  # noqa: F401

from agents.ops.preference_learner import PreferenceLearnerAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"


def _fb_row(
    row_id: str | None = None,
    content_type: str = "article",
    action: str = "approved",
    notes: str | None = None,
) -> MagicMock:
    row_id = row_id or str(uuid.uuid4())
    r = MagicMock()
    r.__getitem__ = lambda self, i: (row_id, content_type, action, notes)[i]
    return r


def _make_db(feedback_rows: list | None = None) -> AsyncMock:
    rows = feedback_rows if feedback_rows is not None else []

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "content_feedback" in sql and "processed = false" in sql:
            result.fetchall.return_value = rows
        else:
            result.fetchall.return_value = []
            result.rowcount = len(rows)
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={},
        config={},
        db=db,
        llm=MagicMock(),
    )


# ── No feedback ───────────────────────────────────────────────────────────────

async def test_no_feedback_returns_success() -> None:
    db = _make_db([])
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.status == "success"


async def test_no_feedback_returns_zero_counts() -> None:
    db = _make_db([])
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.data["content_types_processed"] == 0
    assert result.data["preferences_written"] == 0
    assert result.data["feedback_rows_processed"] == 0


async def test_no_feedback_has_message() -> None:
    db = _make_db([])
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert "message" in result.data


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_success_status_with_feedback() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="approved"),
        _fb_row(action="rejected", notes="too generic"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.status == "success"


async def test_content_types_processed_count() -> None:
    rows = [
        _fb_row(content_type="article", action="approved"),
        _fb_row(content_type="linkedin", action="rejected"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.data["content_types_processed"] == 2


async def test_feedback_rows_processed_count() -> None:
    rows = [_fb_row(action="approved") for _ in range(5)]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.data["feedback_rows_processed"] == 5


async def test_zero_tokens_no_llm() -> None:
    db = _make_db([_fb_row(action="approved")])
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Rate calculations ─────────────────────────────────────────────────────────

async def test_approval_rate_calculated_correctly() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="approved"),
        _fb_row(action="approved"),
        _fb_row(action="rejected"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    summary = result.data["summaries"][0]
    assert summary["approval_rate"] == pytest.approx(0.75, abs=0.01)


async def test_rejection_rate_calculated_correctly() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="rejected"),
        _fb_row(action="rejected"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    summary = result.data["summaries"][0]
    assert summary["rejection_rate"] == pytest.approx(0.6667, abs=0.001)


async def test_edit_rate_calculated_correctly() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="edited", notes="shorten intro"),
        _fb_row(action="edited", notes="fix cta"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    summary = result.data["summaries"][0]
    assert summary["edit_rate"] == pytest.approx(0.6667, abs=0.001)


async def test_rates_sum_to_one() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="edited"),
        _fb_row(action="rejected"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    s = result.data["summaries"][0]
    total = s["approval_rate"] + s["edit_rate"] + s["rejection_rate"]
    assert total == pytest.approx(1.0, abs=0.001)


# ── DB writes ─────────────────────────────────────────────────────────────────

async def test_three_preference_keys_written_per_content_type() -> None:
    """Each content_type produces 3 keys: approval_stats, edit_themes, rejected_patterns."""
    rows = [_fb_row(content_type="article", action="approved")]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.data["preferences_written"] == 3


async def test_two_content_types_write_six_keys() -> None:
    rows = [
        _fb_row(content_type="article", action="approved"),
        _fb_row(content_type="linkedin", action="rejected"),
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert result.data["preferences_written"] == 6


async def test_upsert_insert_called_for_each_preference_key() -> None:
    rows = [_fb_row(content_type="article", action="approved")]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    upserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO preference_summaries" in str(c[0][0])
    ]
    assert len(upserts) == result.data["preferences_written"]


async def test_mark_processed_called_with_correct_ids() -> None:
    row_id = str(uuid.uuid4())
    rows = [_fb_row(row_id=row_id, action="approved")]
    db = _make_db(rows)
    await PreferenceLearnerAgent().run(_ctx(db))
    update_calls = [
        c for c in db.execute.call_args_list
        if "UPDATE content_feedback" in str(c[0][0]) and "processed = true" in str(c[0][0])
    ]
    assert len(update_calls) == 1
    assert row_id in str(update_calls[0][0][1]["ids"])


async def test_flush_called_after_writes() -> None:
    rows = [_fb_row(action="approved")]
    db = _make_db(rows)
    await PreferenceLearnerAgent().run(_ctx(db))
    assert db.flush.call_count >= 1


# ── Edit themes and rejected patterns captured ────────────────────────────────

async def test_edit_notes_included_in_edit_themes_key() -> None:
    rows = [
        _fb_row(action="edited", notes="shorten the intro"),
        _fb_row(action="edited", notes="add a CTA"),
    ]
    db = _make_db(rows)
    await PreferenceLearnerAgent().run(_ctx(db))
    upserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO preference_summaries" in str(c[0][0])
        and "edit_themes" in str(c[0][1].get("key", ""))
    ]
    assert len(upserts) == 1
    import json
    value = json.loads(upserts[0][0][1]["value"])
    assert "shorten the intro" in value["notes"]
    assert "add a CTA" in value["notes"]


async def test_rejected_notes_included_in_rejected_patterns_key() -> None:
    rows = [_fb_row(action="rejected", notes="off-brand tone")]
    db = _make_db(rows)
    await PreferenceLearnerAgent().run(_ctx(db))
    upserts = [
        c for c in db.execute.call_args_list
        if "INSERT INTO preference_summaries" in str(c[0][0])
        and "rejected_patterns" in str(c[0][1].get("key", ""))
    ]
    import json
    value = json.loads(upserts[0][0][1]["value"])
    assert "off-brand tone" in value["notes"]


# ── Invalid action rows skipped ───────────────────────────────────────────────

async def test_unknown_action_row_skipped() -> None:
    rows = [
        _fb_row(action="approved"),
        _fb_row(action="unknown_action"),  # invalid — should be skipped
    ]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    # Only the valid row is processed
    assert result.data["feedback_rows_processed"] == 1


async def test_summaries_list_in_result() -> None:
    rows = [_fb_row(action="approved")]
    db = _make_db(rows)
    result = await PreferenceLearnerAgent().run(_ctx(db))
    assert "summaries" in result.data
    assert isinstance(result.data["summaries"], list)
    assert len(result.data["summaries"]) == 1
