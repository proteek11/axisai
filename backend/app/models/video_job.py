"""
VideoJob — tracks every video creation job dispatched from Moodle plugin local_edzaxisvideo.

Kept entirely separate from ProcessingJob to avoid polluting the content-intelligence
pipeline with video-specific fields (duration, output_url, provider_used, etc.).

Status lifecycle (full):
  Standard path  : queued → processing → done | failed
  Preview path   : queued → processing → preview_pending → preview_ready → approved
                   → processing (full render) → done | failed
  Draft (future) : draft → queued → …
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# ── Enums ─────────────────────────────────────────────────────────────────────

class VideoJobStatus(str, enum.Enum):
    # Standard render flow
    QUEUED          = "queued"
    PROCESSING      = "processing"
    DONE            = "done"
    FAILED          = "failed"

    # Preview / approval flow (Step 10)
    DRAFT           = "draft"           # created but not yet dispatched
    PREVIEW_PENDING = "preview_pending" # 30-s preview render in queue
    PREVIEW_READY   = "preview_ready"   # preview available at preview_url
    APPROVED        = "approved"        # human approved; full render can proceed


# All valid video types — mirrors local_edzaxisvideo/templates.php
VIDEO_TYPES: frozenset[str] = frozenset({
    "stockfootage", "avatar", "explainer", "whiteboard", "kinetic",
    "motion", "illustrative", "slideshow", "presentation", "screencast",
    # Step 7 — 2-3 character scripted dialogue
    "conversational",
    # Step 8 — AI picks the best type automatically
    "auto",
})


# ── Model ─────────────────────────────────────────────────────────────────────

class VideoJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One row per video creation job.

    moodle_job_id is the integer PK from local_edzaxisvideo_jobs in Moodle.
    (tenant_id, moodle_job_id) is unique — Moodle only retries after failure.

    provider_used is populated by the Celery task after render so admins can
    audit exactly which vendor processed each job (useful for billing).

    Preview flow (Step 10):
      POST /{id}/preview  → status = preview_pending → Celery generates 30-s clip
                         → status = preview_ready, preview_url populated
      POST /{id}/approve  → status = approved → Celery runs full render
    """

    __tablename__ = "video_jobs"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "moodle_job_id",
            name="uq_video_jobs_tenant_moodle",
        ),
    )

    # ── Tenant isolation ──────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Integer job ID from Moodle's local_edzaxisvideo_jobs table
    moodle_job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # ── Job description ───────────────────────────────────────────────────────
    video_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    script: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # Full settings payload from Moodle, including _resolved_assets URLs
    settings: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Which providers were actually used — stored for audit / cost attribution
    # Example: {"tts": "edge_tts", "stock": "pexels", "avatar": "heygen", "platform": null}
    provider_used: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── Status ────────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20),
        default=VideoJobStatus.QUEUED.value,
        nullable=False,
        index=True,
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_msg: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Output ────────────────────────────────────────────────────────────────
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Step 10 — 30-second preview clip URL (populated before full render)
    preview_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Error ─────────────────────────────────────────────────────────────────
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Moodle callback URL — POSTed when status becomes done or failed
    callback_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Celery task ID for operator troubleshooting
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # ── Timing ────────────────────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<VideoJob type={self.video_type} "
            f"moodle_id={self.moodle_job_id} status={self.status}>"
        )
