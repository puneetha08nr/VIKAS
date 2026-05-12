"""sentiment.sentiment_filter — Stage 2 filtering, dedup, language detection.

Reads 'pending' raw_mentions and writes to relevant_mentions.
No LLM. All processing is deterministic.

Pipeline per mention:
  1. Normalize body (strip HTML, collapse whitespace)
  2. Detect language (langdetect; ta/en/mixed/unknown)
  3. Relevance check — keyword match for scheme_key / district_key
  4. Deduplication — content hash against recent relevant_mentions
  5. Source weight lookup from source_credibility table (default 1.0)
  6. VADER pre-screen (English only; sets vader_score, vader_confidence)
  7. Write relevant_mention (status='pending_analysis')
  8. Update raw_mention status → filtered_in / filtered_out / duplicate

Input params:
  scheme_key   (str, default "") — filter pending by scheme; "" = all pending
  district_key (str, default "")
  batch_size   (int, default 100) — max mentions to process per run
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any

from bs4 import BeautifulSoup
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.agent_base import AgentContext, AgentResult, BaseAgent
from core.agent_registry import register

logger = logging.getLogger(__name__)

_MIN_BODY_LEN = 20   # discard mentions shorter than this after normalization
_DEDUP_WINDOW_HOURS = 48


@register
class SentimentFilterAgent(BaseAgent):
    name = "sentiment_filter"
    tier = "fast"

    async def execute(self, ctx: AgentContext) -> AgentResult:
        scheme_key: str = ctx.params.get("scheme_key", "")
        district_key: str = ctx.params.get("district_key", "")
        batch_size: int = int(ctx.params.get("batch_size", 100))

        pending = await _fetch_pending(
            scheme_key=scheme_key,
            org_id=ctx.org_id,
            db=ctx.db,
            limit=batch_size,
        )

        stats = {"filtered_in": 0, "filtered_out": 0, "duplicate": 0, "error": 0}

        for raw in pending:
            try:
                outcome = await _process_one(
                    raw=raw,
                    scheme_key=scheme_key,
                    district_key=district_key,
                    org_id=ctx.org_id,
                    db=ctx.db,
                )
                stats[outcome] = stats.get(outcome, 0) + 1
            except Exception as exc:
                logger.warning(
                    "sentiment_filter: error on mention %s — %s",
                    raw.get("id"), exc,
                )
                stats["error"] += 1

        logger.info(
            "sentiment_filter: processed=%d in=%d out=%d dup=%d err=%d scheme=%s",
            len(pending),
            stats["filtered_in"], stats["filtered_out"],
            stats["duplicate"], stats["error"],
            scheme_key or "(all)",
        )
        return AgentResult(
            status="success",
            data={
                "processed": len(pending),
                **stats,
                "scheme_key": scheme_key,
                "district_key": district_key,
            },
        )


# ── Per-mention processing ────────────────────────────────────────────────────

async def _process_one(
    raw: dict[str, Any],
    scheme_key: str,
    district_key: str,
    org_id: str,
    db: AsyncSession,
) -> str:
    """Process one raw_mention. Returns outcome: filtered_in | filtered_out | duplicate."""
    raw_id = str(raw["id"])

    # 1. Normalize text
    body_clean = _normalize(str(raw.get("body") or ""))
    title = _normalize(str(raw.get("title") or ""))
    combined = f"{title} {body_clean}".strip()

    if len(body_clean) < _MIN_BODY_LEN:
        await _set_raw_status(raw_id, "filtered_out", db)
        return "filtered_out"

    # 2. Language detection
    lang, lang_confidence = _detect_language(combined)

    # 3. Relevance check
    hint_schemes: list[str] = raw.get("scheme_hint") or []
    hint_districts: list[str] = raw.get("district_hint") or []
    matched_scheme = scheme_key or (hint_schemes[0] if hint_schemes else "")
    matched_district = district_key or (hint_districts[0] if hint_districts else "")

    if not _is_relevant(combined, matched_scheme, matched_district):
        await _set_raw_status(raw_id, "filtered_out", db)
        return "filtered_out"

    # 4. Deduplication
    content_hash = _content_hash(combined)
    if await _is_duplicate(content_hash, matched_scheme, org_id, db):
        await _set_raw_status(raw_id, "duplicate", db)
        return "duplicate"

    # 5. Source weight
    source_identifier = str(raw.get("source_identifier") or "")
    source_weight = await _get_source_weight(source_identifier, org_id, db)

    # 6. VADER (English only)
    vader_score, vader_confidence = _vader(body_clean) if lang == "en" else (None, None)

    # 7. MinHash signature (for future LSH; stored alongside content_hash)
    minhash_sig = _compute_minhash(combined)
    signature = json.dumps({"content_hash": content_hash, "bands": minhash_sig})

    # 8. Write relevant_mention
    await _insert_relevant(
        raw=raw,
        body_clean=body_clean,
        lang=lang,
        lang_confidence=lang_confidence,
        matched_scheme=matched_scheme,
        matched_district=matched_district,
        source_weight=source_weight,
        vader_score=vader_score,
        vader_confidence=vader_confidence,
        minhash_signature=signature,
        org_id=org_id,
        db=db,
    )

    # 9. Update raw status
    await _set_raw_status(raw_id, "filtered_in", db)
    return "filtered_in"


# ── Text processing ───────────────────────────────────────────────────────────

def _normalize(raw: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    try:
        text = BeautifulSoup(raw, "lxml").get_text(separator=" ")
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", text).strip()


def _detect_language(text: str) -> tuple[str, float]:
    """Return (lang_code, confidence). Falls back to 'unknown' on failure."""
    if not text or len(text) < 10:
        return "unknown", 0.0
    try:
        from langdetect import detect_langs  # type: ignore[import-untyped]
        results = detect_langs(text[:500])
        if not results:
            return "unknown", 0.0
        top = results[0]
        lang = top.lang
        confidence = round(float(top.prob), 4)
        # Map Tamil and related scripts
        if lang in ("ta",):
            return "ta", confidence
        if lang in ("en",):
            return "en", confidence
        # Tanglish / mixed often detected as other lang codes with low confidence
        if confidence < 0.7 and any(r.lang in ("ta", "en") for r in results):
            return "mixed", confidence
        return lang, confidence
    except Exception:
        return "unknown", 0.0


def _is_relevant(text: str, scheme_key: str, district_key: str) -> bool:
    """True if text mentions the scheme or district (case-insensitive keyword match)."""
    lower = text.lower()
    if scheme_key and any(w.lower() in lower for w in scheme_key.split() if len(w) > 3):
        return True
    if district_key and district_key.lower() in lower:
        return True
    return not scheme_key and not district_key  # no filter → always relevant


def _content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.lower().strip())[:300]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _compute_minhash(text: str, num_perm: int = 64) -> list[int]:
    """Compute MinHash signature (num_perm hash values) using 3-char shingles."""
    try:
        from datasketch import MinHash  # type: ignore[import-untyped]
        m = MinHash(num_perm=num_perm)
        words = text.lower().split()
        for i in range(max(1, len(words) - 2)):
            shingle = " ".join(words[i: i + 3])
            m.update(shingle.encode("utf-8"))
        return [int(v) for v in m.hashvalues]
    except Exception:
        return []


def _vader(text: str) -> tuple[float | None, float | None]:
    """VADER compound score and derived confidence. English only."""
    try:
        from vaderSentiment.vaderSentiment import (  # pyright: ignore[reportMissingImports]
            SentimentIntensityAnalyzer,  # type: ignore[import-untyped]
        )
        sia = SentimentIntensityAnalyzer()
        scores = sia.polarity_scores(text[:2000])
        compound = round(float(scores["compound"]), 4)
        confidence = round(min(1.0, abs(compound) * 1.5 + 0.2), 4)
        return compound, confidence
    except Exception:
        return None, None


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _fetch_pending(
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
    limit: int,
) -> list[dict[str, Any]]:
    result = await db.execute(
        text("""
            SELECT id, org_id, source, source_identifier, external_id,
                   url, title, body, author, published_at,
                   engagement_raw, scheme_hint, district_hint
            FROM raw_mentions
            WHERE org_id = :org_id
              AND status = 'pending'
              AND (:scheme_key = '' OR scheme_hint ? :scheme_key)
            ORDER BY collected_at ASC
            LIMIT :limit
        """),
        {"org_id": org_id, "scheme_key": scheme_key, "limit": limit},
    )
    return [dict(row._mapping) for row in result.fetchall()]


async def _is_duplicate(
    content_hash: str,
    scheme_key: str,
    org_id: str,
    db: AsyncSession,
) -> bool:
    result = await db.execute(
        text("""
            SELECT 1 FROM relevant_mentions
            WHERE org_id = :org_id
              AND matched_scheme = :scheme_key
              AND minhash_signature->>'content_hash' = :hash
              AND created_at > now() - make_interval(hours => :window)
            LIMIT 1
        """),
        {
            "org_id": org_id,
            "scheme_key": scheme_key,
            "hash": content_hash,
            "window": _DEDUP_WINDOW_HOURS,
        },
    )
    return result.fetchone() is not None


async def _get_source_weight(
    source_identifier: str,
    org_id: str,
    db: AsyncSession,
) -> float:
    if not source_identifier:
        return 1.0
    result = await db.execute(
        text("""
            SELECT credibility_weight * reach_weight
            FROM source_credibility
            WHERE org_id = :org_id AND source_identifier = :src
            LIMIT 1
        """),
        {"org_id": org_id, "src": source_identifier},
    )
    row = result.fetchone()
    return float(row[0]) if row and row[0] is not None else 1.0


async def _insert_relevant(
    raw: dict[str, Any],
    body_clean: str,
    lang: str,
    lang_confidence: float,
    matched_scheme: str,
    matched_district: str,
    source_weight: float,
    vader_score: float | None,
    vader_confidence: float | None,
    minhash_signature: str,
    org_id: str,
    db: AsyncSession,
) -> None:
    published_at: datetime | None = raw.get("published_at")
    await db.execute(
        text("""
            INSERT INTO relevant_mentions (
                id, org_id, raw_mention_id, source, source_identifier,
                url, title, body_clean,
                language, language_confidence,
                matched_scheme, matched_district,
                published_at, source_weight,
                vader_score, vader_confidence,
                minhash_signature, status, created_at
            ) VALUES (
                gen_random_uuid(), :org_id, :raw_id, :source, :source_identifier,
                :url, :title, :body_clean,
                :language, :lang_confidence,
                :matched_scheme, :matched_district,
                :published_at, :source_weight,
                :vader_score, :vader_confidence,
                CAST(:minhash AS jsonb), 'pending_analysis', now()
            )
            ON CONFLICT DO NOTHING
        """),
        {
            "org_id": org_id,
            "raw_id": str(raw["id"]),
            "source": str(raw.get("source") or ""),
            "source_identifier": str(raw.get("source_identifier") or ""),
            "url": str(raw.get("url") or ""),
            "title": str(raw.get("title") or "")[:2000],
            "body_clean": body_clean[:10000],
            "language": lang,
            "lang_confidence": lang_confidence,
            "matched_scheme": matched_scheme,
            "matched_district": matched_district,
            "published_at": published_at,
            "source_weight": source_weight,
            "vader_score": vader_score,
            "vader_confidence": vader_confidence,
            "minhash": minhash_signature,
        },
    )
    await db.flush()


async def _set_raw_status(mention_id: str, status: str, db: AsyncSession) -> None:
    await db.execute(
        text("UPDATE raw_mentions SET status = :status WHERE id = :id"),
        {"status": status, "id": mention_id},
    )
