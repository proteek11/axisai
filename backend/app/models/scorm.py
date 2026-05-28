"""
SCORM models — scorm_packages and scorm_sessions.

scorm_packages: metadata parsed from imsmanifest.xml, one per ContentItem.
scorm_sessions: per-learner per-attempt runtime cmi.* state.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .content import ContentItem
    from .user import AxisUser
    from .space import LearningSpace


class ScormPackage(Base):
    """
    Metadata for a SCORM package, one row per ContentItem of type 'scorm'.
    Populated at upload time by parsing imsmanifest.xml.
    """
    __tablename__ = "scorm_packages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    scorm_version: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="'1.2' | '2004_3' | '2004_4'",
    )
    entry_point: Mapped[str] = mapped_column(
        String(500), nullable=False,
        comment="Relative path to launch file, e.g. 'story.html'",
    )
    package_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    sco_list: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    manifest_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    file_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    package_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    passing_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_time_allowed: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    content_item: Mapped["ContentItem"] = relationship("ContentItem")

    def __repr__(self) -> str:
        return f"<ScormPackage content_item={self.content_item_id} version={self.scorm_version}>"


class ScormSession(Base):
    """
    Per-learner per-attempt SCORM runtime state.

    One row per (content_item, user, space, attempt_number).
    cmi_data stores the full cmi.* snapshot updated on every LMSCommit().
    Mirrored top-level fields (completion_status, score_raw etc.) enable
    fast SQL queries for reports without parsing JSONB.
    """
    __tablename__ = "scorm_sessions"
    __table_args__ = (
        sa.UniqueConstraint(
            "content_item_id", "user_id", "space_id", "attempt_number",
            name="uq_scorm_session_attempt",
        ),
    )

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
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # ── Mirrored status fields (synced from cmi_data on every commit) ────────
    completion_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_attempted",
        comment="not_attempted | incomplete | completed | unknown",
    )
    success_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown",
        comment="passed | failed | unknown",
    )
    score_raw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_min: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_max: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_scaled: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Resume data ───────────────────────────────────────────────────────────
    lesson_location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    suspend_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cmi_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    content_item: Mapped["ContentItem"] = relationship("ContentItem")
    user: Mapped["AxisUser"] = relationship("AxisUser")
    space: Mapped["LearningSpace"] = relationship("LearningSpace")

    def __repr__(self) -> str:
        return (
            f"<ScormSession content={self.content_item_id} "
            f"user={self.user_id} attempt={self.attempt_number} "
            f"status={self.completion_status}>"
        )
