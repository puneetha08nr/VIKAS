import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class RelevantMention(Base):
    __tablename__ = "relevant_mentions"
    __table_args__ = (
        Index("ix_relevant_mentions_org_id", "org_id"),
        Index("ix_relevant_mentions_raw_mention_id", "raw_mention_id"),
        Index("ix_relevant_mentions_matched_scheme", "matched_scheme"),
        Index("ix_relevant_mentions_matched_district", "matched_district"),
        Index("ix_relevant_mentions_published_at", "published_at"),
        Index("ix_relevant_mentions_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    raw_mention_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("raw_mentions.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    source_identifier: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    body_clean: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    language_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    matched_scheme: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    matched_district: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    vader_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    vader_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    minhash_signature: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending_analysis"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
