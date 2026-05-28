"""
Teams API — group users for bulk Learning Space access.

GET    /api/v1/teams                        → list teams (admin/creator)
POST   /api/v1/teams                        → create team (admin)
GET    /api/v1/teams/{id}                   → get team with members
PUT    /api/v1/teams/{id}                   → update team (admin)
DELETE /api/v1/teams/{id}                   → delete team (admin)
POST   /api/v1/teams/{id}/members           → add members (admin)
DELETE /api/v1/teams/{id}/members           → remove members (admin)
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.team import Team, TeamMember
from app.models.user import AxisUser
from app.schemas.team import (
    TeamCreate,
    TeamDetailResponse,
    TeamListResponse,
    TeamResponse,
    TeamUpdate,
    MemberAddRequest,
    MemberRemoveRequest,
    MemberSummary,
)

router = APIRouter(prefix="/teams", tags=["Teams"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


def _dept_response(dept: Team, members: list[tuple]) -> TeamDetailResponse:
    member_summaries = [
        MemberSummary(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            added_at=dm.added_at,
        )
        for dm, user in members
    ]
    return TeamDetailResponse(
        id=dept.id,
        tenant_id=dept.tenant_id,
        name=dept.name,
        description=dept.description,
        is_active=dept.is_active,
        member_count=len(member_summaries),
        created_at=dept.created_at,
        updated_at=dept.updated_at,
        members=member_summaries,
    )


async def _load_dept(team_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> Team:
    result = await db.execute(
        select(Team).where(
            Team.id == team_id,
            Team.tenant_id == tenant_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Team not found")
    return dept


async def _load_members(team_id: uuid.UUID, db: AsyncSession) -> list[tuple]:
    result = await db.execute(
        select(TeamMember, AxisUser)
        .join(AxisUser, TeamMember.user_id == AxisUser.id)
        .where(TeamMember.team_id == team_id)
        .order_by(AxisUser.full_name, AxisUser.email)
    )
    return result.all()


# ── List teams ──────────────────────────────────────────────────────────

@router.get("", response_model=TeamListResponse)
async def list_teams(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamListResponse:
    """List all teams in this tenant. Admin and creator access."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator access required")

    result = await db.execute(
        select(Team)
        .where(Team.tenant_id == user.tenant_id)
        .order_by(Team.name)
    )
    teams = result.scalars().all()

    dept_responses = []
    for dept in teams:
        members = await _load_members(dept.id, db)
        dept_responses.append(
            TeamResponse(
                id=dept.id,
                tenant_id=dept.tenant_id,
                name=dept.name,
                description=dept.description,
                is_active=dept.is_active,
                member_count=len(members),
                created_at=dept.created_at,
                updated_at=dept.updated_at,
            )
        )

    return TeamListResponse(teams=dept_responses, total=len(dept_responses))


# ── Create team ─────────────────────────────────────────────────────────

@router.post("", response_model=TeamDetailResponse, status_code=201)
async def create_team(
    req: TeamCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Create a new team. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = Team(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        name=req.name,
        description=req.description,
        created_by=user.id,
        is_active=True,
    )
    db.add(dept)
    await db.commit()
    await db.refresh(dept)

    log.info("team_created", team_id=str(dept.id), name=dept.name, by=str(user.id))
    return _dept_response(dept, [])


# ── Get team ────────────────────────────────────────────────────────────

@router.get("/{team_id}", response_model=TeamDetailResponse)
async def get_team(
    team_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Get a team with its member list. Admin or creator."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator access required")

    dept = await _load_dept(team_id, user.tenant_id, db)
    members = await _load_members(team_id, db)
    return _dept_response(dept, members)


# ── Update team ─────────────────────────────────────────────────────────

@router.put("/{team_id}", response_model=TeamDetailResponse)
async def update_team(
    team_id: uuid.UUID,
    req: TeamUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Update team metadata. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(team_id, user.tenant_id, db)

    if req.name is not None:
        dept.name = req.name
    if req.description is not None:
        dept.description = req.description
    if req.is_active is not None:
        dept.is_active = req.is_active

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(team_id, db)
    log.info("team_updated", team_id=str(team_id), by=str(user.id))
    return _dept_response(dept, members)


# ── Delete team ─────────────────────────────────────────────────────────

@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a team. Admin only. Space access grants referencing this dept are cascade-deleted."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(team_id, user.tenant_id, db)
    await db.delete(dept)
    await db.commit()
    log.info("team_deleted", team_id=str(team_id), by=str(user.id))


# ── Add members ───────────────────────────────────────────────────────────────

@router.post("/{team_id}/members", status_code=200, response_model=TeamDetailResponse)
async def add_members(
    team_id: uuid.UUID,
    req: MemberAddRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Add one or more users to a team. Admin only. Idempotent — skips duplicates."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(team_id, user.tenant_id, db)

    # Verify all users exist in this tenant
    result = await db.execute(
        select(AxisUser).where(
            AxisUser.id.in_(req.user_ids),
            AxisUser.tenant_id == user.tenant_id,
        )
    )
    valid_users = {u.id for u in result.scalars().all()}
    invalid = set(req.user_ids) - valid_users
    if invalid:
        raise HTTPException(
            status_code=404,
            detail=f"Users not found in this tenant: {[str(i) for i in invalid]}",
        )

    # Load existing members to skip duplicates
    existing_result = await db.execute(
        select(TeamMember.user_id).where(TeamMember.team_id == team_id)
    )
    existing_ids = {row for row in existing_result.scalars().all()}

    added = 0
    for uid in req.user_ids:
        if uid not in existing_ids:
            db.add(TeamMember(team_id=team_id, user_id=uid, added_by=user.id))
            added += 1

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(team_id, db)
    log.info("members_added", team_id=str(team_id), count=added, by=str(user.id))

    # Phase 13 — team_added email for each newly added user (fire-and-forget)
    if added > 0:
        try:
            import asyncio as _aio
            from app.services.email import send_trigger_email as _send_trigger
            from app.config import settings as _cfg
            from sqlalchemy import select as _select
            _frontend_url = getattr(_cfg, "frontend_url", "https://axis.edzlms.com")
            # Fetch newly added users to get their emails
            _new_ids = [uid for uid in req.user_ids if uid not in existing_ids]
            _user_rows_result = await db.execute(
                _select(AxisUser).where(AxisUser.id.in_(_new_ids))
            )
            _new_users = _user_rows_result.scalars().all()
            for _nu in _new_users:
                _aio.ensure_future(
                    _send_trigger(
                        db=db,
                        trigger="team_added",
                        to_email=_nu.email,
                        to_name=_nu.full_name or "",
                        variables={
                            "full_name": _nu.full_name or _nu.email,
                            "team_name": dept.name,
                            "added_by": user.full_name or user.email,
                            "login_url": f"{_frontend_url}/login",
                        },
                    )
                )
        except Exception:
            pass  # never fail team membership on email error

    return _dept_response(dept, members)


# ── Remove members ────────────────────────────────────────────────────────────

@router.delete("/{team_id}/members", status_code=200, response_model=TeamDetailResponse)
async def remove_members(
    team_id: uuid.UUID,
    req: MemberRemoveRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> TeamDetailResponse:
    """Remove one or more users from a team. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(team_id, user.tenant_id, db)

    result = await db.execute(
        select(TeamMember).where(
            TeamMember.team_id == team_id,
            TeamMember.user_id.in_(req.user_ids),
        )
    )
    members_to_remove = result.scalars().all()
    for m in members_to_remove:
        await db.delete(m)

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(team_id, db)
    log.info("members_removed", team_id=str(team_id), count=len(members_to_remove), by=str(user.id))
    return _dept_response(dept, members)
