"""
Token budget admin and user-self-view endpoints.

Admin routes (require role=admin):
  GET  /api/v1/admin/token-defaults           — list role-level monthly limits
  PUT  /api/v1/admin/token-defaults/{role}    — update a role's default limit
  GET  /api/v1/admin/token-budgets            — list all user budget rows + effective limits
  GET  /api/v1/admin/token-budgets/{user_id}  — single user budget detail
  PUT  /api/v1/admin/token-budgets/{user_id}  — set/clear per-user override
  POST /api/v1/admin/token-budgets/reset      — manually trigger monthly reset

User self-view (any authenticated axis user):
  GET  /api/v1/me/token-budget   — own current budget status
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_dep, require_role
from app.core.database import get_db
from app.models.token_budget import TokenBudgetDefault, UserTokenBudget
from app.models.user import AxisUser
from app.services.token_budget_service import (
    admin_set_override,
    get_budget_status,
    get_effective_limit,
    reset_all_monthly_usage,
)

router = APIRouter()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TokenDefaultResponse(BaseModel):
    role: str
    monthly_token_limit: int

    class Config:
        from_attributes = True


class TokenDefaultUpdate(BaseModel):
    monthly_token_limit: int = Field(..., ge=1000, le=100_000_000)


class BudgetStatusResponse(BaseModel):
    user_id: str
    email: str
    role: str
    full_name: Optional[str]
    used: int
    limit: int
    remaining: int
    pct_used: float
    has_override: bool
    override_reason: Optional[str] = None
    override_set_by: Optional[str] = None


class BudgetOverrideRequest(BaseModel):
    monthly_token_limit: Optional[int] = Field(
        None,
        ge=1000,
        le=100_000_000,
        description="Set to null/None to revert user to their role default",
    )
    reason: Optional[str] = Field(None, max_length=500)


class ResetResponse(BaseModel):
    rows_reset: int
    message: str


# ── Helper ────────────────────────────────────────────────────────────────────

async def _build_budget_response(
    db: AsyncSession, user: AxisUser
) -> BudgetStatusResponse:
    """Build a full BudgetStatusResponse for a user."""
    status_obj = await get_budget_status(db, user)

    # Fetch override details
    result = await db.execute(
        select(UserTokenBudget).where(UserTokenBudget.user_id == user.id)
    )
    budget_row = result.scalar_one_or_none()

    return BudgetStatusResponse(
        user_id=str(user.id),
        email=user.email,
        role=user.role,
        full_name=user.full_name,
        used=status_obj.used,
        limit=status_obj.limit,
        remaining=status_obj.remaining,
        pct_used=round(status_obj.pct_used, 4),
        has_override=status_obj.has_override,
        override_reason=budget_row.override_reason if budget_row else None,
        override_set_by=str(budget_row.override_set_by) if budget_row and budget_row.override_set_by else None,
    )


# ── User self-view ────────────────────────────────────────────────────────────

@router.get("/me/token-budget", response_model=BudgetStatusResponse)
async def get_my_token_budget(
    current_user: AxisUser = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return the calling user's current token budget status."""
    return await _build_budget_response(db, current_user)


# ── Admin — role defaults ─────────────────────────────────────────────────────

@router.get(
    "/admin/token-defaults",
    response_model=list[TokenDefaultResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_token_defaults(db: AsyncSession = Depends(get_db)):
    """List monthly token limits for each role."""
    result = await db.execute(select(TokenBudgetDefault))
    rows = result.scalars().all()
    return [TokenDefaultResponse(role=r.role, monthly_token_limit=r.monthly_token_limit) for r in rows]


@router.put(
    "/admin/token-defaults/{role}",
    response_model=TokenDefaultResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_token_default(
    role: str,
    body: TokenDefaultUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the monthly token default for a role."""
    if role not in ("admin", "creator", "learner"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown role '{role}'. Must be admin, creator, or learner.",
        )
    result = await db.execute(
        select(TokenBudgetDefault).where(TokenBudgetDefault.role == role)
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = TokenBudgetDefault(role=role, monthly_token_limit=body.monthly_token_limit)
        db.add(row)
    else:
        row.monthly_token_limit = body.monthly_token_limit
    await db.commit()
    await db.refresh(row)
    return TokenDefaultResponse(role=row.role, monthly_token_limit=row.monthly_token_limit)


# ── Admin — per-user budgets ──────────────────────────────────────────────────

@router.get(
    "/admin/token-budgets",
    response_model=list[BudgetStatusResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_all_token_budgets(db: AsyncSession = Depends(get_db)):
    """List budget status for every user. Includes effective limit (override or role default)."""
    result = await db.execute(select(AxisUser).where(AxisUser.is_active == True))
    users = result.scalars().all()
    return [await _build_budget_response(db, u) for u in users]


@router.get(
    "/admin/token-budgets/{user_id}",
    response_model=BudgetStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_user_token_budget(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get budget detail for a specific user."""
    result = await db.execute(select(AxisUser).where(AxisUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return await _build_budget_response(db, user)


@router.put(
    "/admin/token-budgets/{user_id}",
    response_model=BudgetStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def set_user_token_budget(
    user_id: uuid.UUID,
    body: BudgetOverrideRequest,
    current_user: AxisUser = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """
    Set or clear a per-user token limit override.
    Pass monthly_token_limit=null to revert user to their role default.
    """
    result = await db.execute(select(AxisUser).where(AxisUser.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await admin_set_override(
        db=db,
        user_id=user_id,
        monthly_token_limit=body.monthly_token_limit,
        reason=body.reason,
        set_by=current_user.id,
    )
    await db.commit()
    return await _build_budget_response(db, user)


@router.post(
    "/admin/token-budgets/reset",
    response_model=ResetResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def manual_monthly_reset(db: AsyncSession = Depends(get_db)):
    """
    Manually trigger the monthly token usage reset for all users.
    Normally run by Celery Beat on the 1st of each month.
    """
    count = await reset_all_monthly_usage(db)
    return ResetResponse(
        rows_reset=count,
        message=f"Monthly token usage reset: {count} user(s) zeroed.",
    )
