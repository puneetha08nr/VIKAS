"""topic_discovery — surfaces fresh content topics from free public sources.

Three signal sources, all free, no API keys required:

  1. PyTrends — related queries (top + rising) for the seed keyword.
  2. Google Suggest — autocomplete for the seed and 7 letter-prefixed variants.
  3. Reddit — top post titles from public hot-search JSON (no auth).

Scoring (fixed by source):
  pytrends_rising  → 8.0
  pytrends_top     → 6.0
  google_suggest   → 5.0
  reddit           → 4.0

Topics are deduped by lowercased string before writing. Each source fails
gracefully — if PyTrends rate-limits or Reddit is slow, the other sources
still write results.

Input params:
  seed_keyword  (str)  — topic seed, required
  max_topics    (int)  — cap on rows written per run (default 30)
"""
import asyncio
import json
import logging
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register
from core.contracts import TopicDiscoveryOutput

logger = logging.getLogger(__name__)

_DEFAULT_MAX = 30
_SCORE_MAP = {
    "pytrends_rising": 8.0,
    "pytrends_top": 6.0,
    "google_suggest": 5.0,
    "reddit": 4.0,
}


@register
class TopicDiscoveryAgent(BaseAgent):
    name = "topic_discovery"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        seed = str(ctx.params.get("seed_keyword", "")).strip()
        if not seed:
            return AgentResult(status="failed", error="seed_keyword param is required")

        max_topics = max(1, int(ctx.params.get("max_topics", _DEFAULT_MAX)))

        raw_topics: list[dict[str, Any]] = []

        # ── Source 1: PyTrends ────────────────────────────────────────────────
        try:
            loop = asyncio.get_running_loop()
            pytrends_results = await loop.run_in_executor(
                None, _fetch_pytrends_sync, seed
            )
            raw_topics.extend(pytrends_results)
        except Exception as exc:
            logger.warning("topic_discovery: pytrends failed, skipping: %s", exc)

        # ── Source 2: Google Suggest ──────────────────────────────────────────
        try:
            suggestions = await _fetch_google_suggest(seed)
            for s in suggestions:
                raw_topics.append({"topic": s, "source": "google_suggest"})
        except Exception as exc:
            logger.warning("topic_discovery: google_suggest failed, skipping: %s", exc)

        # ── Source 3: Reddit ──────────────────────────────────────────────────
        try:
            reddit_topics = await _fetch_reddit(seed)
            raw_topics.extend(reddit_topics)
        except Exception as exc:
            logger.warning("topic_discovery: reddit failed, skipping: %s", exc)

        if not raw_topics:
            return AgentResult(
                status="success",
                data={"topics_written": 0, "seed_keyword": seed, "message": "All sources failed"},
            )

        # ── Deduplicate + validate ────────────────────────────────────────────
        seen: set[str] = set()
        validated: list[TopicDiscoveryOutput] = []

        for raw in raw_topics:
            key = str(raw.get("topic", "")).lower().strip()
            if not key or key == seed.lower() or key in seen:
                continue
            seen.add(key)

            source = str(raw.get("source", "google_suggest"))
            raw["score"] = _SCORE_MAP.get(source, 4.0)

            try:
                validated.append(TopicDiscoveryOutput(**raw))
            except ValidationError as exc:
                logger.warning("topic_discovery: invalid row skipped: %s", exc)

        validated = validated[:max_topics]
        written = await _save_topics(validated, ctx.org_id, ctx.db)

        return AgentResult(
            status="success",
            data={"topics_written": written, "seed_keyword": seed},
        )


# ── PyTrends (sync — runs in thread executor) ─────────────────────────────────

def _fetch_pytrends_sync(seed: str) -> list[dict[str, Any]]:
    from pytrends.request import TrendReq

    pt = TrendReq(hl="en-US", tz=0)
    pt.build_payload([seed], timeframe="today 3-m")
    related = pt.related_queries()

    results: list[dict[str, Any]] = []
    if not related or seed not in related:
        return results

    data = related[seed]

    for label, source in (("top", "pytrends_top"), ("rising", "pytrends_rising")):
        df = data.get(label)
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            topic = str(row.get("query", "")).strip()
            if topic:
                results.append({"topic": topic, "source": source})

    return results


# ── Google Suggest ────────────────────────────────────────────────────────────

async def _fetch_google_suggest(seed: str) -> list[str]:
    base_url = "https://suggestqueries.google.com/complete/search"
    queries = [seed] + [f"{seed} {c}" for c in "abcdefg"]

    async def _one(client: httpx.AsyncClient, q: str) -> list[str]:
        try:
            r = await client.get(base_url, params={"q": q, "client": "firefox", "hl": "en"})
            r.raise_for_status()
            data = r.json()
            return [s.strip() for s in (data[1] if len(data) > 1 else []) if s.strip()]
        except Exception:
            return []

    async with httpx.AsyncClient(timeout=10) as client:
        batches = await asyncio.gather(*[_one(client, q) for q in queries])

    seen: set[str] = set()
    results: list[str] = []
    for batch in batches:
        for item in batch:
            low = item.lower()
            if low not in seen:
                seen.add(low)
                results.append(item)
    return results


# ── Reddit ────────────────────────────────────────────────────────────────────

async def _fetch_reddit(seed: str) -> list[dict[str, Any]]:
    url = "https://www.reddit.com/r/all/search.json"
    headers = {"User-Agent": "topic_discovery_bot/1.0 (research)"}
    params = {"q": seed, "sort": "hot", "limit": 25, "type": "link"}

    async with httpx.AsyncClient(timeout=10, headers=headers) as client:
        r = await client.get(url, params=params)
        r.raise_for_status()
        data = r.json()

    posts = data.get("data", {}).get("children", [])
    results: list[dict[str, Any]] = []
    for post in posts:
        title = str(post.get("data", {}).get("title", "")).strip()
        if title:
            results.append({"topic": title, "source": "reddit"})
    return results


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _save_topics(
    topics: list[TopicDiscoveryOutput],
    org_id: str,
    db: AsyncSession,
) -> int:
    written = 0
    for t in topics:
        await db.execute(
            text(
                "INSERT INTO topics "
                "  (id, org_id, topic, source, score, related_keywords, detected_at) "
                "VALUES "
                "  (gen_random_uuid(), :org_id, :topic, :source, :score, "
                "   CAST(:keywords AS jsonb), now())"
            ),
            {
                "org_id": org_id,
                "topic": t.topic,
                "source": t.source,
                "score": t.score,
                "keywords": json.dumps(t.related_keywords),
            },
        )
        written += 1

    if written:
        await db.flush()
    return written
