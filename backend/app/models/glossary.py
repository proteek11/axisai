"""GlossaryTerm model — dedicated pool table for glossary entries.

Replaces the JSON blob approach (ai_outputs.payload.terms) with proper rows
so teachers can add, edit, and delete individual terms, and regeneration can
produce additional terms without duplicating existing ones.
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class GlossaryTerm(Base):
    __tablename__ = "glossary_terms"

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
    # Nullable — NULL when source='manual'
    ai_output_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ai_outputs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Term content ──────────────────────────────────────────────────────────
    term = Column(String(255), nullable=False, index=True)
    definition = Column(Text, nullable=False)
    # Example sentence showing the term in context (from source material)
    context = Column(Text, nullable=True)
    # List of related term strings e.g. ["TCP/IP", "UDP"]
    related_terms = Column(JSONB, nullable=True)
    # concept | process | tool | formula | principle | other
    category = Column(String(50), nullable=True)

    # ── Pool management ───────────────────────────────────────────────────────
    # generated | manual
    source = Column(String(20), nullable=False, default="generated")
    # 1 = first generation, 2 = first regenerate, …
    generation_batch = Column(Integer, nullable=False, default=1)
    # Teacher can hide specific terms without deleting them
    is_active = Column(Boolean, nullable=False, default=True)

    # ── Manual entry tracking ─────────────────────────────────────────────────
    manually_added_by = Column(BigInteger, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    content_item = relationship("ContentItem", back_populates="glossary_terms")

    def __repr__(self) -> str:
        return f"<GlossaryTerm id={self.id} term={self.term!r} source={self.source}>"
