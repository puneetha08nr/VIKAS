from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import all models so Alembic autogenerate and Base.metadata see every table.
# keyword_clusters ← keywords circular FK is resolved with use_alter=True in keyword_clusters.py.
from db.models.organizations import Organization  # noqa: E402, F401
from db.models.keyword_clusters import KeywordCluster, SearchIntent  # noqa: E402, F401
from db.models.keywords import Keyword, KeywordStatus  # noqa: E402, F401
from db.models.opportunities import Opportunity, OpportunityStatus  # noqa: E402, F401
from db.models.content_items import ContentItem, ContentFormat, ContentStatus  # noqa: E402, F401
from db.models.content_reviews import ContentReview  # noqa: E402, F401
from db.models.competitors import Competitor  # noqa: E402, F401
from db.models.competitor_content import CompetitorContent  # noqa: E402, F401
from db.models.trend_signals import TrendSignal  # noqa: E402, F401
from db.models.knowledge_chunks import KnowledgeChunk  # noqa: E402, F401
from db.models.brand_voice import BrandVoice  # noqa: E402, F401
from db.models.preferences import Preference, PreferenceSource  # noqa: E402, F401
from db.models.prompts import Prompt  # noqa: E402, F401
from db.models.agent_runs import AgentRun, AgentRunStatus  # noqa: E402, F401
from db.models.pipeline_runs import PipelineRun, PipelineRunStatus  # noqa: E402, F401
from db.models.eval_log import EvalLog  # noqa: E402, F401

__all__ = [
    "Base",
    "Organization",
    "KeywordCluster", "SearchIntent",
    "Keyword", "KeywordStatus",
    "Opportunity", "OpportunityStatus",
    "ContentItem", "ContentFormat", "ContentStatus",
    "ContentReview",
    "Competitor",
    "CompetitorContent",
    "TrendSignal",
    "KnowledgeChunk",
    "BrandVoice",
    "Preference", "PreferenceSource",
    "Prompt",
    "AgentRun", "AgentRunStatus",
    "PipelineRun", "PipelineRunStatus",
    "EvalLog",
]
