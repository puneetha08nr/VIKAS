"""Chat API — AI assistant with role-based routing (user vs admin).

Endpoints:
  POST /api/v1/chat/message     — send a message, get a response
  POST /api/v1/chat/lead        — save lead capture (name, phone, email)
  POST /api/v1/chat/feedback    — save chat feedback (rating, comment)
  GET  /api/v1/chat/history     — get recent chat history for this org
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_db_for_org
from config.settings import settings
from core.cost_tracker import CostTracker
from core.llm_router import LLMRouter
from db.models.organizations import Organization
from integrations.email import EmailIntegration
from integrations.slack_webhook import SlackWebhookIntegration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ── Request / Response models ─────────────────────────────────────────────────

class ChatMessageRequest(BaseModel):
    message: str
    role: str = "user"          # "user" | "admin"
    session_id: str | None = None


class ChatMessageResponse(BaseModel):
    reply: str
    role: str
    intent: str                 # "data_query" | "action" | "guidance" | "lead_capture"
    session_id: str
    suggestions: list[str] = []


class LeadRequest(BaseModel):
    name: str
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    session_id: str | None = None


class FeedbackRequest(BaseModel):
    rating: int                 # 1-5
    comment: str = ""
    session_id: str | None = None


# ── Role classifier ───────────────────────────────────────────────────────────

def _classify_role(message: str, role: str) -> str:
    """Return 'admin' or 'user' based on declared role and message content."""
    if role == "admin":
        return "admin"
    admin_keywords = [
        "agent run", "failed jobs", "error log", "cost today", "token usage",
        "celery", "alembic", "migration", "docker", "redis", "pipeline",
        "run agent", "trigger agent", "api key", "env var",
    ]
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in admin_keywords):
        return "admin"
    return "user"


# ── Intent classifier ─────────────────────────────────────────────────────────

def _classify_intent(message: str) -> str:
    """Classify message intent."""
    msg = message.lower()

    data_patterns = [
        "how many", "show me", "list", "count", "total", "how much",
        "what keywords", "which articles", "my content", "my keywords",
        "performance", "status", "stats",
    ]
    action_patterns = [
        "generate", "create", "write", "run", "start", "trigger",
        "research keywords", "make a post", "draft", "produce",
    ]
    lead_patterns = [
        "contact", "reach out", "talk to", "phone", "call me",
        "get in touch", "pricing", "how much does it cost", "buy", "sign up",
    ]

    if any(p in msg for p in lead_patterns):
        return "lead_capture"
    if any(p in msg for p in action_patterns):
        return "action"
    if any(p in msg for p in data_patterns):
        return "data_query"
    return "guidance"


# ── DB query helpers ───────────────────────────────────────────────────────────

async def _get_db_context(org_id: str, db: AsyncSession) -> dict:
    """Fetch rich live stats from DB to give the LLM context."""
    try:
        # Keyword counts by status
        kw = await db.execute(
            text("SELECT COUNT(*), status FROM keywords WHERE org_id = :org_id GROUP BY status"),
            {"org_id": org_id}
        )
        kw_summary = {row[1]: row[0] for row in kw.fetchall()}

        # Top keyword by priority score
        top_kw = await db.execute(
            text(
                "SELECT keyword, volume, kd, intent, priority_score FROM keywords "
                "WHERE org_id = :org_id AND status = 'validated' "
                "ORDER BY priority_score DESC NULLS LAST LIMIT 1"
            ),
            {"org_id": org_id}
        )
        top_kw_row = top_kw.fetchone()
        top_keyword = {
            "keyword": top_kw_row[0],
            "volume": top_kw_row[1],
            "kd": top_kw_row[2],
            "intent": top_kw_row[3],
            "score": float(top_kw_row[4]) if top_kw_row[4] else 0,
        } if top_kw_row else None

        # Article counts by status
        art = await db.execute(
            text("SELECT COUNT(*), status FROM articles WHERE org_id = :org_id GROUP BY status"),
            {"org_id": org_id}
        )
        art_summary = {row[1]: row[0] for row in art.fetchall()}

        # Latest article
        latest_art = await db.execute(
            text(
                "SELECT title, word_count, status, created_at FROM articles "
                "WHERE org_id = :org_id ORDER BY created_at DESC LIMIT 1"
            ),
            {"org_id": org_id}
        )
        latest_art_row = latest_art.fetchone()
        latest_article = {
            "title": latest_art_row[0],
            "word_count": latest_art_row[1],
            "status": latest_art_row[2],
        } if latest_art_row else None

        # Opportunities
        opp = await db.execute(
            text(
                "SELECT COUNT(*), status FROM opportunities "
                "WHERE org_id = :org_id GROUP BY status"
            ),
            {"org_id": org_id}
        )
        opp_summary = {row[1]: row[0] for row in opp.fetchall()}

        # Top opportunity
        top_opp = await db.execute(
            text(
                "SELECT k.keyword, o.composite_score, o.status FROM opportunities o "
                "JOIN keywords k ON o.keyword_id = k.id "
                "WHERE o.org_id = :org_id ORDER BY o.composite_score DESC LIMIT 1"
            ),
            {"org_id": org_id}
        )
        top_opp_row = top_opp.fetchone()
        top_opportunity = {
            "keyword": top_opp_row[0],
            "score": float(top_opp_row[1]),
            "status": top_opp_row[2],
        } if top_opp_row else None

        # Content pending review
        pending = await db.execute(
            text(
                "SELECT COUNT(*) FROM articles "
                "WHERE org_id = :org_id AND status IN ('draft', 'review')"
            ),
            {"org_id": org_id}
        )
        pending_count = pending.scalar() or 0

        # Today's LLM cost
        cost = await db.execute(
            text(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM agent_runs "
                "WHERE org_id = :org_id AND started_at >= CURRENT_DATE"
            ),
            {"org_id": org_id}
        )
        today_cost = float(cost.scalar() or 0)

        # Social content counts
        linkedin = await db.execute(
            text("SELECT COUNT(*) FROM linkedin_posts WHERE org_id = :org_id"),
            {"org_id": org_id}
        )
        twitter = await db.execute(
            text("SELECT COUNT(*) FROM twitter_threads WHERE org_id = :org_id"),
            {"org_id": org_id}
        )
        newsletters = await db.execute(
            text("SELECT COUNT(*) FROM newsletters WHERE org_id = :org_id"),
            {"org_id": org_id}
        )

        # Recent agent runs
        runs = await db.execute(
            text(
                "SELECT agent_name, status, cost_usd, duration_ms FROM agent_runs "
                "WHERE org_id = :org_id ORDER BY started_at DESC LIMIT 5"
            ),
            {"org_id": org_id}
        )
        recent_runs = [
            {
                "agent": r[0], "status": r[1],
                "cost": float(r[2] or 0),
                "duration_s": round((r[3] or 0) / 1000, 1),
            }
            for r in runs.fetchall()
        ]

        return {
            "keywords": kw_summary,
            "top_keyword": top_keyword,
            "articles": art_summary,
            "latest_article": latest_article,
            "opportunities": opp_summary,
            "top_opportunity": top_opportunity,
            "pending_review": pending_count,
            "today_cost_usd": today_cost,
            "social": {
                "linkedin_posts": linkedin.scalar() or 0,
                "twitter_threads": twitter.scalar() or 0,
                "newsletters": newsletters.scalar() or 0,
            },
            "recent_runs": recent_runs,
        }
    except Exception as exc:
        logger.warning("chat: failed to get DB context: %s", exc)
        return {}


# ── System prompts ─────────────────────────────────────────────────────────────

async def _rag_search(query: str, org_id: str, db: AsyncSession, top_k: int = 3) -> str:
    """Keyword-based RAG search over knowledge_chunks. No embeddings needed."""
    try:
        # Extract keywords from query (words > 3 chars)
        keywords = [w.lower() for w in query.split() if len(w) > 3]
        if not keywords:
            return ""

        # Build ILIKE conditions for each keyword
        conditions = " OR ".join(
            f"LOWER(chunk_text) LIKE :kw_{i}" for i in range(len(keywords))
        )
        params: dict = {"org_id": org_id, "top_k": top_k}
        for i, kw in enumerate(keywords):
            params[f"kw_{i}"] = f"%{kw}%"

        result = await db.execute(
            text(
                f"SELECT chunk_text, source_doc FROM knowledge_chunks "
                f"WHERE org_id = :org_id AND ({conditions}) "
                f"ORDER BY created_at DESC LIMIT :top_k"
            ),
            params,
        )
        rows = result.fetchall()
        if not rows:
            return ""

        chunks = "\n\n---\n\n".join(
            f"[Source: {row[1]}]\n{row[0]}" for row in rows
        )
        return chunks
    except Exception as exc:
        logger.warning("chat RAG search failed: %s", exc)
        return ""


def _user_system_prompt(db_context: dict) -> str:
    kw = db_context.get('keywords', {})
    arts = db_context.get('articles', {})
    top_kw = db_context.get('top_keyword')
    top_opp = db_context.get('top_opportunity')
    latest = db_context.get('latest_article')
    social = db_context.get('social', {})
    pending = db_context.get('pending_review', 0)

    if top_kw:
        top_kw_text = (
            f"{top_kw['keyword']} "
            f"(volume: {top_kw['volume']}, KD: {top_kw['kd']}, intent: {top_kw['intent']})"
        )
    else:
        top_kw_text = "None yet"

    top_opp_text = (
        f"{top_opp['keyword']} (score: {top_opp['score']:.1f}/10)"
        if top_opp else "None yet"
    )
    latest_text = (
        f'"{latest["title"]}" ({latest["word_count"]} words, {latest["status"]})'
        if latest else "None yet"
    )

    kw_total = sum(kw.values())
    kw_line = (
        f"{kw_total} total — {kw.get('validated', 0)} validated, "
        f"{kw.get('raw', 0)} raw, {kw.get('archived', 0)} archived"
    )
    art_total = sum(arts.values())
    art_line = (
        f"{art_total} total — {arts.get('draft', 0)} drafts, "
        f"{arts.get('review', 0)} in review, {arts.get('approved', 0)} approved"
    )
    social_line = (
        f"{social.get('linkedin_posts', 0)} LinkedIn posts, "
        f"{social.get('twitter_threads', 0)} Twitter threads, "
        f"{social.get('newsletters', 0)} newsletters"
    )

    return f"""You are a friendly AI marketing assistant for Vikas.

LIVE DATA (use to answer statistics questions):
- Keywords: {kw_line}
- Top keyword: {top_kw_text}
- Top opportunity: {top_opp_text}
- Articles: {art_line}
- Latest article: {latest_text}
- Pending review: {pending} items
- Social content: {social_line}
- Today's AI cost: ${db_context.get('today_cost_usd', 0):.4f}

GUIDELINES:
- Use simple, non-technical language. Be concise — max 3 sentences per reply.
- Answer statistics questions using the live data above.
- If user wants to talk to someone, ask for their contact details.
- Always end with a helpful follow-up question."""


def _admin_system_prompt(db_context: dict) -> str:
    kw = db_context.get('keywords', {})
    arts = db_context.get('articles', {})
    top_kw = db_context.get('top_keyword')
    top_opp = db_context.get('top_opportunity')
    social = db_context.get('social', {})
    recent = db_context.get("recent_runs", [])

    runs_text = "\n".join([
        f"  - {r['agent']}: {r['status']} (${r['cost']:.4f}, {r['duration_s']}s)"
        for r in recent
    ]) or "  No recent runs"

    social_line = (
        f"LinkedIn {social.get('linkedin_posts', 0)}, "
        f"Twitter {social.get('twitter_threads', 0)}, "
        f"Newsletters {social.get('newsletters', 0)}"
    )

    return f"""You are a technical AI assistant for the Vikas platform admin.

LIVE SYSTEM STATE:
- Keywords: {sum(kw.values())} total — {kw}
- Top keyword: {top_kw}
- Articles: {arts}
- Top opportunity: {top_opp}
- Social: {social_line}
- Pending review: {db_context.get('pending_review', 0)}
- Today's cost: ${db_context.get('today_cost_usd', 0):.4f}
- Recent agent runs:
{runs_text}

Help with agent runs, pipeline troubleshooting, LLM costs, DB queries.
Be technical and precise."""


# ── Main chat endpoint ─────────────────────────────────────────────────────────

@router.post("/message", response_model=ChatMessageResponse)
async def chat_message(
    body: ChatMessageRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> ChatMessageResponse:
    session_id = body.session_id or str(uuid.uuid4())
    detected_role = _classify_role(body.message, body.role)
    intent = _classify_intent(body.message)

    db_context = await _get_db_context(str(org.id), db)

    system_prompt = (
        _admin_system_prompt(db_context)
        if detected_role == "admin"
        else _user_system_prompt(db_context)
    )

    # RAG — search knowledge base for relevant context
    rag_context = await _rag_search(body.message, str(org.id), db)
    rag_section = (
        f"\n\nRelevant knowledge base context:\n{rag_context}"
        if rag_context
        else ""
    )

    full_prompt = f"{system_prompt}{rag_section}\n\nUser message: {body.message}"

    config_path = Path(__file__).parent.parent.parent / "config" / "model_tiers.yaml"
    router_llm = LLMRouter(config_path, CostTracker(), settings)

    try:
        reply = await router_llm.complete(
            prompt=full_prompt,
            tier="fast",
            org_id=str(org.id),
            run_id=str(uuid.uuid4()),
            db=db,
        )
    except Exception as exc:
        logger.warning("chat: LLM failed: %s", exc)
        reply = _fallback_reply(body.message, detected_role, intent)

    await _save_message(session_id, str(org.id), body.message, reply, detected_role, intent, db)

    suggestions = _get_suggestions(detected_role, intent)

    return ChatMessageResponse(
        reply=reply.strip(),
        role=detected_role,
        intent=intent,
        session_id=session_id,
        suggestions=suggestions,
    )


# ── Lead capture endpoint ─────────────────────────────────────────────────────

@router.post("/lead")
async def save_lead(
    body: LeadRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    await db.execute(
        text(
            "INSERT INTO chat_leads "
            "  (id, org_id, name, phone, email, company, session_id, created_at) "
            "VALUES "
            "  (gen_random_uuid(), :org_id, :name, :phone, :email, :company, :session_id, now())"
        ),
        {
            "org_id": str(org.id),
            "name": body.name,
            "phone": body.phone or "",
            "email": body.email or "",
            "company": body.company or "",
            "session_id": body.session_id or "",
        },
    )
    await db.commit()
    logger.info("chat: lead captured — %s %s", body.name, body.phone)

    # Send email notification to admin
    await _notify_admin_lead(body)

    return {"status": "saved", "message": f"Lead captured for {body.name}"}


async def _notify_admin_lead(body: LeadRequest) -> None:
    """Send email + Slack notification to admin when a new lead is captured."""
    admin_email = settings.admin_email
    if not admin_email:
        return

    subject = f"🔥 New Lead: {body.name}"
    html = f"""
    <div style="font-family:sans-serif;max-width:500px;margin:0 auto;padding:20px">
      <h2 style="color:#4f46e5">New Lead from Vikas Chat</h2>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="padding:8px;font-weight:bold;color:#6b7280">Name</td>
            <td style="padding:8px">{body.name}</td></tr>
        <tr style="background:#f9fafb">
            <td style="padding:8px;font-weight:bold;color:#6b7280">Phone</td>
            <td style="padding:8px">{body.phone or 'Not provided'}</td></tr>
        <tr><td style="padding:8px;font-weight:bold;color:#6b7280">Email</td>
            <td style="padding:8px">{body.email or 'Not provided'}</td></tr>
        <tr style="background:#f9fafb">
            <td style="padding:8px;font-weight:bold;color:#6b7280">Company</td>
            <td style="padding:8px">{body.company or 'Not provided'}</td></tr>
      </table>
      <p style="color:#6b7280;font-size:12px;margin-top:20px">
        From Vikas AI Platform — Chat Widget
      </p>
    </div>
    """

    email = EmailIntegration(
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        smtp_user=settings.smtp_user,
        smtp_password=settings.smtp_password,
        from_address=settings.smtp_from_address or settings.smtp_user,
    )
    sent = await email.send_email(admin_email, subject, html)

    # Also send Slack notification if configured
    if settings.slack_webhook_url:
        slack = SlackWebhookIntegration(webhook_url=settings.slack_webhook_url)
        slack_text = (
            f"🔥 *New Lead Captured*\n"
            f"*Name:* {body.name}\n"
            f"*Phone:* {body.phone or 'N/A'}\n"
            f"*Email:* {body.email or 'N/A'}\n"
            f"*Company:* {body.company or 'N/A'}"
        )
        await slack.send_message(slack_text)

    if sent:
        logger.info("chat: lead notification sent to %s", admin_email)
    else:
        logger.info("chat: lead notification skipped (SMTP not configured)")


# ── Feedback endpoint ─────────────────────────────────────────────────────────

@router.post("/feedback")
async def save_feedback(
    body: FeedbackRequest,
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> dict:
    await db.execute(
        text(
            "INSERT INTO chat_feedback "
            "  (id, org_id, rating, comment, session_id, created_at) "
            "VALUES "
            "  (gen_random_uuid(), :org_id, :rating, :comment, :session_id, now())"
        ),
        {
            "org_id": str(org.id),
            "rating": body.rating,
            "comment": body.comment,
            "session_id": body.session_id or "",
        },
    )
    await db.commit()
    return {"status": "saved"}


# ── History endpoint ──────────────────────────────────────────────────────────

@router.get("/history")
async def chat_history(
    org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db_for_org),
) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT session_id, message, reply, role, intent, created_at "
            "FROM chat_messages WHERE org_id = :org_id "
            "ORDER BY created_at DESC LIMIT 50"
        ),
        {"org_id": str(org.id)},
    )
    rows = result.fetchall()
    return [
        {
            "session_id": r[0],
            "message": r[1],
            "reply": r[2],
            "role": r[3],
            "intent": r[4],
            "created_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _save_message(
    session_id: str, org_id: str, message: str,
    reply: str, role: str, intent: str, db: AsyncSession
) -> None:
    try:
        await db.execute(
            text(
                "INSERT INTO chat_messages "
                "  (id, org_id, session_id, message, reply, role, intent, created_at) "
                "VALUES "
                "  (gen_random_uuid(), :org_id, :session_id, "
                "   :message, :reply, :role, :intent, now())"
            ),
            {
                "org_id": org_id, "session_id": session_id,
                "message": message, "reply": reply,
                "role": role, "intent": intent,
            },
        )
        await db.flush()
    except Exception as exc:
        logger.warning("chat: could not save message: %s", exc)


def _fallback_reply(message: str, role: str, intent: str) -> str:
    if role == "admin":
        return (
            "I'm having trouble connecting to the LLM right now. "
            "Check your API key configuration in .env and verify the Ollama/API service is running."
        )
    if intent == "lead_capture":
        return (
            "I'd love to connect you with our team! "
            "Could you share your name and phone number so someone can reach out to you?"
        )
    return (
        "I'm here to help with your marketing questions! "
        "You can ask me about keywords, content, opportunities, or how Vikas works."
    )


def _get_suggestions(role: str, intent: str) -> list[str]:
    if role == "admin":
        return [
            "Show recent failed agent runs",
            "What's today's LLM cost?",
            "How many keywords need validation?",
        ]
    if intent == "lead_capture":
        return ["Tell me more about pricing", "Schedule a demo", "How does it work?"]
    if intent == "data_query":
        return [
            "Show my top opportunities",
            "How many articles do I have?",
            "What keywords are validated?",
        ]
    return [
        "What can Vikas do for me?",
        "How does content generation work?",
        "I want to talk to someone",
    ]
