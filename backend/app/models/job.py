"""
ProcessingJob — tracks every background job, its status, and progress.
"""
import uuid
import enum

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class JobType(str, enum.Enum):
    FULL_PIPELINE = "full_pipeline"       # extract + embed + all generators
    EXTRACT_ONLY = "extract_only"         # just extraction + embedding
    GENERATE_OUTPUTS = "generate_outputs" # run generators on already-extracted content
    TRANSLATE = "translate"               # translation job
    REGENERATE = "regenerate"             # rerun specific output with new prompt version
    KB_INGEST = "kb_ingest"              # KB/support document ingestion
    STRUCTURED_INGEST = "structured_ingest"  # SCORM pre-extracted JSON → embed + generate


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


class ProcessingJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One row per background job.
    Celery task ID links this to the actual Celery task for status sync.
    """

    __tablename__ = "processing_jobs"

    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=True,   # NULL for KB_INGEST and STRUCTURED_INGEST jobs
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    job_type: Mapped[JobType] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[JobStatus] = mapped_column(
        String(20), default=JobStatus.QUEUED, nullable=False, index=True
    )

    # Celery task ID — used to query Celery for live status
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # 0-100 progress percentage
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Current step description (e.g., "Extracting PDF text", "Generating quiz")
    progress_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Timing
    started_at: Mapped[str | None] = mapped_column(nullable=True)
    completed_at: Mapped[str | None] = mapped_column(nullable=True)

    # Error details on failure
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Job configuration: which outputs were requested, options, etc.
    job_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    content_item: Mapped["ContentItem"] = relationship(  # noqa: F821
        "ContentItem", back_populates="jobs"
    )

    def __repr__(self) -> str:
        return (
            f"<ProcessingJob {self.job_type} "
            f"status={self.status} progress={self.progress}%>"
        )
