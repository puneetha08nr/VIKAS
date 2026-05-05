"""Unit tests for InternalLinkFinderAgent."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.knowledge.internal_link_finder  # noqa: F401

from agents.knowledge.internal_link_finder import InternalLinkFinderAgent
from core.agent_base import AgentContext

ORG_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000099"

_FAKE_EMBEDDING: list[float] = [0.0] * 1536

# Published content rows: (id, title, published_url)
_PUBLISHED_ROWS = [
    (str(uuid.uuid4()), "AI Marketing Automation Guide", "https://example.com/ai-marketing"),
    (str(uuid.uuid4()), "SEO Best Practices for 2024", "https://example.com/seo-guide"),
    (str(uuid.uuid4()), "Content Strategy for B2B", "https://example.com/b2b-content"),
]

# RAG chunk rows: (id, chunk_text, source_doc, score)
_CHUNK_ROWS = [
    (str(uuid.uuid4()), "AI tools automate repetitive marketing.", "blog/ai-marketing.md", 0.91),
    (str(uuid.uuid4()), "Automation in SEO reduces manual work.", "blog/seo-guide.md", 0.82),
]


def _pub_row(row_id: str, title: str, url: str) -> MagicMock:
    r = MagicMock()
    r.__getitem__ = lambda self, i: (row_id, title, url)[i]
    return r


def _chunk_row(chunk_id: str, text: str, source: str, score: float) -> MagicMock:
    r = MagicMock()
    r.__getitem__ = lambda self, i: (chunk_id, text, source, score)[i]
    return r


def _make_db(
    published: list | None = None,
    chunks: list | None = None,
) -> AsyncMock:
    pub_rows = [_pub_row(*r) for r in (_PUBLISHED_ROWS if published is None else published)]
    rag_rows = [_chunk_row(*r) for r in (_CHUNK_ROWS if chunks is None else chunks)]

    def _side(query, params=None):
        sql = str(query)
        result = MagicMock()
        if "knowledge_chunks" in sql:
            result.fetchall.return_value = rag_rows
        elif "content_items" in sql:
            result.fetchall.return_value = pub_rows
        else:
            result.fetchall.return_value = []
            result.fetchone.return_value = None
        return result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _ctx(db: AsyncMock, params: dict | None = None) -> AgentContext:
    return AgentContext(
        org_id=ORG_ID,
        run_id=RUN_ID,
        params={"query": "ai marketing automation", **(params or {})},
        config={},
        db=db,
        llm=MagicMock(),
    )


def _patch_embed(embedding: list[float] | None = None):
    vec = embedding if embedding is not None else _FAKE_EMBEDDING
    return patch(
        "agents.knowledge.internal_link_finder.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(return_value=vec)},
    )


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_successful_run_returns_success_status() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.status == "success"


async def test_returns_links_list() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert "links" in result.data
    assert isinstance(result.data["links"], list)


async def test_query_echoed_in_result() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.data["query"] == "ai marketing automation"


async def test_link_fields_present() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    link = result.data["links"][0]
    assert "url" in link
    assert "title" in link
    assert "anchor_text" in link
    assert "similarity_score" in link


async def test_links_sorted_by_score_descending() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    scores = [lnk["similarity_score"] for lnk in result.data["links"]]
    assert scores == sorted(scores, reverse=True)


async def test_top_k_limits_results() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db, {"query": "ai", "top_k": 2}))
    assert len(result.data["links"]) <= 2


async def test_total_found_matches_links_length() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.data["total_found"] == len(result.data["links"])


# ── Keyword scoring ────────────────────────────────────────────────────────────

async def test_keyword_overlap_boosts_score() -> None:
    """A title that shares words with the query should score higher than one that doesn't."""
    published = [
        (str(uuid.uuid4()), "AI Marketing Automation Guide", "https://example.com/ai"),
        (str(uuid.uuid4()), "Unrelated Finance Topic", "https://example.com/finance"),
    ]
    db = _make_db(published=published, chunks=[])
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    links = result.data["links"]
    ai_link = next(lnk for lnk in links if "AI" in lnk["title"])
    finance_link = next(lnk for lnk in links if "Finance" in lnk["title"])
    assert ai_link["similarity_score"] > finance_link["similarity_score"]


async def test_zero_score_for_no_overlap() -> None:
    """A title with no query words and no rag match should score 0."""
    published = [
        (str(uuid.uuid4()), "Finance and Accounting Tips", "https://example.com/finance"),
    ]
    db = _make_db(published=published, chunks=[])
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.data["links"][0]["similarity_score"] == 0.0


# ── RAG boost ─────────────────────────────────────────────────────────────────

async def test_rag_boost_applied_when_source_matches_title() -> None:
    """When a chunk's source_doc contains a title word, rag_boost (0.2) is added."""
    # Title word "marketing" appears in source_doc "blog/ai-marketing.md"
    published = [
        (str(uuid.uuid4()), "Marketing Strategy", "https://example.com/marketing"),
    ]
    chunks = [
        (str(uuid.uuid4()), "Some chunk text", "blog/ai-marketing.md", 0.9),
    ]
    db = _make_db(published=published, chunks=chunks)
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    # keyword overlap is 0 (query="ai marketing automation", title words "marketing"/"strategy")
    # rag_boost = 0.2 because "marketing" in "blog/ai-marketing.md"
    score = result.data["links"][0]["similarity_score"]
    assert score >= 0.2


async def test_no_rag_boost_when_no_source_match() -> None:
    """rag_boost not applied when source_doc doesn't contain any title word."""
    published = [
        (str(uuid.uuid4()), "Finance Strategy", "https://example.com/finance"),
    ]
    chunks = [
        (str(uuid.uuid4()), "chunk", "blog/ai-marketing.md", 0.9),
    ]
    db = _make_db(published=published, chunks=chunks)
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    score = result.data["links"][0]["similarity_score"]
    # "finance" and "strategy" not in "blog/ai-marketing.md" → no boost
    assert score == 0.0


async def test_score_capped_at_1_0() -> None:
    """similarity_score never exceeds 1.0 even when both signals fire."""
    # All query words match the title AND rag_boost fires → would exceed 1.0 without cap
    published = [
        (str(uuid.uuid4()), "AI Marketing Automation", "https://example.com/ai"),
    ]
    chunks = [
        (str(uuid.uuid4()), "chunk", "blog/ai-marketing.md", 0.9),
    ]
    db = _make_db(published=published, chunks=chunks)
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    score = result.data["links"][0]["similarity_score"]
    assert score <= 1.0


# ── Embedding failure → keyword-only fallback ─────────────────────────────────

async def test_embedding_failure_still_returns_success() -> None:
    db = _make_db()
    with patch(
        "agents.knowledge.internal_link_finder.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("No API key"))},
    ):
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.status == "success"


async def test_embedding_failure_keyword_scoring_still_works() -> None:
    """When embedding fails, keyword-only scoring still returns relevant links."""
    db = _make_db()
    with patch(
        "agents.knowledge.internal_link_finder.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("timeout"))},
    ):
        result = await InternalLinkFinderAgent().run(_ctx(db))
    links = result.data["links"]
    assert len(links) > 0
    # AI Marketing link should score higher than unrelated ones
    ai_link = next((lnk for lnk in links if "AI" in lnk.get("title", "")), None)
    assert ai_link is not None
    assert ai_link["similarity_score"] > 0.0


async def test_embedding_failure_no_rag_boost() -> None:
    """When embedding fails, rag_sources is empty, so no rag_boost is applied."""
    published = [
        (str(uuid.uuid4()), "Marketing Strategy", "https://example.com/marketing"),
    ]
    db = _make_db(published=published)
    with patch(
        "agents.knowledge.internal_link_finder.EmbeddingGenerator",
        **{"return_value.generate_one": AsyncMock(side_effect=Exception("timeout"))},
    ):
        result = await InternalLinkFinderAgent().run(_ctx(db))
    # Without rag_boost, score = keyword_overlap only
    # query="ai marketing automation" → query_words filtered >2 chars = {"marketing", "automation"}
    # title "Marketing Strategy": "marketing" matches, "automation" does not → 1/2 = 0.5
    score = result.data["links"][0]["similarity_score"]
    assert score == pytest.approx(0.5, abs=0.01)


# ── Edge cases ────────────────────────────────────────────────────────────────

async def test_no_published_content_returns_empty_links() -> None:
    db = _make_db(published=[])
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.status == "success"
    assert result.data["links"] == []
    assert result.data["total_found"] == 0


async def test_missing_query_returns_failed() -> None:
    db = _make_db()
    ctx = AgentContext(
        org_id=ORG_ID, run_id=RUN_ID, params={}, config={}, db=db, llm=MagicMock()
    )
    result = await InternalLinkFinderAgent().run(ctx)
    assert result.status == "failed"
    assert "query" in (result.error or "")


async def test_zero_tokens_no_llm() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


async def test_anchor_text_defaults_to_title() -> None:
    db = _make_db()
    with _patch_embed():
        result = await InternalLinkFinderAgent().run(_ctx(db))
    for link in result.data["links"]:
        assert link["anchor_text"] == link["title"]
