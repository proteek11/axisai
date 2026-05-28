"""
Departments API — group users for bulk Learning Space access.

GET    /api/v1/departments                        → list departments (admin/creator)
POST   /api/v1/departments                        → create department (admin)
GET    /api/v1/departments/{id}                   → get department with members
PUT    /api/v1/departments/{id}                   → update department (admin)
DELETE /api/v1/departments/{id}                   → delete department (admin)
POST   /api/v1/departments/{id}/members           → add members (admin)
DELETE /api/v1/departments/{id}/members           → remove members (admin)
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
from app.models.department import Department, DepartmentMember
from app.models.user import AxisUser
from app.schemas.department import (
    DepartmentCreate,
    DepartmentDetailResponse,
    DepartmentListResponse,
    DepartmentResponse,
    DepartmentUpdate,
    MemberAddRequest,
    MemberRemoveRequest,
    MemberSummary,
)

router = APIRouter(prefix="/departments", tags=["Departments"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


def _dept_response(dept: Department, members: list[tuple]) -> DepartmentDetailResponse:
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
    return DepartmentDetailResponse(
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


async def _load_dept(dept_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession) -> Department:
    result = await db.execute(
        select(Department).where(
            Department.id == dept_id,
            Department.tenant_id == tenant_id,
        )
    )
    dept = result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    return dept


async def _load_members(dept_id: uuid.UUID, db: AsyncSession) -> list[tuple]:
    result = await db.execute(
        select(DepartmentMember, AxisUser)
        .join(AxisUser, DepartmentMember.user_id == AxisUser.id)
        .where(DepartmentMember.department_id == dept_id)
        .order_by(AxisUser.full_name, AxisUser.email)
    )
    return result.all()


# ── List departments ──────────────────────────────────────────────────────────

@router.get("", response_model=DepartmentListResponse)
async def list_departments(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentListResponse:
    """List all departments in this tenant. Admin and creator access."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator access required")

    result = await db.execute(
        select(Department)
        .where(Department.tenant_id == user.tenant_id)
        .order_by(Department.name)
    )
    departments = result.scalars().all()

    dept_responses = []
    for dept in departments:
        members = await _load_members(dept.id, db)
        dept_responses.append(
            DepartmentResponse(
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

    return DepartmentListResponse(departments=dept_responses, total=len(dept_responses))


# ── Create department ─────────────────────────────────────────────────────────

@router.post("", response_model=DepartmentDetailResponse, status_code=201)
async def create_department(
    req: DepartmentCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentDetailResponse:
    """Create a new department. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = Department(
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

    log.info("department_created", dept_id=str(dept.id), name=dept.name, by=str(user.id))
    return _dept_response(dept, [])


# ── Get department ────────────────────────────────────────────────────────────

@router.get("/{dept_id}", response_model=DepartmentDetailResponse)
async def get_department(
    dept_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentDetailResponse:
    """Get a department with its member list. Admin or creator."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator access required")

    dept = await _load_dept(dept_id, user.tenant_id, db)
    members = await _load_members(dept_id, db)
    return _dept_response(dept, members)


# ── Update department ─────────────────────────────────────────────────────────

@router.put("/{dept_id}", response_model=DepartmentDetailResponse)
async def update_department(
    dept_id: uuid.UUID,
    req: DepartmentUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentDetailResponse:
    """Update department metadata. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(dept_id, user.tenant_id, db)

    if req.name is not None:
        dept.name = req.name
    if req.description is not None:
        dept.description = req.description
    if req.is_active is not None:
        dept.is_active = req.is_active

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(dept_id, db)
    log.info("department_updated", dept_id=str(dept_id), by=str(user.id))
    return _dept_response(dept, members)


# ── Delete department ─────────────────────────────────────────────────────────

@router.delete("/{dept_id}", status_code=204)
async def delete_department(
    dept_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a department. Admin only. Space access grants referencing this dept are cascade-deleted."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(dept_id, user.tenant_id, db)
    await db.delete(dept)
    await db.commit()
    log.info("department_deleted", dept_id=str(dept_id), by=str(user.id))


# ── Add members ───────────────────────────────────────────────────────────────

@router.post("/{dept_id}/members", status_code=200, response_model=DepartmentDetailResponse)
async def add_members(
    dept_id: uuid.UUID,
    req: MemberAddRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentDetailResponse:
    """Add one or more users to a department. Admin only. Idempotent — skips duplicates."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(dept_id, user.tenant_id, db)

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
        select(DepartmentMember.user_id).where(DepartmentMember.department_id == dept_id)
    )
    existing_ids = {row for row in existing_result.scalars().all()}

    added = 0
    for uid in req.user_ids:
        if uid not in existing_ids:
            db.add(DepartmentMember(department_id=dept_id, user_id=uid, added_by=user.id))
            added += 1

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(dept_id, db)
    log.info("members_added", dept_id=str(dept_id), count=added, by=str(user.id))
    return _dept_response(dept, members)


# ── Remove members ────────────────────────────────────────────────────────────

@router.delete("/{dept_id}/members", status_code=200, response_model=DepartmentDetailResponse)
async def remove_members(
    dept_id: uuid.UUID,
    req: MemberRemoveRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> DepartmentDetailResponse:
    """Remove one or more users from a department. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    dept = await _load_dept(dept_id, user.tenant_id, db)

    result = await db.execute(
        select(DepartmentMember).where(
            DepartmentMember.department_id == dept_id,
            DepartmentMember.user_id.in_(req.user_ids),
        )
    )
    members_to_remove = result.scalars().all()
    for m in members_to_remove:
        await db.delete(m)

    await db.commit()
    await db.refresh(dept)

    members = await _load_members(dept_id, db)
    log.info("members_removed", dept_id=str(dept_id), count=len(members_to_remove), by=str(user.id))
    return _dept_response(dept, members)
