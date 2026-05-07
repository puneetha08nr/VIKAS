"""Dashboard API routers.

Provides REST endpoints for all dashboard pages that don't have dedicated modules:
  - /opportunities
  - /articles
  - /linkedin-posts
  - /twitter-threads
  - /newsletters
  - /competitors
  - /competitor-content
  - /strategy-reports
  - /rank-tracking
  - /aeo-results
  - /brand-voice
  - /settings/auto-mode
"""
from __future__ import annotations

import asyncio
import re
import socket
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_db_for_org
from db.models.aeo_results import AeoResult
from db.models.brand_voice import BrandVoice
from db.models.competitor_content import CompetitorContent
from db.models.competitors import Competitor
from db.models.opportunities import Opportunity
from db.models.organizations import Organization

router = APIRouter(tags=["dashboard"])


# ── Opportunities ─────────────────────────────────────────────────────────────

@router.get("/opportunities")
async def list_opportunities(
    order: str = Query("composite_score_desc"),
    limit: int = Query(50, ge=1, le=200),
    status: str | None = Query(None),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    q = select(Opportunity).limit(limit)
    if status:
        q = q.where(Opportunity.status == status)
    if order == "composite_score_desc":
        q = q.order_by(Opportunity.composite_score.desc())
    else:
        q = q.order_by(Opportunity.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()

    # Enrich with keyword text via a separate query
    kw_ids = list({str(r.keyword_id) for r in rows})
    kw_map: dict[str, str] = {}
    if kw_ids:
        placeholders = ", ".join(f":id_{i}" for i in range(len(kw_ids)))
        params = {f"id_{i}": uid for i, uid in enumerate(kw_ids)}
        kw_result = await db.execute(
            text(f"SELECT id::text, keyword FROM keywords WHERE id::text IN ({placeholders})"),
            params,
        )
        kw_map = {r[0]: r[1] for r in kw_result.fetchall()}

    return [
        {
            "id": str(r.id),
            "keyword_id": str(r.keyword_id),
            "keyword": kw_map.get(str(r.keyword_id), ""),
            "source": r.source,
            "search_score": r.search_score,
            "competitive_gap_score": r.competitive_gap_score,
            "trend_score": r.trend_score,
            "engagement_score": r.engagement_score,
            "composite_score": r.composite_score,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── Articles (raw SQL — no ORM model for articles table) ─────────────────────

@router.get("/articles")
async def list_articles(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    where = "WHERE org_id = :org_id"
    params: dict = {"org_id": str(org.id), "limit": limit}
    if status:
        where += " AND status = :status"
        params["status"] = status
    result = await db.execute(
        text(
            "SELECT id, org_id, keyword, title, body_html, word_count, "
            f"status, published_url, created_at FROM articles {where} "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "org_id": str(r[1]),
            "keyword": r[2],
            "title": r[3],
            "body_html": r[4],
            "word_count": r[5],
            "status": r[6],
            "published_url": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
        }
        for r in rows
    ]


class UpdateArticleBody(BaseModel):
    status: str | None = None
    published_url: str | None = None


@router.put("/articles/{article_id}")
async def update_article(
    article_id: str,
    body: UpdateArticleBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    try:
        uuid.UUID(article_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Article not found")

    sets: list[str] = []
    params: dict = {"id": article_id, "org_id": str(org.id)}
    if body.status is not None:
        sets.append("status = :status")
        params["status"] = body.status
    if body.published_url is not None:
        sets.append("published_url = :published_url")
        params["published_url"] = body.published_url
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")

    await db.execute(
        text(
            f"UPDATE articles SET {', '.join(sets)} "
            "WHERE id = CAST(:id AS uuid) AND org_id = :org_id"
        ),
        params,
    )
    await db.commit()
    return {"id": article_id, "updated": True}


# ── LinkedIn posts ────────────────────────────────────────────────────────────

@router.get("/linkedin-posts")
async def list_linkedin_posts(
    article_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    where = "WHERE org_id = :org_id"
    params: dict = {"org_id": str(org.id), "limit": limit}
    if article_id:
        where += " AND article_id = CAST(:article_id AS uuid)"
        params["article_id"] = article_id
    result = await db.execute(
        text(
            "SELECT id, article_id, content, hashtags, status, created_at "
            f"FROM linkedin_posts {where} ORDER BY created_at DESC LIMIT :limit"
        ),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "article_id": str(r[1]) if r[1] else None,
            "content": r[2],
            "hashtags": r[3] or [],
            "status": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


# ── Twitter threads ───────────────────────────────────────────────────────────

@router.get("/twitter-threads")
async def list_twitter_threads(
    article_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    where = "WHERE org_id = :org_id"
    params: dict = {"org_id": str(org.id), "limit": limit}
    if article_id:
        where += " AND article_id = CAST(:article_id AS uuid)"
        params["article_id"] = article_id
    result = await db.execute(
        text(
            "SELECT id, article_id, tweets, status, created_at "
            f"FROM twitter_threads {where} ORDER BY created_at DESC LIMIT :limit"
        ),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "article_id": str(r[1]) if r[1] else None,
            "tweets": r[2] or [],
            "tweet_count": len(r[2]) if r[2] else 0,
            "status": r[3],
            "created_at": r[4].isoformat() if r[4] else None,
        }
        for r in rows
    ]


# ── Newsletters ───────────────────────────────────────────────────────────────

@router.get("/newsletters")
async def list_newsletters(
    article_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    where = "WHERE org_id = :org_id"
    params: dict = {"org_id": str(org.id), "limit": limit}
    if article_id:
        where += " AND article_id = CAST(:article_id AS uuid)"
        params["article_id"] = article_id
    result = await db.execute(
        text(
            "SELECT id, article_id, subject, preview_text, body, body_html, "
            f"status, created_at FROM newsletters {where} "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        params,
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "article_id": str(r[1]) if r[1] else None,
            "subject": r[2],
            "preview_text": r[3],
            "body_html": r[4] or r[5] or "",
            "status": r[6],
            "created_at": r[7].isoformat() if r[7] else None,
        }
        for r in rows
    ]


# ── Social mock publish endpoints ────────────────────────────────────────────

@router.put("/linkedin-posts/{post_id}")
async def update_linkedin_post(
    post_id: str,
    body: dict,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    new_status = body.get("status", "draft")
    mock_url = (
        f"https://linkedin.com/posts/mock-{post_id[:8]}" if new_status == "published" else None
    )
    sets = "status = :status, updated_at = now()"
    params: dict = {"id": post_id, "org_id": str(org.id), "status": new_status}
    if mock_url:
        sets += ", published_url = :url"
        params["url"] = mock_url
    await db.execute(
        text(f"UPDATE linkedin_posts SET {sets} WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        params,
    )
    await db.commit()
    return {"id": post_id, "status": new_status, "published_url": mock_url}


@router.put("/twitter-threads/{thread_id}")
async def update_twitter_thread(
    thread_id: str,
    body: dict,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    new_status = body.get("status", "draft")
    mock_url = (
        f"https://twitter.com/mock/status/{thread_id[:8]}" if new_status == "published" else None
    )
    sets = "status = :status, updated_at = now()"
    params: dict = {"id": thread_id, "org_id": str(org.id), "status": new_status}
    if mock_url:
        sets += ", published_url = :url"
        params["url"] = mock_url
    await db.execute(
        text(
            f"UPDATE twitter_threads SET {sets}"
            " WHERE id = CAST(:id AS uuid) AND org_id = :org_id"
        ),
        params,
    )
    await db.commit()
    return {"id": thread_id, "status": new_status, "published_url": mock_url}


@router.put("/newsletters/{newsletter_id}")
async def update_newsletter(
    newsletter_id: str,
    body: dict,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    new_status = body.get("status", "draft")
    mock_url = (
        f"https://mail.mock/campaigns/{newsletter_id[:8]}" if new_status == "published" else None
    )
    sets = "status = :status, updated_at = now()"
    params: dict = {"id": newsletter_id, "org_id": str(org.id), "status": new_status}
    if mock_url:
        sets += ", sent_at = now()"
    await db.execute(
        text(f"UPDATE newsletters SET {sets} WHERE id = CAST(:id AS uuid) AND org_id = :org_id"),
        params,
    )
    await db.commit()
    return {"id": newsletter_id, "status": new_status, "published_url": mock_url}


# ── Competitors ───────────────────────────────────────────────────────────────

@router.get("/competitors")
async def list_competitors(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    result = await db.execute(
        select(Competitor).order_by(Competitor.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "domain": r.domain,
            "last_crawled_at": r.last_crawled_at.isoformat() if r.last_crawled_at else None,
        }
        for r in rows
    ]


_DOMAIN_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)


def _normalise_domain(raw: str) -> str:
    return (
        raw.strip()
        .lower()
        .removeprefix("https://")
        .removeprefix("http://")
        .removeprefix("www.")
        .split("/")[0]
    )


async def _domain_resolves(domain: str) -> bool:
    loop = asyncio.get_event_loop()
    try:
        await loop.getaddrinfo(domain, None)
        return True
    except socket.gaierror:
        return False


class AddCompetitorBody(BaseModel):
    domain: str


@router.post("/competitors", status_code=http_status.HTTP_201_CREATED)
async def add_competitor(
    body: AddCompetitorBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    domain = _normalise_domain(body.domain)
    if not domain:
        raise HTTPException(status_code=422, detail="domain is required")
    if not _DOMAIN_RE.match(domain):
        raise HTTPException(status_code=422, detail=f"'{domain}' is not a valid domain name")
    if not await _domain_resolves(domain):
        raise HTTPException(
            status_code=422,
            detail=f"'{domain}' could not be resolved — check the domain and try again",
        )
    comp = Competitor(org_id=org.id, domain=domain)
    db.add(comp)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"'{domain}' is already being tracked")
    await db.refresh(comp)
    return {"id": str(comp.id), "domain": comp.domain}


@router.delete("/competitors/{competitor_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def remove_competitor(
    competitor_id: str,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> None:
    try:
        cid = uuid.UUID(competitor_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found")
    result = await db.execute(select(Competitor).where(Competitor.id == cid))
    comp = result.scalar_one_or_none()
    if comp is None:
        raise HTTPException(status_code=404, detail="Competitor not found")
    await db.delete(comp)
    await db.commit()


# ── Competitor content ────────────────────────────────────────────────────────

@router.get("/competitor-content")
async def list_competitor_content(
    order: str = Query("threat_score_desc"),
    limit: int = Query(20, ge=1, le=100),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    q = select(CompetitorContent).limit(limit)
    if order == "threat_score_desc":
        q = q.order_by(CompetitorContent.threat_score.desc().nullslast())
    else:
        q = q.order_by(CompetitorContent.created_at.desc())
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "competitor_id": str(r.competitor_id),
            "url": r.url,
            "title": r.title,
            "word_count": r.word_count,
            "threat_score": r.threat_score,
            "keywords_overlap": r.keywords_overlap if isinstance(r.keywords_overlap, list) else [],
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


# ── Strategy reports ──────────────────────────────────────────────────────────

@router.get("/strategy-reports")
async def list_strategy_reports(
    limit: int = Query(5, ge=1, le=20),
    order: str = Query("desc"),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT id, opportunities_analyzed, recommendations, summary, status, created_at "
            "FROM strategy_reports WHERE org_id = :org_id "
            "ORDER BY created_at DESC LIMIT :limit"
        ),
        {"org_id": str(org.id), "limit": limit},
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "opportunities_analyzed": r[1],
            "recommendations": r[2] or [],
            "summary": r[3],
            "status": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


# ── Rank tracking ─────────────────────────────────────────────────────────────

@router.get("/rank-tracking")
async def list_rank_tracking(
    order: str = Query("position_asc"),
    limit: int = Query(20, ge=1, le=100),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    order_clause = "position ASC NULLS LAST" if order == "position_asc" else "checked_at DESC"
    result = await db.execute(
        text(
            f"SELECT id, keyword_id, keyword, position, previous_position, url, checked_at "
            f"FROM rank_tracking WHERE org_id = :org_id "
            f"ORDER BY {order_clause} LIMIT :limit"
        ),
        {"org_id": str(org.id), "limit": limit},
    )
    rows = result.fetchall()
    return [
        {
            "id": str(r[0]),
            "keyword_id": str(r[1]),
            "keyword": r[2],
            "position": r[3],
            "previous_position": r[4],
            "url": r[5],
            "checked_at": r[6].isoformat() if r[6] else None,
        }
        for r in rows
    ]


# ── AEO results ───────────────────────────────────────────────────────────────

@router.get("/aeo-results")
async def list_aeo_results(
    limit: int = Query(20, ge=1, le=100),
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    result = await db.execute(
        select(AeoResult).order_by(AeoResult.scanned_at.desc()).limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "keyword_id": str(r.keyword_id),
            "keyword": r.keyword,
            "has_ai_overview": r.ai_overview,
            "has_featured_snippet": r.featured_snippet,
            "paa_count": r.paa_count,
            "checked_at": r.scanned_at.isoformat() if r.scanned_at else None,
        }
        for r in rows
    ]


# ── Brand voice ───────────────────────────────────────────────────────────────

@router.get("/brand-voice")
async def get_brand_voice(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    result = await db.execute(select(BrandVoice).where(BrandVoice.org_id == org.id))
    bv = result.scalar_one_or_none()
    if bv is None:
        return {"id": None, "tone": "", "vocabulary": [], "banned_phrases": [], "style_rules": {}}
    return {
        "id": str(bv.id),
        "tone": bv.tone or "",
        "vocabulary": bv.vocabulary if isinstance(bv.vocabulary, list) else [],
        "banned_phrases": bv.banned_phrases if isinstance(bv.banned_phrases, list) else [],
        "style_rules": bv.style_rules if isinstance(bv.style_rules, dict) else {},
    }


class UpdateBrandVoiceBody(BaseModel):
    tone: str | None = None
    vocabulary: list[str] | None = None
    banned_phrases: list[str] | None = None
    style_rules: dict | None = None


@router.put("/brand-voice")
async def update_brand_voice(
    body: UpdateBrandVoiceBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    result = await db.execute(select(BrandVoice).where(BrandVoice.org_id == org.id))
    bv = result.scalar_one_or_none()
    if bv is None:
        bv = BrandVoice(org_id=org.id)
        db.add(bv)
    if body.tone is not None:
        bv.tone = body.tone
    if body.vocabulary is not None:
        bv.vocabulary = body.vocabulary
    if body.banned_phrases is not None:
        bv.banned_phrases = body.banned_phrases
    if body.style_rules is not None:
        bv.style_rules = body.style_rules
    bv.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(bv)
    return {"id": str(bv.id), "tone": bv.tone, "updated": True}


# ── Auto mode settings ────────────────────────────────────────────────────────

_AUTO_MODE_DEFAULTS = {
    "enabled": False,
    "schedule_time": "02:00",
    "seed_keywords": [],
    "max_daily_pipelines": 5,
}


@router.get("/settings/auto-mode")
async def get_auto_mode(
    org: Organization = Depends(get_current_org),
) -> dict:
    settings = org.settings or {}
    auto = settings.get("auto_mode", _AUTO_MODE_DEFAULTS)
    return {**_AUTO_MODE_DEFAULTS, **auto}


class UpdateAutoModeBody(BaseModel):
    enabled: bool | None = None
    schedule_time: str | None = None
    seed_keywords: list[str] | None = None
    max_daily_pipelines: int | None = None


@router.put("/settings/auto-mode")
async def update_auto_mode(
    body: UpdateAutoModeBody,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    settings = dict(org.settings or {})
    auto = dict(settings.get("auto_mode", _AUTO_MODE_DEFAULTS))
    if body.enabled is not None:
        auto["enabled"] = body.enabled
    if body.schedule_time is not None:
        auto["schedule_time"] = body.schedule_time
    if body.seed_keywords is not None:
        auto["seed_keywords"] = body.seed_keywords
    if body.max_daily_pipelines is not None:
        auto["max_daily_pipelines"] = body.max_daily_pipelines
    settings["auto_mode"] = auto
    await db.execute(
        sa_update(Organization).where(Organization.id == org.id).values(settings=settings)
    )
    await db.commit()
    return auto
