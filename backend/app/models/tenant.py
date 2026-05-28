"""
Tenant model — one row per Moodle instance connecting to axis-ai.
Supports multi-tenancy from day one.
"""
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from .content import ContentItem
    from .audit import AuditLog
    from .rate_limit import RateLimitRule


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Represents a single Moodle installation.
    Every other table has a tenant_id FK for data isolation.

    Feature flags (feature_*): set by Moodle admin — control which AI outputs
    are enabled for the entire installation. Teachers can only *restrict* further,
    never enable something the admin has disabled.

    Rate limits: enforced in Redis per user. Moodle admin sets the baseline;
    per-user overrides stored in UserTokenOverride table.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    moodle_url: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ── Feature flags (admin-controlled, cascade down to teachers/students) ────
    feature_summary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_glossary: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_flashcards: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_quiz: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_faq: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_infographic: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_chatbot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    feature_kb_chat: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False,
        comment="Support/KB chatbot mode (admin uploads knowledge base docs)")

    # ── Chat rate limits (baseline — per-user overrides in UserTokenOverride) ──
    chat_session_msg_limit: Mapped[int] = mapped_column(
        Integer, default=50, nullable=False,
        comment="Max messages per chat session per user (0 = unlimited)"
    )
    chat_daily_msg_limit: Mapped[int] = mapped_column(
        Integer, default=200, nullable=False,
        comment="Max chat messages per user per calendar day (0 = unlimited)"
    )
    chat_monthly_msg_limit: Mapped[int] = mapped_column(
        Integer, default=2000, nullable=False,
        comment="Max chat messages per user per calendar month (0 = unlimited)"
    )
    token_monthly_limit: Mapped[int] = mapped_column(
        Integer, default=5_000_000, nullable=False,
        comment="Max tokens consumed across all users for this tenant per month (0 = unlimited)"
    )

    # Tenant-level config overrides (provider preference, model overrides, etc.)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Relationships
    api_keys: Mapped[list["ApiKey"]] = relationship(
        "ApiKey", back_populates="tenant", cascade="all, delete-orphan"
    )
    content_items: Mapped[list["ContentItem"]] = relationship(
        "ContentItem", back_populates="tenant", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        "AuditLog", back_populates="tenant"
    )
    rate_limit_rules: Mapped[list["RateLimitRule"]] = relationship(
        "RateLimitRule", back_populates="tenant", cascade="all, delete-orphan"
    )
    user_token_overrides: Mapped[list["UserTokenOverride"]] = relationship(
        "UserTokenOverride", back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.name} ({self.moodle_url})>"


class UserTokenOverride(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Per-user token/rate-limit overrides.
    Admin can give specific users higher (or lower) limits than the tenant baseline.
    Moodle plugin creates/updates these when admin edits a user override.
    """

    __tablename__ = "user_token_overrides"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    moodle_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # NULL on any field = fall back to tenant baseline
    chat_session_msg_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat_daily_msg_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chat_monthly_msg_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    note: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Admin note explaining why this user has an override"
    )
    set_by_moodle_user_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Moodle user ID of the admin who set this override"
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="user_token_overrides")

    def __repr__(self) -> str:
        return f"<UserTokenOverride user={self.moodle_user_id} tenant={self.tenant_id}>"


class ApiKey(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    API keys issued to Moodle instances / admin clients.
    Only key_hash is stored — never the raw key.
    """

    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    # Fine-grained scope control (future use)
    scopes: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(nullable=True)
    expires_at: Mapped[str | None] = mapped_column(nullable=True)

    # Relationships
    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="api_keys")

    def __repr__(self) -> str:
        return f"<ApiKey {self.name} (tenant={self.tenant_id})>"
