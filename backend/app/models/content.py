"""
ContentItem — the central anchor for everything in the system.

Supports two origins:
  • 'moodle'  — created by the Moodle edzaiaxisfront plugin.
                Identified by (tenant_id, moodle_cmid).
  • 'space'   — created by the standalone Next.js frontend.
                Identified by (tenant_id, asset_id), linked to a LearningSpace.

The dual-origin design keeps the Moodle pipeline 100% unchanged while
allowing the standalone frontend to upload content without Moodle dependencies.
"""
import uuid
import enum
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .job import ProcessingJob
    from .output import AIOutput, QuizQuestion
    from .transcript import Transcript
    from .audit import AuditLog
    from .flashcard import FlashcardItem
    from .glossary import GlossaryTerm
    from .space import LearningSpace


class ContentType(str, enum.Enum):
    PDF = "pdf"
    TEXT = "text"
    YOUTUBE = "youtube"
    VIMEO = "vimeo"
    PEERTUBE = "peertube"
    SCORM = "scorm"
    H5P = "h5p"
    HTML_PAGE = "html_page"
    ZOOM = "zoom"
    ASSIGNMENT = "assignment"
    VIDEO_UPLOAD = "video_upload"
    AUDIO = "audio"
    INTERACTIVE_PDF = "interactive_pdf"
    INTERACTIVE_SLIDES = "interactive_slides"
    UNKNOWN = "unknown"


class ContentStatus(str, enum.Enum):
    PENDING = "pending"          # Created, not yet processed
    PROCESSING = "processing"    # Currently being processed
    READY = "ready"              # Fully processed, outputs available
    FAILED = "failed"            # Processing failed
    STALE = "stale"              # Content changed (hash mismatch), needs reprocessing


class ContentOrigin(str, enum.Enum):
    MOODLE = "moodle"   # Created via Moodle plugin (uses moodle_course_id + moodle_cmid)
    SPACE  = "space"    # Created via standalone frontend (uses space_id + asset_id)


class ContentItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Master record for every piece of ingested content.

    Key design decisions:
    - origin discriminates between Moodle-sourced and standalone-sourced content.
    - For Moodle content:   moodle_cmid is the dedup key (UNIQUE partial index).
    - For space content:    asset_id is the dedup key (UNIQUE partial index).
    - Partial unique indexes replace the old hard UNIQUE(tenant_id, moodle_cmid)
      so that NULL moodle_cmid rows (space-origin) don't collide.
    - Qdrant chunk IDs are derived from (tenant_id, content_item_id, chunk_index,
      content_hash) — origin-agnostic and upsert-safe.
    """

    __tablename__ = "content_items"
    __table_args__ = (
        # Partial unique index: Moodle dedup — one cmid per tenant, NULLs excluded
        Index(
            "uix_tenant_moodle_cmid",
            "tenant_id", "moodle_cmid",
            unique=True,
            postgresql_where=sa_text("moodle_cmid IS NOT NULL"),
        ),
        # Partial unique index: standalone dedup — one asset_id per tenant, NULLs excluded
        Index(
            "uix_tenant_asset_id",
            "tenant_id", "asset_id",
            unique=True,
            postgresql_where=sa_text("asset_id IS NOT NULL"),
        ),
    )

    # ── Origin discriminator ──────────────────────────────────────────────────
    origin: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=ContentOrigin.MOODLE.value,
        index=True,
        comment="'moodle' = created via Moodle plugin; 'space' = standalone frontend",
    )

    # ── Tenant ────────────────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Moodle origin fields (nullable for space-origin content) ──────────────
    moodle_course_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="Moodle course ID. NULL for space-origin content.",
    )
    moodle_cmid: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, index=True,
        comment="Moodle course module ID. Unique per tenant (partial index). NULL for space-origin.",
    )
    moodle_section_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # ── Standalone (space) origin fields (nullable for Moodle-origin content) ─
    space_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Learning Space this content belongs to. NULL for moodle-origin content.",
    )
    asset_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
        comment="Unique upload ID for space-origin content (replaces moodle_cmid). NULL for moodle-origin.",
    )

    # ── Content metadata ──────────────────────────────────────────────────────
    content_type: Mapped[ContentType] = mapped_column(
        String(20), nullable=False, index=True
    )
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)

    # ── Change detection ──────────────────────────────────────────────────────
    content_hash: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, index=True,
        comment="SHA256 of raw source. Changed hash triggers reprocessing.",
    )

    # ── Processing state ──────────────────────────────────────────────────────
    status: Mapped[ContentStatus] = mapped_column(
        String(20), default=ContentStatus.PENDING, nullable=False, index=True
    )
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    # ── Generation count settings ────────────────────────────────────────────
    quiz_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    flashcard_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # ── Processing config ─────────────────────────────────────────────────────
    processing_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # ── Extra metadata ────────────────────────────────────────────────────────
    moodle_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # ── LXP Catalogue fields (Phase 16) ──────────────────────────────────────
    is_public: Mapped[bool] = mapped_column(
        Boolean(),
        default=False,
        nullable=False,
        comment="True = visible to all creators in tenant. False = creator-only.",
    )
    experience_mode: Mapped[str] = mapped_column(
        String(20),
        default="standard",
        nullable=False,
        comment="standard = AI output tabs. interactive = embedded interactions.",
    )
    creator_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="AxisUser who added this content to the library.",
    )

    # ── Interactive content (Phase 14) ────────────────────────────────────────
    # List of MCQ / True-False / Callout objects keyed by timestamp.
    interactions: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # PPTX slide image paths: [{index, path, thumbnail_path}]
    slide_assets: Mapped[list] = mapped_column(JSONB, default=list, nullable=True)
    interaction_responses: Mapped[list["InteractionResponse"]] = relationship(
        "InteractionResponse", back_populates="content_item", cascade="all, delete-orphan"
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="content_items")
    space: Mapped[Optional["LearningSpace"]] = relationship(
        "LearningSpace",
        foreign_keys=[space_id],
        back_populates="direct_content_items",
    )
    jobs: Mapped[list["ProcessingJob"]] = relationship(
        "ProcessingJob", back_populates="content_item", cascade="all, delete-orphan"
    )
    ai_outputs: Mapped[list["AIOutput"]] = relationship(
        "AIOutput", back_populates="content_item", cascade="all, delete-orphan"
    )
    quiz_questions: Mapped[list["QuizQuestion"]] = relationship(
        "QuizQuestion", back_populates="content_item", cascade="all, delete-orphan"
    )
    transcripts: Mapped[list["Transcript"]] = relationship(
        "Transcript", back_populates="content_item", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="content_item"
    )
    flashcard_items: Mapped[list["FlashcardItem"]] = relationship(
        "FlashcardItem", back_populates="content_item", cascade="all, delete-orphan"
    )
    glossary_terms: Mapped[list["GlossaryTerm"]] = relationship(
        "GlossaryTerm", back_populates="content_item", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        if self.origin == ContentOrigin.MOODLE.value:
            return f"<ContentItem origin=moodle cmid={self.moodle_cmid} type={self.content_type} status={self.status}>"
        return f"<ContentItem origin=space asset_id={self.asset_id} type={self.content_type} status={self.status}>"


class ExtractedContent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Raw extracted text before chunking.
    Stored separately so we can re-chunk without re-extracting.
    """

    __tablename__ = "extracted_content"

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    extraction_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    content_item: Mapped["ContentItem"] = relationship("ContentItem")

    def __repr__(self) -> str:
        return f"<ExtractedContent content_item={self.content_item_id} words={self.word_count}>"


class UserContentProgress(Base):
    """
    Content-level completion tracking — Phase 16 LXP.

    Tracks a learner's progress through a ContentItem independently of any space.
    A single record per (user, content_item). Completed content is marked done
    across all spaces where it appears.
    """
    __tablename__ = "user_content_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "content_item_id", name="uq_user_content_progress"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    progress_pct: Mapped[float] = mapped_column(sa.Float(), default=0.0, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completion_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    def __repr__(self) -> str:
        return f"<UserContentProgress user={self.user_id} content={self.content_item_id} pct={self.progress_pct}>"
