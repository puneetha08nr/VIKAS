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


# ── SEO stubs (fill when building each agent) ─────────────────────────────────

class GapAnalysisOutput(BaseModel):
    """Output contract for gap_analyzer agent. Fill when building."""
    ...


class RankTrackingOutput(BaseModel):
    """Output contract for rank_tracker agent. Fill when building."""
    ...


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


# ── Knowledge stubs ───────────────────────────────────────────────────────────

class DocumentIngestionOutput(BaseModel):
    """Output contract for document_ingester agent. Fill when building."""
    ...


class BrandVoiceOutput(BaseModel):
    """Output contract for brand_voice_keeper agent. Fill when building."""
    ...


class RAGSearchOutput(BaseModel):
    """Output contract for rag_searcher agent. Fill when building."""
    ...


class WordPressPublishOutput(BaseModel):
    """Output contract for wordpress_publisher agent. Fill when building."""
    ...
