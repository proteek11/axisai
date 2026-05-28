"""
AxisUser — standalone application users for the axis.edzlms.com frontend.
Not linked to Moodle users. Managed independently.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .tenant import Tenant
    from .space import LearningSpace, SpaceAccess
    from .token_budget import UserTokenBudget
    from .skills import OrgRole


class AxisUser(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Application user for the standalone Next.js frontend.

    Roles:
      admin   — full platform control
      creator — manages own Learning Spaces + content
      learner — studies content in assigned spaces
    """

    __tablename__ = "axis_users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    # LTI 1.3 — set for JIT-provisioned users: "<issuer>::<sub>"
    lti_sub: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    # Skills / Org Role shortcut (mirrors active row in user_org_roles)
    active_org_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_roles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    created_spaces: Mapped[list["LearningSpace"]] = relationship(
        "LearningSpace", back_populates="creator", cascade="all, delete-orphan"
    )
    space_accesses: Mapped[list["SpaceAccess"]] = relationship(
        "SpaceAccess", foreign_keys="[SpaceAccess.user_id]", back_populates="user", cascade="all, delete-orphan"
    )
    token_budget: Mapped[Optional["UserTokenBudget"]] = relationship(
        "UserTokenBudget", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AxisUser {self.email} role={self.role}>"


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """Refresh token record. SHA-256 of raw token stored — never the raw token."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)

    from sqlalchemy import func
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["AxisUser"] = relationship("AxisUser", back_populates="refresh_tokens")

    def __repr__(self) -> str:
        return f"<RefreshToken user={self.user_id} expires={self.expires_at}>"
