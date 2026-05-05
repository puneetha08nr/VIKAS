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

from pydantic import BaseModel, field_validator, model_validator

# ── Shared mixin ──────────────────────────────────────────────────────────────

class _KeywordMetricsMixin(BaseModel):
    """Shared numeric fields and coercion for keyword-related outputs."""
    volume: int | None = None
    kd: float | None = None
    cpc: float | None = None
    data_source: str = "llm_estimate"

    @field_validator("volume", mode="before")
    @classmethod
    def _coerce_volume(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return int(float(str(v)))
        except (ValueError, TypeError):
            return None

    @field_validator("kd", "cpc", mode="before")
    @classmethod
    def _coerce_float(cls, v: object) -> float | None:
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
    intent: str | None = None
    reason: str | None = None
    source_run_id: str | None = None

    @field_validator("intent", mode="before")
    @classmethod
    def normalise_intent(cls, v: object) -> str | None:
        if not v:
            return None
        s = str(v).lower().strip()
        return s if s in _VALID_INTENTS else None

    @field_validator("reason", mode="before")
    @classmethod
    def normalise_reason(cls, v: object) -> str | None:
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
    def derive_status_from_worth_targeting(self) -> KeywordValidationOutput:
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


# ── SEO agents (continued) ────────────────────────────────────────────────────

class SiteAuditorOutput(BaseModel):
    """One audit snapshot produced by site_auditor agent."""
    org_id: str
    site_url: str
    total_keywords: int = 0
    ranking_count: int = 0
    quick_wins_count: int = 0
    not_ranking_count: int = 0
    avg_position: float | None = None
    gsc_rows_fetched: int = 0
    summary: dict = {}

    @field_validator("total_keywords", "ranking_count", "quick_wins_count",
                     "not_ranking_count", "gsc_rows_fetched", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0

    @field_validator("avg_position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> float | None:
        if v is None:
            return None
        try:
            return round(float(str(v)), 1)
        except (ValueError, TypeError):
            return None


# ── SEO agents (AEO scanner) ──────────────────────────────────────────────────

_VALID_AEO_STATUSES = frozenset({"found", "not_found", "blocked"})


class AeoScannerOutput(BaseModel):
    """One SERP snapshot produced by aeo_scanner agent."""
    keyword_id: str
    keyword: str
    ai_overview: bool = False
    featured_snippet: bool = False
    paa_count: int = 0
    organic_position: int | None = None
    status: str = "found"  # "found" | "not_found" | "blocked"

    @field_validator("keyword_id", "keyword", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("paa_count", mode="before")
    @classmethod
    def _coerce_paa(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0

    @field_validator("organic_position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> int | None:
        if v is None:
            return None
        try:
            return max(1, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return None

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        s = str(v).strip()
        return s if s in _VALID_AEO_STATUSES else "found"


# ── SEO stubs (fill when building each agent) ─────────────────────────────────

class GapAnalysisOutput(BaseModel):
    """One opportunity row updated by gap_analyzer agent."""
    keyword: str
    keyword_id: str
    competitive_gap_score: float
    our_position: float | None = None
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
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


class RankTrackingOutput(BaseModel):
    """One row produced by rank_tracker agent."""
    keyword: str
    keyword_id: str
    position: float | None = None
    previous_position: float | None = None
    status: str = "not_ranking"  # "quick_win" | "ranking" | "not_ranking"

    @field_validator("position", "previous_position", mode="before")
    @classmethod
    def _coerce_position(cls, v: object) -> float | None:
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


# ── Video agents ──────────────────────────────────────────────────────────────

_VALID_VIDEO_STATUSES = frozenset(
    {"pending_video", "in_review", "video_ready", "published", "rejected"}
)


class VideoHandoffOutput(BaseModel):
    """Result produced by video_handoff agent for one created job."""
    job_id: str
    upload_url: str
    status: str = "pending_video"
    notified: bool = False

    @field_validator("job_id", "upload_url", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        s = str(v).strip()
        return s if s in _VALID_VIDEO_STATUSES else "pending_video"


# ── Ops agents ────────────────────────────────────────────────────────────────

class PreferenceLearnerOutput(BaseModel):
    """Summary produced by preference_learner for one content_type."""
    org_id: str
    content_type: str
    total_feedback: int = 0
    approved: int = 0
    edited: int = 0
    rejected: int = 0
    approval_rate: float = 0.0
    edit_rate: float = 0.0
    rejection_rate: float = 0.0
    preferences_written: int = 0

    @field_validator("org_id", "content_type", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("total_feedback", "approved", "edited", "rejected",
                     "preferences_written", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0

    @field_validator("approval_rate", "edit_rate", "rejection_rate", mode="before")
    @classmethod
    def _clamp_rate(cls, v: object) -> float:
        try:
            return round(max(0.0, min(1.0, float(str(v)))), 4)
        except (ValueError, TypeError):
            return 0.0


# ── Content stubs ─────────────────────────────────────────────────────────────

# ArticlePlannerOutput and ArticleWriterOutput defined later in this file


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
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        return str(v) if str(v) in {"ok", "failed", "skipped"} else "failed"


class ThreatAssessorOutput(BaseModel):
    """One competitor_content row scored by threat_assessor agent."""
    competitor_content_id: str
    url: str
    keyword_overlap_score: float = 0.0  # 0-10, count of validated keywords in body
    content_depth_score: float = 0.0    # 0-10, derived from word_count
    threat_score: float = 0.0           # composite: (overlap*0.6) + (depth*0.4)

    @field_validator("keyword_overlap_score", "content_depth_score", "threat_score", mode="before")
    @classmethod
    def _clamp_score(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 3)
        except (ValueError, TypeError):
            return 0.0


class KeywordOverlapOutput(BaseModel):
    """One competitor_content row updated by keyword_overlap_analyzer."""
    competitor_content_id: str
    url: str
    matched_keywords: list[str] = []
    overlap_count: int = 0

    @field_validator("matched_keywords", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        return []

    @field_validator("overlap_count", mode="before")
    @classmethod
    def _coerce_count(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


# ── Knowledge agents ─────────────────────────────────────────────────────────

class InternalLinkOutput(BaseModel):
    """One internal link suggestion produced by internal_link_finder agent."""
    url: str
    title: str
    anchor_text: str         # defaults to title — caller may override
    similarity_score: float = 0.0

    @field_validator("url", "title", "anchor_text", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("similarity_score", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(1.0, float(str(v)))), 4)
        except (ValueError, TypeError):
            return 0.0


# ── Knowledge stubs ───────────────────────────────────────────────────────────

class DocumentIngesterOutput(BaseModel):
    """Output contract for document_ingester agent."""
    source_name: str
    chunks_created: int = 0
    chunks_failed: int = 0   # embedded with NULL (stored but no vector)
    status: str = "success"  # success | partial | failed


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


class RagSearcherOutput(BaseModel):
    """One knowledge chunk returned by rag_searcher — ranked by cosine similarity."""
    chunk_id: str
    content: str        # maps to knowledge_chunks.chunk_text
    source: str         # maps to knowledge_chunks.source_doc
    similarity_score: float = 0.0

    @field_validator("chunk_id", "content", "source", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()

    @field_validator("similarity_score", mode="before")
    @classmethod
    def _clamp_sim(cls, v: object) -> float:
        try:
            return round(max(-1.0, min(1.0, float(str(v)))), 6)
        except (ValueError, TypeError):
            return 0.0


# kept for backwards-compat if anything references the old stub name
RAGSearchOutput = RagSearcherOutput


# WordPressPublisherOutput defined later in this file


# ── SEO agents (topic discovery) ──────────────────────────────────────────────

_VALID_TOPIC_SOURCES = frozenset(
    {"pytrends_rising", "pytrends_top", "google_suggest", "reddit"}
)


class TopicDiscoveryOutput(BaseModel):
    """One topic row produced by topic_discovery agent."""
    topic: str
    source: str        # "pytrends_rising" | "pytrends_top" | "google_suggest" | "reddit"
    score: float = 0.0  # 0-10 signal strength
    related_keywords: list[str] = []

    @field_validator("topic", mode="before")
    @classmethod
    def _strip_topic(cls, v: object) -> str:
        return str(v).strip()[:500]

    @field_validator("source", mode="before")
    @classmethod
    def _validate_source(cls, v: object) -> str:
        s = str(v).strip()
        return s if s in _VALID_TOPIC_SOURCES else "google_suggest"

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 2)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("related_keywords", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        return []


# ── Video agents ──────────────────────────────────────────────────────────────

class BrollSelectorOutput(BaseModel):
    """One b-roll result produced by broll_selector agent."""
    scene_text: str
    suggestions_found: int = 0
    status: str = "ok"  # ok | no_results | blocked


# ── Content agents ────────────────────────────────────────────────────────────

class ArticlePlannerOutput(BaseModel):
    """Output produced by article_planner agent."""
    article_plan_id: str
    keyword: str
    title: str
    meta_description: str = ""
    word_count_target: int = 1800
    outline_sections: int = 0
    status: str = "planned"


class ArticleWriterOutput(BaseModel):
    """Output produced by article_writer agent."""
    article_id: str
    article_plan_id: str
    title: str
    word_count: int = 0
    sections_written: int = 0
    status: str = "draft"


class ContentDirectorOutput(BaseModel):
    """Output produced by content_director orchestrator."""
    opportunity_id: str
    article_plan_id: str = ""
    article_id: str = ""
    linkedin_post_id: str = ""
    twitter_thread_id: str = ""
    newsletter_id: str = ""
    video_script_id: str = ""
    status: str = "success"


class LinkedInAgentOutput(BaseModel):
    """Output produced by linkedin_agent."""
    linkedin_post_id: str
    article_id: str
    word_count: int = 0
    status: str = "draft"


class TwitterAgentOutput(BaseModel):
    """Output produced by twitter_agent."""
    twitter_thread_id: str
    article_id: str
    tweet_count: int = 0
    status: str = "draft"


class NewsletterAgentOutput(BaseModel):
    """Output produced by newsletter_agent."""
    newsletter_id: str
    article_id: str
    status: str = "draft"


class VideoScriptwriterOutput(BaseModel):
    """Output produced by video_scriptwriter agent."""
    video_script_id: str
    article_id: str
    total_duration_seconds: int = 0
    scene_count: int = 0
    status: str = "draft"


class LeadMagnetAgentOutput(BaseModel):
    """Output produced by lead_magnet_agent."""
    lead_magnet_id: str
    keyword: str
    format: str  # checklist | ebook | template
    title: str
    status: str = "draft"


class WordPressPublisherOutput(BaseModel):
    """Output produced by wordpress_publisher agent."""
    article_id: str
    published_url: str = ""
    wp_post_id: int = 0
    status: str = "published"


# ── Competitor agents ─────────────────────────────────────────────────────────

class CompetitorDiscoveryOutput(BaseModel):
    """Output produced by competitor_discovery agent."""
    seed_keyword: str
    competitors_found: int = 0
    competitors_written: int = 0


# ── Ops agents ────────────────────────────────────────────────────────────────

class StrategySynthesizerOutput(BaseModel):
    """Output produced by strategy_synthesizer agent."""
    report_id: str
    opportunities_analyzed: int = 0
    recommendations_count: int = 0
    status: str = "success"


class AIAssistantOutput(BaseModel):
    """Output produced by ai_assistant agent."""
    question: str
    answer: str
    sources_used: int = 0
    status: str = "success"


class PipelineOrchestratorOutput(BaseModel):
    """Output produced by pipeline_orchestrator agent."""
    opportunity_id: str
    stages_completed: int = 0
    stages_failed: int = 0
    status: str = "success"


class AutoModeEngineOutput(BaseModel):
    """Output produced by auto_mode_engine agent."""
    opportunities_selected: int = 0
    pipelines_triggered: int = 0
    status: str = "success"
