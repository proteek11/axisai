"""
Token budget models.

TokenBudgetDefault  — one row per role, holds the platform-wide monthly limit.
UserTokenBudget     — one row per user, holds the per-user running counter and
                      optional admin override limit.

Design decisions:
- monthly_token_limit in UserTokenBudget is nullable: NULL means "fall through
  to the role default". This avoids needing to backfill every user when an
  admin changes the role default.
- tokens_used_this_month is reset to 0 by the Celery Beat task on the 1st of
  each month (see app/tasks/budget_tasks.py).
- Enforcement happens in AIClient.generate() before any LiteLLM call.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from .base import Base

if TYPE_CHECKING:
    from .user import AxisUser


class TokenBudgetDefault(Base):
    """
    Platform-wide monthly token limit per role.
    Admin-configurable via PUT /api/v1/admin/token-defaults.
    """

    __tablename__ = "token_budget_defaults"

    role: Mapped[str] = mapped_column(String(20), primary_key=True)
    monthly_token_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<TokenBudgetDefault role={self.role} limit={self.monthly_token_limit:,}>"


class UserTokenBudget(Base):
    """
    Per-user token budget row.

    One row per AxisUser. Created lazily on first AI generation request, or
    proactively by admin override.

    Effective limit resolution (in order):
      1. user_token_budgets.monthly_token_limit if NOT NULL
      2. token_budget_defaults.monthly_token_limit for the user's role
    """

    __tablename__ = "user_token_budgets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default="gen_random_uuid()",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # NULL = use role default
    monthly_token_limit: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    tokens_used_this_month: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    override_set_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # relationship
    user: Mapped["AxisUser"] = relationship("AxisUser", back_populates="token_budget")

    @property
    def has_override(self) -> bool:
        return self.monthly_token_limit is not None

    def __repr__(self) -> str:
        limit_str = f"{self.monthly_token_limit:,}" if self.monthly_token_limit else "role-default"
        return (
            f"<UserTokenBudget user={self.user_id} "
            f"used={self.tokens_used_this_month:,} limit={limit_str}>"
        )
