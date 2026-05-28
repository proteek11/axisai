"""
SpaceCertificate — issued when a learner completes all required items in a Learning Space.

One row per (user, space) — unique constraint ensures no duplicates.
Re-issuing overwrites the existing record.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .user import AxisUser
    from .space import LearningSpace
    from .certificate_template import SpaceCertificateConfig


class SpaceCertificate(Base):
    __tablename__ = "space_certificates"

    __table_args__ = (
        UniqueConstraint("user_id", "space_id", name="uq_space_cert_user_space"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        nullable=False,
    )

    # FK to the cert config that triggered this issuance (nullable for old records)
    config_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("space_certificate_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Filesystem path where the generated PDF is stored
    # e.g. /data/certificates/{cert_id}.pdf
    pdf_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Snapshot data used to render the certificate (learner name, space title, date)
    cert_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # ── Relationships ──────────────────────────────────────────────────────
    user: Mapped["AxisUser"] = relationship("AxisUser", foreign_keys=[user_id])
    space: Mapped["LearningSpace"] = relationship("LearningSpace", foreign_keys=[space_id])
    config: Mapped[Optional["SpaceCertificateConfig"]] = relationship(
        "SpaceCertificateConfig", back_populates="issued_certificates",
        foreign_keys=[config_id]
    )

    def __repr__(self) -> str:
        return f"<SpaceCertificate user={self.user_id} space={self.space_id} issued={self.issued_at}>"
