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

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# ── Shared mixin ──────────────────────────────────────────────────────────────

class _KeywordMetricsMixin(BaseModel):
    """Shared numeric fields and coercion for keyword-related outputs."""
    volume: int | None = None
    kd: float | None = None
    cpc: float | None = None
    data_source: str = "pending"

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
    trend_score: float | None = None  # NULL until a real trend signal is available
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


# ── Content stubs (aliases — full contracts defined below) ────────────────────


class LinkedInPostOutput(BaseModel):
    """Output contract for linkedin_agent."""
    content_item_id: str
    post_text: str
    hashtags: list[str] = []
    estimated_reach_tier: str = "medium"

    @field_validator("estimated_reach_tier", mode="before")
    @classmethod
    def _validate_tier(cls, v: object) -> str:
        return str(v) if str(v) in {"low", "medium", "high"} else "medium"

    @field_validator("hashtags", mode="before")
    @classmethod
    def _coerce_hashtags(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(h).lstrip("#") for h in v]
        return []

    @field_validator("post_text", mode="before")
    @classmethod
    def _coerce_text(cls, v: object) -> str:
        return str(v).strip() if v else ""


class VideoScriptOutput(BaseModel):
    """Output contract for video_script_agent."""
    content_item_id: str
    title: str
    total_duration_seconds: int = 180
    scenes: list[dict] = []
    cta: str = ""

    @field_validator("total_duration_seconds", mode="before")
    @classmethod
    def _coerce_duration(cls, v: object) -> int:
        try:
            return max(30, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 180

    @field_validator("scenes", mode="before")
    @classmethod
    def _coerce_scenes(cls, v: object) -> list:
        return v if isinstance(v, list) else []


class LeadMagnetOutput(BaseModel):
    """Output contract for lead_magnet_agent."""
    content_item_id: str
    title: str
    subtitle: str = ""
    format: str = "checklist"
    introduction: str = ""
    sections: list[dict] = []
    bonus_tip: str = ""
    cta: str = ""

    @field_validator("format", mode="before")
    @classmethod
    def _validate_format(cls, v: object) -> str:
        valid = {"checklist", "template", "mini-guide", "swipe-file"}
        return str(v) if str(v) in valid else "checklist"

    @field_validator("sections", mode="before")
    @classmethod
    def _coerce_sections(cls, v: object) -> list:
        return v if isinstance(v, list) else []


class ImageCreatorOutput(BaseModel):
    """Output contract for image_creator_agent."""
    content_item_id: str
    prompt: str
    negative_prompt: str = ""
    style: str = "photorealistic"
    aspect_ratio: str = "16:9"
    alt_text: str = ""
    image_url: str = ""

    @field_validator("style", mode="before")
    @classmethod
    def _validate_style(cls, v: object) -> str:
        valid = {"photorealistic", "illustration", "3d"}
        return str(v) if str(v) in valid else "photorealistic"

    @field_validator("aspect_ratio", mode="before")
    @classmethod
    def _validate_ratio(cls, v: object) -> str:
        valid = {"16:9", "1:1", "9:16", "4:3"}
        return str(v) if str(v) in valid else "16:9"


class NewsletterOutput(BaseModel):
    """Output contract for newsletter_agent."""
    content_item_id: str
    subject_line: str
    preview_text: str = ""
    body: str = ""
    cta_text: str = ""
    estimated_open_rate_tier: str = "medium"

    @field_validator("estimated_open_rate_tier", mode="before")
    @classmethod
    def _validate_tier(cls, v: object) -> str:
        return str(v) if str(v) in {"low", "medium", "high"} else "medium"

    @field_validator("subject_line", "preview_text", "body", "cta_text", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip() if v else ""


class TwitterThreadOutput(BaseModel):
    """Output contract for twitter_agent."""
    content_item_id: str
    tweets: list[str] = []
    hashtags: list[str] = []
    estimated_reach_tier: str = "medium"

    @field_validator("estimated_reach_tier", mode="before")
    @classmethod
    def _validate_tier(cls, v: object) -> str:
        return str(v) if str(v) in {"low", "medium", "high"} else "medium"

    @field_validator("hashtags", mode="before")
    @classmethod
    def _coerce_hashtags(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(h).lstrip("#") for h in v]
        return []

    @field_validator("tweets", mode="before")
    @classmethod
    def _coerce_tweets(cls, v: object) -> list[str]:
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


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


# ── Knowledge stubs ───────────────────────────────────────────────────────────

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


# ── Contracts matching remote agent implementations ───────────────────────────

class ArticlePlannerOutput(BaseModel):
    """Output contract for article_planner agent (remote implementation)."""
    article_plan_id: str
    keyword: str
    title: str
    meta_description: str = ""
    word_count_target: int = 1800
    outline_sections: int = 0
    status: str = "planned"


class ArticleWriterOutput(BaseModel):
    """Output contract for article_writer agent (remote implementation)."""
    article_id: str
    article_plan_id: str
    title: str
    word_count: int = 0
    sections_written: int = 0
    status: str = "draft"


class ContentDirectorOutput(BaseModel):
    """Output contract for content_director agent (remote implementation)."""
    opportunity_id: str
    article_plan_id: str = ""
    article_id: str = ""
    linkedin_post_id: str = ""
    twitter_thread_id: str = ""
    newsletter_id: str = ""
    video_script_id: str = ""
    status: str = "success"


class LinkedInAgentOutput(BaseModel):
    """Output contract for linkedin_agent (remote implementation)."""
    linkedin_post_id: str
    article_id: str = ""
    word_count: int = 0
    status: str = "draft"


class TwitterAgentOutput(BaseModel):
    """Output contract for twitter_agent (remote implementation)."""
    twitter_thread_id: str
    article_id: str = ""
    tweet_count: int = 0
    status: str = "draft"


class NewsletterAgentOutput(BaseModel):
    """Output contract for newsletter_agent (remote implementation)."""
    newsletter_id: str
    article_id: str = ""
    status: str = "draft"


class LeadMagnetAgentOutput(BaseModel):
    """Output contract for lead_magnet_agent (remote implementation)."""
    lead_magnet_id: str
    keyword: str
    format: str = "checklist"
    title: str = ""
    status: str = "draft"


class VideoScriptwriterOutput(BaseModel):
    """Output contract for video_scriptwriter agent (remote implementation)."""
    video_script_id: str
    article_id: str = ""
    total_duration_seconds: int = 0
    scene_count: int = 0
    status: str = "draft"


class WordPressPublisherOutput(BaseModel):
    """Output contract for wordpress_publisher agent (remote implementation)."""
    article_id: str
    published_url: str = ""
    wp_post_id: int = 0
    status: str = "draft"


class DocumentIngesterOutput(BaseModel):
    """Output contract for document_ingester agent (remote implementation)."""
    source_name: str
    chunks_created: int = 0
    chunks_failed: int = 0
    status: str = "success"


class RagSearcherOutput(BaseModel):
    """Output contract for rag_searcher agent (remote implementation)."""
    chunk_id: str
    content: str
    source: str
    similarity_score: float = 0.0

    @field_validator("similarity_score", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(-1.0, min(1.0, float(str(v)))), 6)
        except (ValueError, TypeError):
            return 0.0


class InternalLinkOutput(BaseModel):
    """One internal link suggestion produced by internal_link_finder."""
    url: str
    title: str
    anchor_text: str = ""
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


class AIAssistantOutput(BaseModel):
    """Output produced by ai_assistant agent."""
    question: str
    answer: str
    sources_used: int = 0
    status: str = "success"


class ThreatAssessorOutput(BaseModel):
    """One competitor_content row scored by threat_assessor agent."""
    competitor_content_id: str
    url: str
    keyword_overlap_score: float = 0.0
    content_depth_score: float = 0.0
    threat_score: float = 0.0

    @field_validator("keyword_overlap_score", "content_depth_score", "threat_score", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 3)
        except (ValueError, TypeError):
            return 0.0


class CompetitorDiscoveryOutput(BaseModel):
    """Output produced by competitor_discovery agent."""
    seed_keyword: str
    competitors_found: int = 0
    competitors_written: int = 0


class AeoScannerOutput(BaseModel):
    """Output contract for aeo_scanner agent — validated from LLM JSON."""
    keyword: str = ""
    keyword_id: str = ""
    ai_overview: bool = False
    featured_snippet: bool = False
    paa_count: int = 0
    organic_position: int | None = None
    status: str = "ok"
    aeo_score: float = 0.0

    @field_validator("aeo_score", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 2)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("paa_count", mode="before")
    @classmethod
    def _coerce_int(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


class TopicDiscoveryOutput(BaseModel):
    """One topic row produced by topic_discovery agent."""
    topic: str
    source: str = "google_suggest"
    score: float = 0.0
    related_keywords: list[str] = []

    @field_validator("topic", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        return str(v).strip()[:500]

    @field_validator("score", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(10.0, float(str(v)))), 2)
        except (ValueError, TypeError):
            return 0.0

    @field_validator("related_keywords", mode="before")
    @classmethod
    def _coerce_list(cls, v: object) -> list[str]:
        return [str(x) for x in v] if isinstance(v, list) else []


class BrollSelectorOutput(BaseModel):
    """One b-roll result produced by broll_selector agent."""
    scene_text: str
    suggestions_found: int = 0
    status: str = "ok"

    @field_validator("scene_text", mode="before")
    @classmethod
    def _coerce_str(cls, v: object) -> str:
        return str(v).strip()


class VideoHandoffOutput(BaseModel):
    """Output produced by video_handoff agent."""
    job_id: str
    upload_url: str = ""
    status: str = "pending_video"
    notified: bool = False

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        valid = {"pending_video", "queued", "processing", "done", "failed"}
        return str(v) if str(v) in valid else "pending_video"


class AutoModeEngineOutput(BaseModel):
    """Output produced by auto_mode_engine agent."""
    opportunities_selected: int = 0
    pipelines_triggered: int = 0
    status: str = "success"


class PipelineOrchestratorOutput(BaseModel):
    """Output produced by pipeline_orchestrator agent."""
    opportunity_id: str
    stages_completed: int = 0
    stages_failed: int = 0
    status: str = "success"

    @field_validator("status", mode="before")
    @classmethod
    def _validate_status(cls, v: object) -> str:
        return str(v) if str(v) in {"success", "partial", "failed"} else "success"


class StrategySynthesizerOutput(BaseModel):
    """Output produced by strategy_synthesizer agent."""
    report_id: str
    opportunities_analyzed: int = 0
    recommendations_count: int = 0
    status: str = "success"


class PreferenceLearnerOutput(BaseModel):
    """Output produced by preference_learner agent — one row per content_type."""
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


# ── Aliases for backwards compatibility ───────────────────────────────────────
ArticlePlanOutput = ArticlePlannerOutput
ArticleOutput = ArticleWriterOutput
WordPressPublishOutput = WordPressPublisherOutput
DocumentIngestionOutput = DocumentIngesterOutput
RAGSearchOutput = RagSearcherOutput
ContentDirectorLegacyOutput = ContentDirectorOutput


# ── Sentiment analyser ────────────────────────────────────────────────────────

_VALID_POLARITIES = frozenset({"positive", "negative", "neutral", "mixed"})
_VALID_POLARITY_METHODS = frozenset({"vader", "llm_haiku", "llm_sonnet", "llm_batch"})


class PolarityOutput(BaseModel):
    """LLM polarity classification output — Prompts 1 and 2."""
    polarity: Literal["positive", "negative", "neutral", "mixed"]
    polarity_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(default="", max_length=200)
    contains_sarcasm: bool = False
    is_about_scheme: bool = True

    @field_validator("polarity", mode="before")
    @classmethod
    def _validate_polarity(cls, v: object) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_POLARITIES else "neutral"

    @field_validator("polarity_score", "confidence", mode="before")
    @classmethod
    def _clamp_float(cls, v: object) -> float:
        try:
            return round(float(str(v)), 4)
        except (ValueError, TypeError):
            return 0.0


class BatchPolarityItem(BaseModel):
    """One item in a batch polarity response — Prompt 3."""
    id: str
    polarity: Literal["positive", "negative", "neutral", "mixed"]
    polarity_score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    is_about_scheme: bool = True

    @field_validator("polarity", mode="before")
    @classmethod
    def _validate_polarity(cls, v: object) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_POLARITIES else "neutral"

    @field_validator("polarity_score", "confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(float(str(v)), 4)
        except (ValueError, TypeError):
            return 0.0


class BatchPolarityOutput(BaseModel):
    """Wrapper for batch polarity results — Prompt 3."""
    items: list[BatchPolarityItem] = []


class ThemeMatchItem(BaseModel):
    """One matched theme entry from theme_classifier."""
    theme_key: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_quote: str = ""

    @field_validator("theme_key", mode="before")
    @classmethod
    def _strip(cls, v: object) -> str:
        return str(v).strip().lower()

    @field_validator("confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(1.0, float(str(v)))), 4)
        except (ValueError, TypeError):
            return 0.0


class ThemeClassifierOutput(BaseModel):
    """Output of per-mention theme classifier — Prompt 5."""
    matched_themes: list[ThemeMatchItem] = []
    no_match_reason: str = ""


class PersonMentioned(BaseModel):
    """One person extracted by entity_extractor."""
    name: str
    role_if_stated: str = ""
    polarity_toward: str = "not_evaluative"

    @field_validator("polarity_toward", mode="before")
    @classmethod
    def _validate(cls, v: object) -> str:
        valid = {"positive", "negative", "neutral", "not_evaluative"}
        return str(v) if str(v) in valid else "not_evaluative"


class FactualClaim(BaseModel):
    """One factual claim extracted by entity_extractor."""
    claim: str
    is_verifiable: bool = False
    claim_type: str = "event"
    involves_numbers: bool = False

    @field_validator("claim_type", mode="before")
    @classmethod
    def _validate(cls, v: object) -> str:
        valid = {"statistic", "event", "promise", "accusation", "comparison"}
        return str(v) if str(v) in valid else "event"


class QuotedStatement(BaseModel):
    """One quoted statement extracted by entity_extractor."""
    speaker: str = ""
    quote: str


class EntityExtractorOutput(BaseModel):
    """Entity and claim extraction output — Prompt 6."""
    schemes_mentioned: list[str] = []
    districts_mentioned: list[str] = []
    persons_mentioned: list[PersonMentioned] = []
    factual_claims: list[FactualClaim] = []
    quoted_statements: list[QuotedStatement] = []


class AnalyzedMentionOutput(BaseModel):
    """Result written to analyzed_mentions after Stage 3 processing."""
    relevant_mention_id: str
    polarity: str = "neutral"
    polarity_score: float = 0.0
    polarity_confidence: float = 0.0
    polarity_method: str = "vader"
    contains_sarcasm: bool = False
    themes: list[str] = []
    is_about_scheme: bool = True

    @field_validator("polarity", mode="before")
    @classmethod
    def _validate_polarity(cls, v: object) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_POLARITIES else "neutral"

    @field_validator("polarity_method", mode="before")
    @classmethod
    def _validate_method(cls, v: object) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_POLARITY_METHODS else "vader"

    @field_validator("polarity_score", "polarity_confidence", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(float(str(v)), 4)
        except (ValueError, TypeError):
            return 0.0


class SentimentSignalOutput(BaseModel):
    """One aggregated signal row produced by Stage 4 aggregator."""
    scheme_key: str
    district_key: str
    signal_date: str
    mention_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    mixed_count: int = 0
    avg_polarity_score: float | None = None
    weighted_avg_polarity_score: float | None = None
    dominant_polarity: str = "neutral"
    spike_detected: bool = False

    @field_validator("dominant_polarity", mode="before")
    @classmethod
    def _validate(cls, v: object) -> str:
        s = str(v).lower().strip()
        return s if s in _VALID_POLARITIES else "neutral"

    @field_validator(
        "mention_count", "positive_count", "negative_count",
        "neutral_count", "mixed_count", mode="before"
    )
    @classmethod
    def _coerce_int(cls, v: object) -> int:
        try:
            return max(0, int(v))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


class SpikeDriverItem(BaseModel):
    """One driver item from spike_analyzer output."""
    driver_description: str
    evidence_mention_ids: list[str] = []
    estimated_share_pct: int = Field(ge=0, le=100, default=0)

    @field_validator("estimated_share_pct", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> int:
        try:
            return max(0, min(100, int(v)))  # type: ignore[arg-type]
        except (ValueError, TypeError):
            return 0


_VALID_RESPONSE_TYPES = frozenset({
    "address_concern", "factual_correction",
    "amplify_positive_counter", "monitor_only", "escalate_to_compliance",
})
_VALID_URGENCY = frozenset({"low", "medium", "high", "critical"})


class SpikeAnalyzerOutput(BaseModel):
    """Output from spike_analyzer LLM — Prompt 7."""
    situation_summary: str
    primary_drivers: list[SpikeDriverItem] = []
    is_organic_or_amplified: str = "uncertain"
    amplification_signals: list[str] = []
    recommended_response_type: str = "monitor_only"
    urgency: str = "low"
    rationale_for_urgency: str = ""

    @field_validator("is_organic_or_amplified", mode="before")
    @classmethod
    def _validate_amplified(cls, v: object) -> str:
        return str(v) if str(v) in {"organic", "amplified", "uncertain"} else "uncertain"

    @field_validator("recommended_response_type", mode="before")
    @classmethod
    def _validate_response(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_RESPONSE_TYPES else "monitor_only"

    @field_validator("urgency", mode="before")
    @classmethod
    def _validate_urgency(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_URGENCY else "low"


_VALID_SOURCE_TYPES = frozenset({
    "mainstream_news", "regional_news", "citizen_journalist",
    "social_media_individual", "social_media_amplifier",
    "official_government", "political_party", "ngo_advocacy",
    "blog", "unknown",
})
_VALID_REACH = frozenset({"national", "state", "district", "local", "niche", "unknown"})
_VALID_EDITORIAL = frozenset({"high", "medium", "low", "none", "unknown"})
_VALID_LEAN = frozenset({
    "left", "right", "ruling_party_aligned",
    "opposition_aligned", "independent", "unknown",
})


class SourceCredibilityOutput(BaseModel):
    """Source credibility scoring output — Prompt 8."""
    source_type: str = "unknown"
    estimated_reach: str = "unknown"
    editorial_standards: str = "unknown"
    known_political_lean: str = "unknown"
    credibility_weight: float = Field(ge=0.0, le=1.5, default=1.0)
    reach_weight: float = Field(ge=0.0, le=1.5, default=1.0)
    rationale: str = ""
    requires_human_review: bool = True
    human_review_reason: str = ""

    @field_validator("source_type", mode="before")
    @classmethod
    def _validate_source_type(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_SOURCE_TYPES else "unknown"

    @field_validator("estimated_reach", mode="before")
    @classmethod
    def _validate_reach(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_REACH else "unknown"

    @field_validator("editorial_standards", mode="before")
    @classmethod
    def _validate_editorial(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_EDITORIAL else "unknown"

    @field_validator("known_political_lean", mode="before")
    @classmethod
    def _validate_lean(cls, v: object) -> str:
        return str(v) if str(v) in _VALID_LEAN else "unknown"

    @field_validator("credibility_weight", "reach_weight", mode="before")
    @classmethod
    def _clamp(cls, v: object) -> float:
        try:
            return round(max(0.0, min(1.5, float(str(v)))), 4)
        except (ValueError, TypeError):
            return 1.0
