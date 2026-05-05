"""Unit tests for CompetitorMonitorAgent."""
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import agents.competitor.competitor_monitor  # noqa: F401 — triggers @register

from agents.competitor.competitor_monitor import CompetitorMonitorAgent
from core.agent_base import AgentContext, AgentResult
from integrations.base import IntegrationError
from integrations.sitemap import SitemapIntegration, _parse_sitemap_xml

# ── Fixtures ──────────────────────────────────────────────────────────────────

_SAMPLE_URLS = [
    "https://competitor.com/blog/post-1",
    "https://competitor.com/blog/post-2",
    "https://competitor.com/pricing",
]


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_llm() -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock()
    llm.last_tokens_used = 0
    llm.last_cost_usd = 0.0
    return llm


@pytest.fixture
def ctx(mock_db: AsyncMock, mock_llm: MagicMock) -> AgentContext:
    return AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000002",
        params={"competitors": ["competitor1.com", "competitor2.com"]},
        config={},
        db=mock_db,
        llm=mock_llm,
    )


@contextmanager
def _patch_sitemap(urls: list[str] | None = None, error: Exception | None = None):
    """Patch SitemapIntegration.fetch_sitemap on the class."""
    if error is not None:
        mock = AsyncMock(side_effect=error)
    else:
        mock = AsyncMock(return_value=urls if urls is not None else _SAMPLE_URLS)
    with patch.object(SitemapIntegration, "fetch_sitemap", mock):
        yield mock


# ── Happy path ────────────────────────────────────────────────────────────────

async def test_all_domains_reachable_returns_success(ctx: AgentContext) -> None:
    with _patch_sitemap():
        result = await CompetitorMonitorAgent().run(ctx)
    assert result.status == "success"


async def test_competitors_monitored_count_equals_domain_count(ctx: AgentContext) -> None:
    with _patch_sitemap():
        result = await CompetitorMonitorAgent().run(ctx)
    assert result.data["competitors_monitored"] == 2
    assert result.data["total"] == 2


async def test_urls_found_reflects_sitemap_size(ctx: AgentContext) -> None:
    with _patch_sitemap(urls=_SAMPLE_URLS):
        result = await CompetitorMonitorAgent().run(ctx)
    for entry in result.data["results"]:
        assert entry["urls_found"] == len(_SAMPLE_URLS)


async def test_result_contains_one_entry_per_domain(ctx: AgentContext) -> None:
    with _patch_sitemap():
        result = await CompetitorMonitorAgent().run(ctx)
    assert len(result.data["results"]) == 2
    domains = {r["domain"] for r in result.data["results"]}
    assert domains == {"competitor1.com", "competitor2.com"}


async def test_upsert_called_for_each_reachable_domain(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_sitemap():
        await CompetitorMonitorAgent().run(ctx)
    upsert_calls = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO competitors" in str(c.args[0])
    ]
    # One upsert per domain (plus the agent_runs INSERT)
    assert len(upsert_calls) == 2


async def test_agent_run_record_created(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    with _patch_sitemap():
        await CompetitorMonitorAgent().run(ctx)
    run_inserts = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO agent_runs" in str(c.args[0])
    ]
    assert len(run_inserts) == 1


async def test_tokens_used_is_zero_no_llm(ctx: AgentContext) -> None:
    with _patch_sitemap():
        result = await CompetitorMonitorAgent().run(ctx)
    assert result.tokens_used == 0
    assert result.cost_usd == 0.0


# ── Failure / partial ─────────────────────────────────────────────────────────

async def test_all_unreachable_returns_partial(ctx: AgentContext) -> None:
    err = IntegrationError("connection timeout", None, "sitemap")
    with _patch_sitemap(error=err):
        result = await CompetitorMonitorAgent().run(ctx)
    assert result.status == "partial"
    assert result.data["competitors_monitored"] == 0


async def test_unreachable_domain_status_is_unreachable(ctx: AgentContext) -> None:
    err = IntegrationError("404", 404, "sitemap")
    with _patch_sitemap(error=err):
        result = await CompetitorMonitorAgent().run(ctx)
    for entry in result.data["results"]:
        assert entry["status"] == "unreachable"


async def test_unreachable_domain_still_writes_competitor_row(
    ctx: AgentContext, mock_db: AsyncMock
) -> None:
    err = IntegrationError("timeout", None, "sitemap")
    with _patch_sitemap(error=err):
        await CompetitorMonitorAgent().run(ctx)
    insert_calls = [
        c for c in mock_db.execute.call_args_list
        if c.args and "INSERT INTO competitors" in str(c.args[0])
    ]
    # _ensure_competitor inserts with DO NOTHING — one per domain
    assert len(insert_calls) == 2


async def test_partial_failure_returns_partial_status(
    mock_db: AsyncMock, mock_llm: MagicMock
) -> None:
    """First domain succeeds, second fails → partial."""
    err = IntegrationError("timeout", None, "sitemap")
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000003",
        params={"competitors": ["good.com", "bad.com"]},
        config={},
        db=mock_db,
        llm=mock_llm,
    )

    call_count = 0

    async def _side_effect(_self: object, domain: str) -> list[str]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _SAMPLE_URLS
        raise err

    with patch.object(SitemapIntegration, "fetch_sitemap", _side_effect):
        result = await CompetitorMonitorAgent().run(ctx)

    assert result.status == "partial"
    assert result.data["competitors_monitored"] == 1
    assert result.data["results"][0]["status"] == "ok"
    assert result.data["results"][1]["status"] == "unreachable"


# ── Missing / empty params — fallback to DB ───────────────────────────────────

def _db_with_stored_domains(domains: list[str]) -> AsyncMock:
    """DB mock where SELECT domain FROM competitors returns given list."""
    domain_result = MagicMock()
    domain_result.fetchall.return_value = [
        MagicMock(**{"__getitem__": lambda self, i: d}) for d in domains
    ]
    write_result = MagicMock()
    write_result.rowcount = 1

    def _side(query, params=None):
        if "SELECT domain FROM competitors" in str(query):
            return domain_result
        return write_result

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=_side)
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


async def test_no_param_db_empty_returns_success_zero(
    mock_llm: MagicMock,
) -> None:
    """No competitors param AND no stored domains → success with total=0 and a message."""
    db = _db_with_stored_domains([])
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000004",
        params={},
        config={},
        db=db,
        llm=mock_llm,
    )
    result = await CompetitorMonitorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["total"] == 0
    assert "message" in result.data


async def test_no_param_db_has_domains_falls_back_to_db(
    mock_llm: MagicMock,
) -> None:
    """No competitors param but DB has stored domains → agent scrapes them."""
    db = _db_with_stored_domains(["stored-competitor.com"])
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000005",
        params={},
        config={},
        db=db,
        llm=mock_llm,
    )
    with _patch_sitemap(["https://stored-competitor.com/sitemap.xml"]):
        result = await CompetitorMonitorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["total"] == 1


async def test_empty_list_param_falls_back_to_db(
    mock_llm: MagicMock,
) -> None:
    """Explicit empty list for competitors → same fallback as missing param."""
    db = _db_with_stored_domains([])
    ctx = AgentContext(
        org_id="00000000-0000-0000-0000-000000000001",
        run_id="00000000-0000-0000-0000-000000000006",
        params={"competitors": []},
        config={},
        db=db,
        llm=mock_llm,
    )
    result = await CompetitorMonitorAgent().run(ctx)
    assert result.status == "success"
    assert result.data["total"] == 0


# ── _parse_sitemap_xml unit tests ─────────────────────────────────────────────

_URLSET_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/page1</loc></url>
  <url><loc>https://example.com/page2</loc></url>
  <url><loc>https://example.com/page3</loc></url>
</urlset>"""

_SITEMAPINDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>"""

_NO_NS_XML = """<?xml version="1.0"?>
<urlset>
  <url><loc>https://example.com/no-ns-page</loc></url>
</urlset>"""


def test_parse_urlset_returns_page_urls() -> None:
    urls = _parse_sitemap_xml(_URLSET_XML)
    assert len(urls) == 3
    assert "https://example.com/page1" in urls
    assert "https://example.com/page3" in urls


def test_parse_sitemapindex_returns_sub_sitemap_urls() -> None:
    urls = _parse_sitemap_xml(_SITEMAPINDEX_XML)
    assert len(urls) == 2
    assert "https://example.com/sitemap-posts.xml" in urls


def test_parse_no_namespace_xml() -> None:
    urls = _parse_sitemap_xml(_NO_NS_XML)
    assert len(urls) == 1
    assert urls[0] == "https://example.com/no-ns-page"


def test_parse_invalid_xml_returns_empty() -> None:
    assert _parse_sitemap_xml("not xml at all") == []
    assert _parse_sitemap_xml("") == []
    assert _parse_sitemap_xml("<broken>") == []


def test_parse_empty_urlset_returns_empty() -> None:
    xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
    assert _parse_sitemap_xml(xml) == []


def test_parse_strips_whitespace_from_urls() -> None:
    xml = """<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>  https://example.com/page  </loc></url>
</urlset>"""
    urls = _parse_sitemap_xml(xml)
    assert urls == ["https://example.com/page"]
