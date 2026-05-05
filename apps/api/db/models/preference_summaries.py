import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class PreferenceSummary(Base):
    """Key-value store for aggregated preference signals per org.

    Written by preference_learner after processing content_feedback rows.
    The existing `preferences` table stores individual learned patterns;
    this table stores rolled-up summary stats (approval_rate, edit themes, etc.)
    so they can be injected into future agent prompts without re-aggregating.
    """

    __tablename__ = "preference_summaries"
    __table_args__ = (
        Index("ix_preference_summaries_org_id", "org_id"),
        UniqueConstraint("org_id", "preference_key", name="uq_preference_summaries_org_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    preference_key: Mapped[str] = mapped_column(String(100), nullable=False)
    preference_value: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
