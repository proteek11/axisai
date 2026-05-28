"""
PDFAnnotation — a learner's highlight, underline, or note on an Interactive PDF page.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .content import ContentItem
    from .user import AxisUser


class PDFAnnotation(Base):
    __tablename__ = "pdf_annotations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 1-based page number
    page_num: Mapped[int] = mapped_column(Integer, nullable=False)

    # 'highlight' | 'note' | 'underline'
    annotation_type: Mapped[str] = mapped_column(String(20), nullable=False, default="highlight")

    # Selected text (for highlights/underlines) or note body
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # pdf.js position data: {x, y, width, height, rects: [{x1,y1,x2,y2},...]}
    position_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Hex colour for highlights, e.g. "#FFF176"
    color: Mapped[str] = mapped_column(String(7), nullable=False, default="#FFF176")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped["AxisUser"] = relationship("AxisUser", foreign_keys=[user_id])
    content_item: Mapped["ContentItem"] = relationship("ContentItem", foreign_keys=[content_item_id])

    def __repr__(self) -> str:
        return (
            f"<PDFAnnotation user={self.user_id} "
            f"content={self.content_item_id} page={self.page_num} type={self.annotation_type}>"
        )
