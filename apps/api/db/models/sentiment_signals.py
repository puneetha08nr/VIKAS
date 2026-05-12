import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class SentimentSignal(Base):
    __tablename__ = "sentiment_signals"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "scheme_key", "district_key", "signal_date", "window_hours",
            name="uq_sentiment_signals_key",
        ),
        Index("ix_sentiment_signals_org_id", "org_id"),
        Index("ix_sentiment_signals_scheme_key", "scheme_key"),
        Index("ix_sentiment_signals_district_key", "district_key"),
        Index("ix_sentiment_signals_signal_date", "signal_date"),
        Index("ix_sentiment_signals_spike_detected", "spike_detected"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    scheme_key: Mapped[str] = mapped_column(String(200), nullable=False)
    district_key: Mapped[str] = mapped_column(String(200), nullable=False)
    signal_date: Mapped[date] = mapped_column(Date, nullable=False)
    window_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weighted_mention_count: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mixed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_polarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    weighted_avg_polarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    dominant_polarity: Mapped[str] = mapped_column(String(20), nullable=False, default="neutral")
    dominant_themes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    spike_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    spike_analysis: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
