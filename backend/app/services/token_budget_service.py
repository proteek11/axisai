"""
Token budget service.

Handles all budget-related DB operations so the AIClient stays clean.
Called by AIClient.generate() for pre-flight checks and post-call accounting.

Public API:
  get_effective_limit(db, user) -> int
      Returns the user's actual monthly limit (override or role default).

  check_budget(db, user, estimated_tokens) -> BudgetStatus
      Raises TokenBudgetExceededError if the user is at or over limit.

  record_usage(db, user_id, tokens_used) -> None
      Atomically increments tokens_used_this_month.

  get_budget_row(db, user_id) -> UserTokenBudget
      Upserts and returns the user's budget row (creates lazily).

  reset_all_monthly_usage(db) -> int
      Zeroes tokens_used_this_month for every user. Called by Celery Beat.
"""

from __future__ import annotations

import uuid
import logging
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.token_budget import TokenBudgetDefault, UserTokenBudget
from app.models.user import AxisUser
from app.core.exceptions import TokenBudgetExceededError

logger = logging.getLogger(__name__)

# Role defaults — used as in-memory fallback if DB row is missing
_HARDCODED_DEFAULTS: dict[str, int] = {
    "admin": 2_000_000,
    "creator": 500_000,
    "learner": 100_000,
}


@dataclass
class BudgetStatus:
    user_id: uuid.UUID
    used: int
    limit: int
    remaining: int
    has_override: bool
    pct_used: float  # 0.0–1.0


async def _get_role_default(db: AsyncSession, role: str) -> int:
    """Fetch monthly_token_limit for a role from DB, falling back to hardcoded."""
    result = await db.execute(
        select(TokenBudgetDefault).where(TokenBudgetDefault.role == role)
    )
    row = result.scalar_one_or_none()
    if row:
        return row.monthly_token_limit
    return _HARDCODED_DEFAULTS.get(role, 100_000)


async def get_budget_row(db: AsyncSession, user: AxisUser) -> UserTokenBudget:
    """
    Return the UserTokenBudget for this user, creating it lazily if needed.
    Uses an upsert so concurrent calls don't double-insert.
    """
    result = await db.execute(
        select(UserTokenBudget).where(UserTokenBudget.user_id == user.id)
    )
    budget = result.scalar_one_or_none()
    if budget:
        return budget

    # Lazy creation — inherits role default (monthly_token_limit = NULL)
    stmt = (
        pg_insert(UserTokenBudget)
        .values(user_id=user.id)
        .on_conflict_do_nothing(index_elements=["user_id"])
        .returning(UserTokenBudget)
    )
    result = await db.execute(stmt)
    await db.flush()

    # Re-fetch (on_conflict_do_nothing may return nothing if row existed)
    result2 = await db.execute(
        select(UserTokenBudget).where(UserTokenBudget.user_id == user.id)
    )
    return result2.scalar_one()


async def get_effective_limit(db: AsyncSession, user: AxisUser) -> int:
    """
    Effective monthly limit for this user:
      - user_token_budgets.monthly_token_limit  (if set — admin override)
      - token_budget_defaults.monthly_token_limit for the user's role
    """
    budget = await get_budget_row(db, user)
    if budget.monthly_token_limit is not None:
        return budget.monthly_token_limit
    return await _get_role_default(db, user.role)


async def get_budget_status(db: AsyncSession, user: AxisUser) -> BudgetStatus:
    """Full budget snapshot for a user."""
    budget = await get_budget_row(db, user)
    limit = await get_effective_limit(db, user)
    used = budget.tokens_used_this_month
    remaining = max(0, limit - used)
    pct = min(1.0, used / limit) if limit > 0 else 1.0
    return BudgetStatus(
        user_id=user.id,
        used=used,
        limit=limit,
        remaining=remaining,
        has_override=budget.has_override,
        pct_used=pct,
    )


async def check_budget(
    db: AsyncSession,
    user: AxisUser,
    estimated_tokens: int = 0,
) -> BudgetStatus:
    """
    Raises TokenBudgetExceededError if user is at or over their monthly limit.
    Returns BudgetStatus so callers can show remaining tokens in warnings.
    """
    status = await get_budget_status(db, user)
    if status.used >= status.limit:
        raise TokenBudgetExceededError(
            user_id=str(user.id),
            used=status.used,
            limit=status.limit,
        )
    return status


async def record_usage(
    db: AsyncSession,
    user_id: uuid.UUID,
    tokens_used: int,
) -> None:
    """
    Atomically increment tokens_used_this_month via UPSERT.
    Creates the row if it doesn't exist (e.g. when check_budget session was
    not committed before this call).  Never silently drops counts.
    """
    if tokens_used <= 0:
        return
    stmt = (
        pg_insert(UserTokenBudget)
        .values(user_id=user_id, tokens_used_this_month=tokens_used)
        .on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "tokens_used_this_month": (
                    UserTokenBudget.tokens_used_this_month + tokens_used
                )
            },
        )
    )
    await db.execute(stmt)
    await db.flush()
    logger.debug("Recorded %d tokens for user %s", tokens_used, user_id)


async def reset_all_monthly_usage(db: AsyncSession) -> int:
    """
    Zero out tokens_used_this_month for every user.
    Called by the Celery Beat task on the 1st of each month.
    Returns the number of rows reset.
    """
    result = await db.execute(
        update(UserTokenBudget).values(tokens_used_this_month=0)
    )
    await db.commit()
    count = result.rowcount
    logger.info("Monthly token usage reset: %d user budget rows zeroed", count)
    return count


async def admin_set_override(
    db: AsyncSession,
    user_id: uuid.UUID,
    monthly_token_limit: int | None,
    reason: str | None,
    set_by: uuid.UUID,
) -> UserTokenBudget:
    """
    Admin sets (or clears) a per-user token limit override.
    Pass monthly_token_limit=None to revert to role default.
    """
    result = await db.execute(
        select(UserTokenBudget).where(UserTokenBudget.user_id == user_id)
    )
    budget = result.scalar_one_or_none()

    if budget is None:
        # Create the row with the override
        budget = UserTokenBudget(
            user_id=user_id,
            monthly_token_limit=monthly_token_limit,
            override_reason=reason,
            override_set_by=set_by,
        )
        db.add(budget)
    else:
        budget.monthly_token_limit = monthly_token_limit
        budget.override_reason = reason
        budget.override_set_by = set_by

    await db.flush()
    await db.refresh(budget)
    return budget
