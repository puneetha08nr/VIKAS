import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class SchemePattern(Base):
    __tablename__ = "scheme_patterns"
    __table_args__ = (
        Index("ix_scheme_patterns_org_id", "org_id"),
        Index("ix_scheme_patterns_scheme_key", "scheme_key"),
        Index("ix_scheme_patterns_period_start", "period_start"),
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
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    total_mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    net_polarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    dominant_themes: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    top_districts: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    velocity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    trend_direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stable"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
