import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from db.models import Base


class SearchIntent(enum.StrEnum):
    informational = "informational"
    navigational = "navigational"
    commercial = "commercial"
    transactional = "transactional"


class KeywordCluster(Base):
    __tablename__ = "keyword_clusters"
    __table_args__ = (Index("ix_keyword_clusters_org_id", "org_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    intent: Mapped[SearchIntent] = mapped_column(
        SAEnum(SearchIntent, name="search_intent", native_enum=True), nullable=False
    )
    # use_alter breaks the circular FK with keywords at DDL time
    primary_keyword_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "keywords.id",
            use_alter=True,
            name="fk_keyword_clusters_primary_keyword_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
