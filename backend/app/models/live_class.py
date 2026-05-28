"""
Live Class models — Phase 19B (Zoom integration).

LiveClassSession  — one scheduled Zoom meeting, linked to a LearningSpace.
LiveClassAttendance — one participant row per session (imported after class ends).
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .space import LearningSpace
    from .tenant import Tenant
    from .content import ContentItem
    from .user import AxisUser


class LiveClassStatus:
    SCHEDULED = "scheduled"
    LIVE = "live"
    ENDED = "ended"
    IMPORTED = "imported"
    CANCELLED = "cancelled"
    FAILED = "failed"


class LiveClassSession(Base):
    """One scheduled Zoom (or future Meet) live class per row."""
    __tablename__ = "live_class_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Provider: 'zoom' | 'google_meet'
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="zoom")

    # External provider IDs
    external_meeting_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    external_meeting_uuid: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Meeting details
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    # URLs (populated after meeting is created in Zoom)
    join_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    host_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # State: scheduled → live → ended → imported | cancelled | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=LiveClassStatus.SCHEDULED)

    # Per-class config toggles
    auto_record: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    import_recording: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    import_attendance: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    generate_ai_outputs: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notify_learners: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Post-class — filled in after import completes
    content_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    recording_local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recording_duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    actual_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    participant_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Error tracking
    import_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Creator info
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"),
        onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    attendance: Mapped[list["LiveClassAttendance"]] = relationship(
        "LiveClassAttendance", back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<LiveClassSession {self.title!r} [{self.status}] @ {self.scheduled_at}>"


class LiveClassAttendance(Base):
    """One participant row per session — imported from Zoom after the class ends."""
    __tablename__ = "live_class_attendance"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("live_class_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zoom participant identifiers
    participant_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # Zoom user_id (registered)
    user_email: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # Timing
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Zoom-specific metrics
    attentiveness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Full raw payload from Zoom API (for future use)
    raw_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
    )

    # Relationships
    session: Mapped["LiveClassSession"] = relationship("LiveClassSession", back_populates="attendance")

    def __repr__(self) -> str:
        return f"<LiveClassAttendance {self.user_email} session={self.session_id}>"
