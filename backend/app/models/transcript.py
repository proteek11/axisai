"""
Transcript model — video/audio transcripts with language variants.
First-class table so transcripts are queryable and reusable for translation.
"""
import uuid
import enum

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TranscriptSource(str, enum.Enum):
    API_CAPTIONS = "api_captions"   # YouTube/Vimeo caption API
    WHISPER_LOCAL = "whisper_local" # Local OpenAI Whisper model
    WHISPER_API = "whisper_api"     # OpenAI Whisper API
    MANUAL = "manual"               # Human-provided
    TRANSLATED = "translated"       # Auto-translated from another language


class Transcript(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Video/audio transcript in a specific language.

    segments: [{"start": 0.0, "end": 5.2, "text": "Hello..."}, ...]
    Stored as JSONB for flexibility — SRT, VTT, or raw segments all normalize to this.

    UNIQUE(content_item_id, language) — one transcript per language per content item.
    """

    __tablename__ = "transcripts"
    __table_args__ = (
        UniqueConstraint("content_item_id", "language", name="uq_transcript_lang"),
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    language: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[TranscriptSource] = mapped_column(String(20), nullable=False)

    # Full text (for embedding and search)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamped segments for interactive transcript UI
    segments: Mapped[list] = mapped_column(
        JSONB, default=list, nullable=False,
        comment="[{start_sec, end_sec, text}]"
    )

    # Source language before translation (if this is a translated transcript)
    translated_from: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Relationships
    content_item: Mapped["ContentItem"] = relationship(  # noqa: F821
        "ContentItem", back_populates="transcripts"
    )

    def __repr__(self) -> str:
        return (
            f"<Transcript lang={self.language} "
            f"source={self.source} words={self.word_count}>"
        )
