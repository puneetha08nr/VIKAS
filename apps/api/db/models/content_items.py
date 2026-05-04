import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class ContentFormat(enum.StrEnum):
    article = "article"
    linkedin = "linkedin"
    twitter = "twitter"
    newsletter = "newsletter"
    video_script = "video_script"
    lead_magnet = "lead_magnet"


class ContentStatus(enum.StrEnum):
    draft = "draft"
    review = "review"
    approved = "approved"
    published = "published"
    rejected = "rejected"


class ContentItem(Base):
    __tablename__ = "content_items"
    __table_args__ = (
        Index("ix_content_items_org_id", "org_id"),
        Index("ix_content_items_opportunity_id", "opportunity_id"),
        Index("ix_content_items_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
    )
    format: Mapped[ContentFormat] = mapped_column(
        SAEnum(ContentFormat, name="content_format", native_enum=True), nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[ContentStatus] = mapped_column(
        SAEnum(ContentStatus, name="content_status", native_enum=True),
        nullable=False,
        default=ContentStatus.draft,
    )
    brand_voice_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    seo_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    published_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
