import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class SourceCredibility(Base):
    __tablename__ = "source_credibility"
    __table_args__ = (
        UniqueConstraint("org_id", "source_identifier", name="uq_source_credibility_org_source"),
        Index("ix_source_credibility_org_id", "org_id"),
        Index("ix_source_credibility_requires_review", "requires_human_review"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_identifier: Mapped[str] = mapped_column(String(500), nullable=False)
    source_handle: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    estimated_reach: Mapped[str] = mapped_column(String(30), nullable=False, default="unknown")
    editorial_standards: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    known_political_lean: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unknown"
    )
    credibility_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    reach_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_review_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    scored_by: Mapped[str] = mapped_column(String(20), nullable=False, default="llm")
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
