"""
LTI 1.3 platform registration model.
One row per Moodle (or other LMS) instance connected to axis-ai.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LTIPlatform(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A registered LTI 1.3 platform (e.g. a Moodle site).

    issuer       — Moodle site URL, matches the `iss` claim in every JWT.
    client_id    — Assigned by Moodle when the External Tool is created.
    deployment_ids — JSON list of strings (usually ["1"]).
    """

    __tablename__ = "lti_platforms"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_login_url: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_token_url: Mapped[str] = mapped_column(String(512), nullable=False)
    key_set_url: Mapped[str] = mapped_column(String(512), nullable=False)
    deployment_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<LTIPlatform '{self.name}' issuer={self.issuer}>"
