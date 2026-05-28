"""FlashcardItem model — dedicated pool table for flashcard items.

Replaces the JSON blob approach (ai_outputs.payload.cards) with proper rows
so we can: query, dedup, add/edit/delete individual cards, track pool size,
and enforce per-content max caps.
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class FlashcardItem(Base):
    __tablename__ = "flashcard_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable — NULL when source='manual' (no AI output produced it)
    ai_output_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_outputs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Card content ──────────────────────────────────────────────────────────
    front = Column(Text, nullable=False)
    back = Column(Text, nullable=False)
    hint = Column(Text, nullable=True)
    # definition | application | comparison | cause_effect | process
    card_type = Column(String(50), nullable=True)
    # easy | medium | hard
    difficulty = Column(String(20), nullable=True)
    topic = Column(String(255), nullable=True)

    # ── Pool management ───────────────────────────────────────────────────────
    # generated | manual
    source = Column(String(20), nullable=False, default="generated")
    # 1 = first generation, 2 = first regenerate, 3 = second regenerate, …
    generation_batch = Column(Integer, nullable=False, default=1)
    # Teacher can disable specific cards without deleting them
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Manual entry tracking ─────────────────────────────────────────────────
    # Set to moodle_user_id when source='manual'
    manually_added_by = Column(BigInteger, nullable=True)

    # ── Qdrant reference ──────────────────────────────────────────────────────
    # Stored after embedding into axis_question_intelligence collection.
    # Used for semantic deduplication on regenerate.
    qdrant_id = Column(UUID(as_uuid=True), nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    content_item = relationship("ContentItem", back_populates="flashcard_items")

    def __repr__(self) -> str:
        return f"<FlashcardItem id={self.id} source={self.source} batch={self.generation_batch}>"
