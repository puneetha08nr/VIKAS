from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic autogenerate and Base.metadata see every table.
# keyword_clusters ← keywords circular FK is resolved with use_alter=True in keyword_clusters.py.
from db.models.aeo_results import AeoResult  # noqa: E402, F401
from db.models.agent_runs import AgentRun, AgentRunStatus  # noqa: E402, F401
from db.models.analyzed_mentions import AnalyzedMention  # noqa: E402, F401
from db.models.brand_voice import BrandVoice  # noqa: E402, F401
from db.models.competitor_content import CompetitorContent  # noqa: E402, F401
from db.models.competitors import Competitor  # noqa: E402, F401
from db.models.content_feedback import ContentFeedback  # noqa: E402, F401
from db.models.content_items import ContentFormat, ContentItem, ContentStatus  # noqa: E402, F401
from db.models.content_reviews import ContentReview  # noqa: E402, F401
from db.models.district_patterns import DistrictPattern  # noqa: E402, F401
from db.models.eval_log import EvalLog  # noqa: E402, F401
from db.models.keyword_clusters import KeywordCluster, SearchIntent  # noqa: E402, F401
from db.models.keywords import Keyword, KeywordStatus  # noqa: E402, F401
from db.models.knowledge_chunks import KnowledgeChunk  # noqa: E402, F401
from db.models.opportunities import Opportunity, OpportunityStatus  # noqa: E402, F401
from db.models.organizations import Organization  # noqa: E402, F401
from db.models.pipeline_runs import PipelineRun, PipelineRunStatus  # noqa: E402, F401
from db.models.preference_summaries import PreferenceSummary  # noqa: E402, F401
from db.models.preferences import Preference, PreferenceSource  # noqa: E402, F401
from db.models.prompts import Prompt  # noqa: E402, F401
from db.models.raw_mentions import RawMention  # noqa: E402, F401
from db.models.relevant_mentions import RelevantMention  # noqa: E402, F401
from db.models.scheme_patterns import SchemePattern  # noqa: E402, F401
from db.models.sentiment_signals import SentimentSignal  # noqa: E402, F401
from db.models.source_credibility import SourceCredibility  # noqa: E402, F401
from db.models.theme_taxonomy import ThemeTaxonomy  # noqa: E402, F401
from db.models.topics import Topic  # noqa: E402, F401
from db.models.trend_signals import TrendSignal  # noqa: E402, F401
from db.models.video_jobs import VideoJob  # noqa: E402, F401

__all__ = [
    "Base",
    "AeoResult",
    "ContentFeedback",
    "PreferenceSummary",
    "Organization",
    "KeywordCluster", "SearchIntent",
    "Keyword", "KeywordStatus",
    "Opportunity", "OpportunityStatus",
    "ContentItem", "ContentFormat", "ContentStatus",
    "ContentReview",
    "Competitor",
    "CompetitorContent",
    "Topic",
    "TrendSignal",
    "VideoJob",
    "KnowledgeChunk",
    "BrandVoice",
    "Preference", "PreferenceSource",
    "Prompt",
    "AgentRun", "AgentRunStatus",
    "PipelineRun", "PipelineRunStatus",
    "EvalLog",
    "RawMention",
    "RelevantMention",
    "AnalyzedMention",
    "SentimentSignal",
    "SchemePattern",
    "DistrictPattern",
    "ThemeTaxonomy",
    "SourceCredibility",
]
