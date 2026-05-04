import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class KeywordStatus(enum.StrEnum):
    raw = "raw"
    validated = "validated"
    clustered = "clustered"
    archived = "archived"


class Keyword(Base):
    __tablename__ = "keywords"
    __table_args__ = (
        Index("ix_keywords_org_id", "org_id"),
        Index("ix_keywords_cluster_id", "cluster_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(String(500), nullable=False)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpc: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("keyword_clusters.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[KeywordStatus] = mapped_column(
        SAEnum(KeywordStatus, name="keyword_status", native_enum=True),
        nullable=False,
        default=KeywordStatus.raw,
    )
    source_agent: Mapped[str] = mapped_column(String(100), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    data_source: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default="llm_estimate"
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
