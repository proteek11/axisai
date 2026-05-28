"""
Org Setup API — proficiency levels, org roles, role skill targets, user role assignment.

GET    /api/v1/org-setup/proficiency-levels                       → list levels (sorted by level_order)
POST   /api/v1/org-setup/proficiency-levels                       → create level
PUT    /api/v1/org-setup/proficiency-levels/{id}                  → update level
DELETE /api/v1/org-setup/proficiency-levels/{id}                  → delete level (guarded)

GET    /api/v1/org-setup/org-roles                                → list roles (with team_name, skill_target_count)
POST   /api/v1/org-setup/org-roles                                → create role
PUT    /api/v1/org-setup/org-roles/{id}                           → update role
DELETE /api/v1/org-setup/org-roles/{id}                           → delete role (guarded)

GET    /api/v1/org-setup/org-roles/{id}/skill-targets             → list skill targets for role
POST   /api/v1/org-setup/org-roles/{id}/skill-targets             → upsert skill target
DELETE /api/v1/org-setup/org-roles/{id}/skill-targets/{sid}       → remove skill target

POST   /api/v1/org-setup/users/{user_id}/org-role                 → assign org role to user
"""
import uuid
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.skills import (
    OrgRole,
    OrgRoleSkillTarget,
    ProficiencyLevel,
    Skill,
    UserOrgRole,
)
from app.models.team import Team
from app.models.user import AxisUser

router = APIRouter(prefix="/org-setup", tags=["Org Setup"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ProficiencyLevelCreate(BaseModel):
    level_order: int
    label: str
    description: Optional[str] = None


class ProficiencyLevelUpdate(BaseModel):
    level_order: Optional[int] = None
    label: Optional[str] = None
    description: Optional[str] = None


class OrgRoleCreate(BaseModel):
    name: str
    team_id: Optional[uuid.UUID] = None


class OrgRoleUpdate(BaseModel):
    name: Optional[str] = None
    team_id: Optional[uuid.UUID] = None
    is_archived: Optional[bool] = None


class SkillTargetUpsert(BaseModel):
    skill_id: uuid.UUID
    target_level_id: uuid.UUID


class AssignOrgRoleRequest(BaseModel):
    org_role_id: uuid.UUID


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin only")


async def _get_level(
    level_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> ProficiencyLevel:
    result = await db.execute(
        select(ProficiencyLevel).where(
            ProficiencyLevel.id == level_id,
            ProficiencyLevel.tenant_id == tenant_id,
        )
    )
    level = result.scalar_one_or_none()
    if not level:
        raise HTTPException(status_code=404, detail="Proficiency level not found")
    return level


async def _get_org_role(
    role_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> OrgRole:
    result = await db.execute(
        select(OrgRole).where(
            OrgRole.id == role_id,
            OrgRole.tenant_id == tenant_id,
        )
    )
    role = result.scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Org role not found")
    return role


# ═══════════════════════════════════════════════════════════════════════════════
# PROFICIENCY LEVELS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/proficiency-levels")
async def list_proficiency_levels(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all proficiency levels for the tenant, sorted by level_order."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    result = await db.execute(
        select(ProficiencyLevel)
        .where(ProficiencyLevel.tenant_id == user.tenant_id)
        .order_by(ProficiencyLevel.level_order)
    )
    levels = result.scalars().all()

    return [
        {
            "id": str(lv.id),
            "level_order": lv.level_order,
            "label": lv.label,
            "description": lv.description,
            "created_at": lv.created_at.isoformat(),
        }
        for lv in levels
    ]


@router.post("/proficiency-levels", status_code=201)
async def create_proficiency_level(
    body: ProficiencyLevelCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new proficiency level for the tenant."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Check for duplicate level_order or label within tenant
    dup = await db.execute(
        select(ProficiencyLevel).where(
            ProficiencyLevel.tenant_id == user.tenant_id,
            (ProficiencyLevel.level_order == body.level_order)
            | (ProficiencyLevel.label == body.label),
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="A proficiency level with this order or label already exists",
        )

    level = ProficiencyLevel(
        tenant_id=user.tenant_id,
        level_order=body.level_order,
        label=body.label,
        description=body.description,
    )
    db.add(level)
    await db.commit()
    await db.refresh(level)

    log.info("proficiency_level_created", id=str(level.id), label=level.label, admin=str(user.id))
    return {
        "id": str(level.id),
        "level_order": level.level_order,
        "label": level.label,
        "description": level.description,
        "created_at": level.created_at.isoformat(),
    }


@router.put("/proficiency-levels/{level_id}")
async def update_proficiency_level(
    level_id: uuid.UUID,
    body: ProficiencyLevelUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update label, description, or level_order of a proficiency level."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    level = await _get_level(level_id, user.tenant_id, db)

    if body.level_order is not None:
        level.level_order = body.level_order
    if body.label is not None:
        level.label = body.label
    if body.description is not None:
        level.description = body.description

    await db.commit()
    await db.refresh(level)

    return {
        "id": str(level.id),
        "level_order": level.level_order,
        "label": level.label,
        "description": level.description,
        "created_at": level.created_at.isoformat(),
    }


@router.delete("/proficiency-levels/{level_id}", status_code=204)
async def delete_proficiency_level(
    level_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a proficiency level.

    Guarded: rejects if any OrgRoleSkillTarget or UserSkillProgress references this level.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    level = await _get_level(level_id, user.tenant_id, db)

    # Guard: check OrgRoleSkillTarget references
    target_ref = await db.execute(
        select(OrgRoleSkillTarget.id).where(
            OrgRoleSkillTarget.target_level_id == level_id
        ).limit(1)
    )
    if target_ref.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: this level is referenced by one or more role skill targets",
        )

    # Guard: check UserSkillProgress references (import here to avoid circular)
    from app.models.skills import UserSkillProgress
    progress_ref = await db.execute(
        select(UserSkillProgress.id).where(
            UserSkillProgress.current_level_id == level_id
        ).limit(1)
    )
    if progress_ref.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: this level is referenced by user skill progress records",
        )

    await db.delete(level)
    await db.commit()
    log.info("proficiency_level_deleted", id=str(level_id), admin=str(user.id))


# ═══════════════════════════════════════════════════════════════════════════════
# ORG ROLES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/org-roles")
async def list_org_roles(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List org roles with team_name and skill_target_count."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Fetch roles with optional team join
    result = await db.execute(
        select(OrgRole, Team.name.label("team_name"))
        .outerjoin(Team, OrgRole.team_id == Team.id)
        .where(OrgRole.tenant_id == user.tenant_id)
        .order_by(OrgRole.created_at)
    )
    rows = result.all()

    # Skill target counts per role
    counts_result = await db.execute(
        select(
            OrgRoleSkillTarget.org_role_id,
            func.count(OrgRoleSkillTarget.id).label("cnt"),
        )
        .group_by(OrgRoleSkillTarget.org_role_id)
    )
    counts_map: dict[uuid.UUID, int] = {row.org_role_id: row.cnt for row in counts_result}

    return [
        {
            "id": str(role.id),
            "name": role.name,
            "team_id": str(role.team_id) if role.team_id else None,
            "team_name": team_name,
            "is_archived": role.is_archived,
            "skill_target_count": counts_map.get(role.id, 0),
            "created_at": role.created_at.isoformat(),
        }
        for role, team_name in rows
    ]


@router.post("/org-roles", status_code=201)
async def create_org_role(
    body: OrgRoleCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new org role."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Check for duplicate name within tenant
    dup = await db.execute(
        select(OrgRole).where(
            OrgRole.tenant_id == user.tenant_id,
            OrgRole.name == body.name,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="An org role with this name already exists")

    # Validate team_id belongs to this tenant if provided
    if body.team_id:
        team_check = await db.execute(
            select(Team).where(Team.id == body.team_id, Team.tenant_id == user.tenant_id)
        )
        if not team_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Team not found")

    role = OrgRole(
        tenant_id=user.tenant_id,
        name=body.name,
        team_id=body.team_id,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    log.info("org_role_created", id=str(role.id), name=role.name, admin=str(user.id))
    return {
        "id": str(role.id),
        "name": role.name,
        "team_id": str(role.team_id) if role.team_id else None,
        "is_archived": role.is_archived,
        "skill_target_count": 0,
        "created_at": role.created_at.isoformat(),
    }


@router.put("/org-roles/{role_id}")
async def update_org_role(
    role_id: uuid.UUID,
    body: OrgRoleUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update name, team_id, or is_archived of an org role."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    role = await _get_org_role(role_id, user.tenant_id, db)

    if body.name is not None:
        role.name = body.name
    if body.team_id is not None:
        team_check = await db.execute(
            select(Team).where(Team.id == body.team_id, Team.tenant_id == user.tenant_id)
        )
        if not team_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Team not found")
        role.team_id = body.team_id
    if body.is_archived is not None:
        role.is_archived = body.is_archived

    await db.commit()
    await db.refresh(role)

    return {
        "id": str(role.id),
        "name": role.name,
        "team_id": str(role.team_id) if role.team_id else None,
        "is_archived": role.is_archived,
        "created_at": role.created_at.isoformat(),
    }


@router.delete("/org-roles/{role_id}", status_code=204)
async def delete_org_role(
    role_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete an org role.

    Guarded: rejects if any UserOrgRole record references this role.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    role = await _get_org_role(role_id, user.tenant_id, db)

    user_ref = await db.execute(
        select(UserOrgRole.id).where(UserOrgRole.org_role_id == role_id).limit(1)
    )
    if user_ref.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: this role is assigned to one or more users",
        )

    await db.delete(role)
    await db.commit()
    log.info("org_role_deleted", id=str(role_id), admin=str(user.id))


# ═══════════════════════════════════════════════════════════════════════════════
# ORG ROLE SKILL TARGETS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/org-roles/{role_id}/skill-targets")
async def list_skill_targets(
    role_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all skill targets for an org role."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Verify role belongs to tenant
    await _get_org_role(role_id, user.tenant_id, db)

    result = await db.execute(
        select(OrgRoleSkillTarget, Skill, ProficiencyLevel)
        .join(Skill, OrgRoleSkillTarget.skill_id == Skill.id)
        .join(ProficiencyLevel, OrgRoleSkillTarget.target_level_id == ProficiencyLevel.id)
        .where(OrgRoleSkillTarget.org_role_id == role_id)
        .order_by(Skill.name)
    )
    rows = result.all()

    return [
        {
            "id": str(target.id),
            "skill_id": str(target.skill_id),
            "skill_name": skill.name,
            "target_level_id": str(target.target_level_id),
            "target_level_label": level.label,
            "target_level_order": level.level_order,
            "created_at": target.created_at.isoformat(),
        }
        for target, skill, level in rows
    ]


@router.post("/org-roles/{role_id}/skill-targets", status_code=201)
async def upsert_skill_target(
    role_id: uuid.UUID,
    body: SkillTargetUpsert,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Upsert a skill target for an org role.

    If a target already exists for (role_id, skill_id), updates the target_level_id.
    Otherwise creates a new record.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    await _get_org_role(role_id, user.tenant_id, db)

    # Validate skill belongs to this tenant
    skill_check = await db.execute(
        select(Skill).where(Skill.id == body.skill_id, Skill.tenant_id == user.tenant_id)
    )
    skill = skill_check.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")

    # Validate target level belongs to this tenant
    level_check = await db.execute(
        select(ProficiencyLevel).where(
            ProficiencyLevel.id == body.target_level_id,
            ProficiencyLevel.tenant_id == user.tenant_id,
        )
    )
    level = level_check.scalar_one_or_none()
    if not level:
        raise HTTPException(status_code=404, detail="Proficiency level not found")

    # Check for existing target
    existing = await db.execute(
        select(OrgRoleSkillTarget).where(
            OrgRoleSkillTarget.org_role_id == role_id,
            OrgRoleSkillTarget.skill_id == body.skill_id,
        )
    )
    target = existing.scalar_one_or_none()

    if target:
        target.target_level_id = body.target_level_id
        await db.commit()
        await db.refresh(target)
        created = False
    else:
        target = OrgRoleSkillTarget(
            org_role_id=role_id,
            skill_id=body.skill_id,
            target_level_id=body.target_level_id,
        )
        db.add(target)
        await db.commit()
        await db.refresh(target)
        created = True

    log.info(
        "skill_target_upserted",
        role=str(role_id),
        skill=str(body.skill_id),
        created=created,
        admin=str(user.id),
    )
    return {
        "id": str(target.id),
        "skill_id": str(target.skill_id),
        "skill_name": skill.name,
        "target_level_id": str(target.target_level_id),
        "target_level_label": level.label,
        "created": created,
    }


@router.delete("/org-roles/{role_id}/skill-targets/{skill_id}", status_code=204)
async def remove_skill_target(
    role_id: uuid.UUID,
    skill_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a skill target from an org role."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    await _get_org_role(role_id, user.tenant_id, db)

    result = await db.execute(
        select(OrgRoleSkillTarget).where(
            OrgRoleSkillTarget.org_role_id == role_id,
            OrgRoleSkillTarget.skill_id == skill_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="Skill target not found")

    await db.delete(target)
    await db.commit()
    log.info("skill_target_removed", role=str(role_id), skill=str(skill_id), admin=str(user.id))


# ═══════════════════════════════════════════════════════════════════════════════
# USER ORG ROLE ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/users/{user_id}/org-role", status_code=200)
async def assign_org_role_to_user(
    user_id: uuid.UUID,
    body: AssignOrgRoleRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Assign an org role to a user.

    Deactivates any existing active UserOrgRole, creates a new active record,
    and updates AxisUser.active_org_role_id.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Load target user (must be in same tenant)
    target_result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id,
            AxisUser.tenant_id == user.tenant_id,
            AxisUser.is_active == True,
        )
    )
    target_user = target_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    # Validate org role belongs to this tenant
    role = await _get_org_role(body.org_role_id, user.tenant_id, db)

    # Deactivate existing active UserOrgRole entries for this user
    active_roles_result = await db.execute(
        select(UserOrgRole).where(
            UserOrgRole.user_id == user_id,
            UserOrgRole.is_active == True,
        )
    )
    for existing in active_roles_result.scalars().all():
        existing.is_active = False

    # Create new active assignment
    new_assignment = UserOrgRole(
        user_id=user_id,
        org_role_id=body.org_role_id,
        is_active=True,
    )
    db.add(new_assignment)

    # Update active_org_role_id on AxisUser
    target_user.active_org_role_id = body.org_role_id

    await db.commit()
    await db.refresh(new_assignment)

    log.info(
        "user_org_role_assigned",
        target_user=str(user_id),
        org_role=str(body.org_role_id),
        admin=str(user.id),
    )
    return {
        "user_id": str(user_id),
        "org_role_id": str(body.org_role_id),
        "org_role_name": role.name,
        "assignment_id": str(new_assignment.id),
        "assigned_at": new_assignment.assigned_at.isoformat(),
    }
