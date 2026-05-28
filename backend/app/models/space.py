"""
Learning Space models — the core organisational concept for axis.edzlms.com.
A Learning Space is a named container of content items, managed by a creator,
accessible to specific learners or publicly via a share token.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .user import AxisUser
    from .tenant import Tenant
    from .content import ContentItem
    from .team import Team


class LearningSpace(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A Learning Space groups content items for organised study.

    is_published       — creator has made it available to assigned learners
    is_guest_accessible — no login required; accessible via share token URL
    """

    __tablename__ = "learning_spaces"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    creator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_guest_accessible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    space_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    # Relationships
    creator: Mapped["AxisUser"] = relationship("AxisUser", back_populates="created_spaces")
    items: Mapped[list["SpaceItem"]] = relationship(
        "SpaceItem", back_populates="space", cascade="all, delete-orphan",
        order_by="SpaceItem.position",
    )
    access_grants: Mapped[list["SpaceAccess"]] = relationship(
        "SpaceAccess", back_populates="space", cascade="all, delete-orphan"
    )
    share_tokens: Mapped[list["ShareToken"]] = relationship(
        "ShareToken", back_populates="space", cascade="all, delete-orphan"
    )
    direct_content_items: Mapped[list["ContentItem"]] = relationship(
        "ContentItem",
        foreign_keys="ContentItem.space_id",
        back_populates="space",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<LearningSpace '{self.title}' published={self.is_published}>"


class SpaceItem(UUIDPrimaryKeyMixin, Base):
    """
    A content item within a Learning Space.
    position    — display order (0-indexed)
    visible_outputs — which AI output tabs are shown to learners
    """

    __tablename__ = "space_items"
    __table_args__ = (
        UniqueConstraint("space_id", "content_item_id", name="uq_space_content"),
    )

    from sqlalchemy import func
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    section_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    title_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    visible_outputs: Mapped[list] = mapped_column(
        JSONB,
        default=lambda: ["summary", "glossary", "flashcards", "quiz", "infographic"],
        nullable=False,
    )
    # Learner regeneration controls (creator sets per content item in a space)
    allow_learner_regen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_quiz_count: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    max_flashcard_count: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    # ── SCORM-specific per-item config (creator sets when adding to space) ───
    scorm_completion_trigger: Mapped[str] = mapped_column(
        String(32), nullable=False, default="completion_only",
        comment="completion_only | pass_required",
    )
    scorm_max_attempts: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True,
        comment="NULL = unlimited",
    )
    scorm_grade_aggregation: Mapped[str] = mapped_column(
        String(16), nullable=False, default="highest",
        comment="highest | average | latest",
    )

    # Relationships
    space: Mapped["LearningSpace"] = relationship("LearningSpace", back_populates="items")
    content_item: Mapped["ContentItem"] = relationship("ContentItem")

    def __repr__(self) -> str:
        return f"<SpaceItem space={self.space_id} content={self.content_item_id} pos={self.position}>"


class SpaceAccess(UUIDPrimaryKeyMixin, Base):
    """
    Grants access to a Learning Space — either to a specific user OR to a team.
    Exactly one of user_id / team_id must be set (enforced at API layer).

    user_id  → direct individual access
    team_id  → all members of the team get access
    """

    __tablename__ = "space_access"
    __table_args__ = (
        # Prevent duplicate direct-user grants
        UniqueConstraint("space_id", "user_id", name="uq_space_user"),
        # Prevent duplicate team grants
        UniqueConstraint("space_id", "team_id", name="uq_space_team"),
    )

    from sqlalchemy import func
    granted_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable — set for direct user grants
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    # Nullable — set for team grants
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
    )

    space: Mapped["LearningSpace"] = relationship("LearningSpace", back_populates="access_grants")
    user: Mapped["AxisUser | None"] = relationship("AxisUser", foreign_keys=[user_id], back_populates="space_accesses")
    team: Mapped["Team | None"] = relationship("Team", foreign_keys=[team_id])


class ShareToken(UUIDPrimaryKeyMixin, Base):
    """
    URL-safe share token for public/guest access to a Learning Space.
    expires_at = NULL means never expires.
    max_access = NULL means unlimited uses.
    """

    __tablename__ = "share_tokens"

    from sqlalchemy import func
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_access: Mapped[int | None] = mapped_column(Integer, nullable=True)

    space: Mapped["LearningSpace"] = relationship("LearningSpace", back_populates="share_tokens")

    def __repr__(self) -> str:
        return f"<ShareToken space={self.space_id} token={self.token[:8]}...>"
