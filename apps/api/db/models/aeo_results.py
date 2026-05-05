import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class AeoResult(Base):
    __tablename__ = "aeo_results"
    __table_args__ = (
        Index("ix_aeo_results_org_id", "org_id"),
        Index("ix_aeo_results_keyword_id", "keyword_id"),
        Index("ix_aeo_results_scanned_at", "scanned_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keywords.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    ai_overview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    featured_snippet: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paa_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    organic_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="found"
    )  # "found" | "not_found" | "blocked"
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
