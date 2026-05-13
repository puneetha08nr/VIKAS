import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class AnalyzedMention(Base):
    __tablename__ = "analyzed_mentions"
    __table_args__ = (
        Index("ix_analyzed_mentions_org_id", "org_id"),
        Index("ix_analyzed_mentions_relevant_mention_id", "relevant_mention_id"),
        Index("ix_analyzed_mentions_polarity", "polarity"),
        Index("ix_analyzed_mentions_matched_scheme", "matched_scheme"),
        Index("ix_analyzed_mentions_matched_district", "matched_district"),
        Index("ix_analyzed_mentions_analyzed_at", "analyzed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    relevant_mention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("relevant_mentions.id", ondelete="CASCADE"),
        nullable=False,
    )
    matched_scheme: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    matched_district: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    polarity: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    polarity_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    polarity_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    polarity_method: Mapped[str] = mapped_column(String(30), nullable=False, default="vader")
    contains_sarcasm: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_about_scheme: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    themes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    theme_confidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    entities: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
