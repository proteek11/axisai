"""
Audit log — immutable record of every single AI call made by the system.
The ground truth for token usage, cost, and debugging.
"""
import uuid
import enum

from sqlalchemy import (
    BigInteger, Float, ForeignKey, Integer, Numeric, String, Text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AuditStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"


class AuditLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Immutable record of every AI API call.
    Written once, never updated. The financial and debugging source of truth.

    Indexed heavily for the admin dashboard queries:
    - by tenant (billing)
    - by provider+model (cost analysis)
    - by task_type (usage breakdown)
    - by moodle_course_id (course-level reporting)
    - by moodle_user_id (user-level rate limiting)
    - by created_at (time-window queries)
    """

    __tablename__ = "audit_logs"

    # ── Context ───────────────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Set when call originated from chatbot"
    )

    # ── Moodle context (denormalized for fast reporting without joins) ─────────
    moodle_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moodle_course_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moodle_cmid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # ── AI call details ────────────────────────────────────────────────────────
    provider: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True,
        comment="summary|quiz|flashcards|embed|translate|chat|..."
    )

    # ── Token & cost tracking ─────────────────────────────────────────────────
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(12, 8), nullable=True,
        comment="Estimated cost in USD based on provider pricing"
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Status ─────────────────────────────────────────────────────────────────
    status: Mapped[AuditStatus] = mapped_column(
        String(20), default=AuditStatus.SUCCESS, nullable=False, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Provider tracking ─────────────────────────────────────────────────────
    provider_request_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="The request ID returned by the AI provider (for support tickets)"
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="audit_logs")  # noqa: F821
    content_item: Mapped["ContentItem"] = relationship(  # noqa: F821
        "ContentItem", back_populates="audit_logs"
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog {self.provider}/{self.model} "
            f"task={self.task_type} tokens={self.total_tokens} "
            f"status={self.status}>"
        )
