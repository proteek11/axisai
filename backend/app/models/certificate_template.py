"""
CertificateTemplate — admin-managed branded certificate templates.
SpaceCertificateConfig — creator-placed cert trigger inside a learning space.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, Index, String, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

if TYPE_CHECKING:
    from .tenant import Tenant
    from .space import LearningSpace
    from .certificate import SpaceCertificate


class CertificateTemplate(Base):
    __tablename__ = "certificate_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # completion / participation / achievement / custom
    type_tag: Mapped[str] = mapped_column(String(64), nullable=False, default="completion")
    # classic / modern / minimal / branded
    layout_style: Mapped[str] = mapped_column(String(64), nullable=False, default="classic")
    title_text: Mapped[str] = mapped_column(
        String(512), nullable=False, default="Certificate of Completion"
    )
    body_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    signature_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    signature_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    signature_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"),
        onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    configs: Mapped[list["SpaceCertificateConfig"]] = relationship(
        "SpaceCertificateConfig", back_populates="template"
    )

    def __repr__(self) -> str:
        return f"<CertificateTemplate {self.name!r} [{self.type_tag}]>"


class SpaceCertificateConfig(Base):
    """One row per certificate placed by a creator in a learning space."""
    __tablename__ = "space_certificate_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("certificate_templates.id", ondelete="SET NULL"),
        nullable=True,
    )
    # all_items | percentage | assessment | manual
    trigger_type: Mapped[str] = mapped_column(String(64), nullable=False, default="all_items")
    # e.g. {"percentage": 80} or {"assessment_id": "uuid"}
    trigger_value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    custom_title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    custom_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False
    )

    # Relationships
    template: Mapped[Optional["CertificateTemplate"]] = relationship(
        "CertificateTemplate", back_populates="configs"
    )
    space: Mapped["LearningSpace"] = relationship("LearningSpace", foreign_keys=[space_id])
    issued_certificates: Mapped[list["SpaceCertificate"]] = relationship(
        "SpaceCertificate", back_populates="config",
        foreign_keys="SpaceCertificate.config_id"
    )

    def __repr__(self) -> str:
        return f"<SpaceCertificateConfig space={self.space_id} trigger={self.trigger_type}>"
