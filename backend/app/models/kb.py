"""
KnowledgeBaseItem model — admin-uploaded documents for the Support chatbot.

These are NOT course content. They are institution-wide support documents:
help guides, password-reset instructions, policies, how-to PDFs, etc.

When a chat session is started with chat_mode="support", RAG searches
axis_kb_chunks instead of axis_content_chunks.

Vector storage: axis_kb_chunks Qdrant collection
  payload keys: tenant_id, kb_item_id, doc_type, chunk_index, text, title
"""
import uuid
import enum

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KBDocType(str, enum.Enum):
    SUPPORT = "support"          # General support / help desk
    POLICY = "policy"            # Institutional policies
    HOW_TO = "how_to"            # Step-by-step guides
    FAQ = "faq"                  # Pre-written FAQ docs
    ANNOUNCEMENT = "announcement"  # General announcements
    OTHER = "other"


class KBItemStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"
    DELETED = "deleted"


class KnowledgeBaseItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A single admin-uploaded document in the support knowledge base.

    Admin uploads PDF/URL → Moodle plugin calls POST /api/v1/kb/ingest
    → this record is created → Celery processes it → vectors stored in
    axis_kb_chunks with kb_item_id payload for filtering.

    When status=READY, the KB document is searchable in support chat.
    When status=DELETED, vectors are removed from Qdrant (soft-delete first).
    """

    __tablename__ = "kb_items"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # ── Document identity ─────────────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    doc_type: Mapped[str] = mapped_column(
        String(30), default=KBDocType.SUPPORT.value, nullable=False, index=True
    )
    source_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="URL if ingested via URL; null if uploaded file"
    )
    file_path: Mapped[str | None] = mapped_column(
        String(2048), nullable=True,
        comment="Server file path if uploaded; null if URL-based"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="SHA-256 of the source content for change detection"
    )

    # ── Processing ────────────────────────────────────────────────────────────
    status: Mapped[str] = mapped_column(
        String(20), default=KBItemStatus.PENDING.value, nullable=False, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Visibility ────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True,
        comment="Admin can deactivate without deleting vectors"
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    uploaded_by_moodle_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Moodle user ID of the admin who uploaded this document"
    )
    processing_metadata: Mapped[dict] = mapped_column(
        JSONB, default=dict, nullable=False,
        comment="Language detected, page count, processing config, etc."
    )

    def __repr__(self) -> str:
        return f"<KBItem {self.title[:40]} ({self.doc_type}, {self.status})>"
