"""
InteractionResponse — stores each learner's answer to an interactive content question.

One row per attempt (learner can re-attempt on re-watch; first attempt used for scoring).
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Text, text as sa_text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .content import ContentItem
    from .user import AxisUser


class InteractionResponse(Base):
    __tablename__ = "interaction_responses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zero-based index into content_items.interactions array
    interaction_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # The answer submitted: option index as string ("0","1","2","3"), "true", "false"
    selected_answer: Mapped[str] = mapped_column(Text, nullable=False)

    # None for callouts (no correct/wrong)
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Seconds from overlay appearance to submission
    time_taken_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    answered_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa_text("NOW()"),
        nullable=False,
    )

    # ── Relationships ──────────────────────────────────────────────────────────
    content_item: Mapped["ContentItem"] = relationship(
        "ContentItem", back_populates="interaction_responses"
    )
    user: Mapped["AxisUser"] = relationship("AxisUser")

    # ── Indexes ────────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_interaction_responses_content_user", "content_item_id", "user_id"),
    )
