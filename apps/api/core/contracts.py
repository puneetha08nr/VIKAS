"""
Output contracts for all v1 agents.

Each agent's execute() result is validated against its contract before being
written to the DB. This catches bad LLM output at the boundary rather than
silently persisting malformed data.

Convention:
  - All numeric fields are Optional with None default (DB columns are nullable)
  - String enum fields validate against the allowed set; invalid → None or default
  - Stubs for unbuilt agents are empty models; fill when building the agent
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, field_validator, model_validator

# ── Shared mixin ──────────────────────────────────────────────────────────────

class _KeywordMetricsMixin(BaseModel):
    """Shared numeric fields and coercion for keyword-related outputs."""
    volume: Optional[int] = None
    kd: Optional[float] = None
    cpc: Optional[float] = None
    data_source: str = "llm_estimate"

    @field_validator("volume", mode="before")
    @classmethod
    def _coerce_volume(cls, v: object) -> Optional[int]:
        if v is None:
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None

    @field_validator("kd", "cpc", mode="before")
    @classmethod
    def _coerce_float(cls, v: object) -> Optional[float]:
        if v is None:
            return None
        try:
            return float(str(v))
        except (ValueError, TypeError):
            return None


# ── SEO agents ────────────────────────────────────────────────────────────────

_VALID_INTENTS = frozenset({"informational", "commercial", "transactional", "navigational"})


class KeywordResearchOutput(_KeywordMetricsMixin):
    """One keyword row produced by keyword_research agent."""
    keyword: str
    intent: Optional[str] = None
    reason: Optional[str] = None
    source_run_id: Optional[str] = None

    @field_validator("intent", mode="before")
    @classmethod
    def normalise_intent(cls, v: object) -> Optional[str]:
        if not v:
            return None
        s = str(v).lower().strip()
        return s if s in _VALID_INTENTS else None

    @field_validator("reason", mode="before")
    @classmethod
    def normalise_reason(cls, v: object) -> Optional[str]:
        if not v:
            return None
        s = str(v).strip()
        return s or None


class KeywordValidationOutput(_KeywordMetricsMixin):
    """One keyword row produced by keyword_validator agent."""
    keyword_id: str
    keyword: str
    worth_targeting: bool = False
    reason: str = ""
    updated_status: str = "archived"

    @field_validator("worth_targeting", mode="before")
    @classmethod
    def coerce_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in {"true", "yes", "1", "worth targeting"}
        return bool(v)

    @field_validator("updated_status", mode="before")
    @classmethod
    def validate_status(cls, v: object) -> str:
        return str(v) if str(v) in {"validated", "archived"} else "archived"

    @model_validator(mode="after")
    def derive_status_from_worth_targeting(self) -> "KeywordValidationOutput":
        # If status wasn't explicitly set to a recognised value, derive it.
        if self.updated_status == "archived" and self.worth_targeting:
            self.updated_status = "validated"
        return self


class OpportunityOutput(BaseModel):
    """One row produced by opportunity_scorer agent."""
    keyword_id: str
    org_id: str
    source: str = "keyword_research"
    search_score: float
    competitive_gap_score: float
    trend_score: float
    engagement_score: float
    composite_score: float
    status: str = "new"
    format_fit_scores: dict = {}


class TrendSignalOutput(BaseModel):
    """One row produced by trend_collector agent."""
    query: str
    source: str = "google_trends"
    momentum: float = 5.0

    @field_validator("query", mode="before")
    @classmethod
    def _strip_query(cls, v: object) -> str:
        return str(v).strip()[:500]

    @field_validator("momentum", mode="before")
    @classmethod
    def _clamp_momentum(cls, v: object) -> float:
        try:
            return max(0.0, min(10.0, float(str(v))))
        except (ValueError, TypeError):
            return 5.0


# ── SEO stubs (fill when building each agent) ─────────────────────────────────

class GapAnalysisOutput(BaseModel):
    """One opportunity row updated by gap_analyzer agent."""
    keyword: str
    keyword_id: str
    competitive_gap_score: float
    our_position: Optional[float] = None
    competitor_pages_found: int = 0

    @field_validator("competitive_gap_score", mode="before")
    @classmethod
    def _clamp_gap(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 2)
        except (ValueError, TypeError):
            return 5.0

    @field_validator("competitor_pages_found", mode="before")
    @classmethod
    def _coerce_pages(cls, v: object) -> int:
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return 0


class RankTrackingOutput(BaseModel):
    """One row produced by rank_tracker agent."""
    keyword: str
    keyword_id: str
    position: Optional[float] = None
    previous_position: Optional[float] = None
    status: str = "not_ranking"  # "quick_win" | "ranking" | "not_ranking"

    @field_validator("position", "previous_position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> Optional[float]:
        if v is None:
            return None
        try:
            return round(float(str(v)), 1)
        except (ValueError, TypeError):
            return None

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        return str(v) if str(v) in {"quick_win", "ranking", "not_ranking"} else "not_ranking"


# ── Content stubs ─────────────────────────────────────────────────────────────

class ArticlePlanOutput(BaseModel):
    """Output contract for article_planner agent. Fill when building."""
    ...


class ArticleOutput(BaseModel):
    """Output contract for article_writer agent. Fill when building."""
    ...


class ContentDirectorOutput(BaseModel):
    """Output contract for content_director agent. Fill when building."""
    ...


class LinkedInPostOutput(BaseModel):
    """Output contract for linkedin_agent. Fill when building."""
    ...


# ── Competitor agents ─────────────────────────────────────────────────────────

class CompetitorMonitorOutput(BaseModel):
    """One competitor entry produced by competitor_monitor agent."""
    domain: str
    urls_found: int = 0
    status: str = "ok"  # "ok" | "unreachable"

    @field_validator("status", mode="before")
    @classmethod
    def validate_monitor_status(cls, v: object) -> str:
        return str(v) if str(v) in {"ok", "unreachable"} else "ok"


class ContentExtractorOutput(BaseModel):
    """One URL result produced by content_extractor agent."""
    url: str
    domain: str
    title: str = ""
    word_count: int = 0
    status: str = "ok"  # "ok" | "failed" | "skipped"

    @field_validator("url", "domain", mode="before")
    @classmethod
    def _strip_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("word_count", mode="before")
    @classmethod
    def _coerce_word_count(cls, v: object) -> int:
        try:
            return max(0, int(v))
        except (ValueError, TypeError):
            return 0

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        return str(v) if str(v) in {"ok", "failed", "skipped"} else "failed"


# ── Knowledge stubs ───────────────────────────────────────────────────────────

class DocumentIngestionOutput(BaseModel):
    """Output contract for document_ingester agent. Fill when building."""
    ...


class BrandVoiceOutput(BaseModel):
    """One brand-voice state row produced by brand_voice_keeper agent."""
    org_id: str
    tone: str = ""
    vocabulary: list = []
    banned_phrases: list = []
    style_rules: dict = {}

    @field_validator("tone", mode="before")
    @classmethod
    def _strip_tone(cls, v: object) -> str:
        return str(v).strip()[:255] if v else ""

    @field_validator("vocabulary", "banned_phrases", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, ValueError):
                return []
        return []

    @field_validator("style_rules", mode="before")
    @classmethod
    def _coerce_dict(cls, v: object) -> dict:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            import json
            try:
                parsed = json.loads(v)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}


class RAGSearchOutput(BaseModel):
    """Output contract for rag_searcher agent. Fill when building."""
    ...


class WordPressPublishOutput(BaseModel):
    """Output contract for wordpress_publisher agent. Fill when building."""
    ...
