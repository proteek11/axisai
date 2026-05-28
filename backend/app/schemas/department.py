"""
Pydantic schemas for Departments (/api/v1/departments/*).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Department ────────────────────────────────────────────────────────────────

class DepartmentCreate(BaseModel):
    name: str
    description: str | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class MemberSummary(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    added_at: datetime

    model_config = {"from_attributes": True}


class DepartmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DepartmentDetailResponse(DepartmentResponse):
    """Full department with member list."""
    members: list[MemberSummary] = []


class DepartmentListResponse(BaseModel):
    departments: list[DepartmentResponse]
    total: int


# ── Membership ────────────────────────────────────────────────────────────────

class MemberAddRequest(BaseModel):
    """Add one or more users to a department."""
    user_ids: list[uuid.UUID]


class MemberRemoveRequest(BaseModel):
    """Remove one or more users from a department."""
    user_ids: list[uuid.UUID]


# ── Space access (department grants) ─────────────────────────────────────────

class DepartmentAccessGrantCreate(BaseModel):
    """Grant an entire department access to a Learning Space."""
    department_id: uuid.UUID


class AccessGrantResponse(BaseModel):
    space_id: uuid.UUID
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    user_name: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    granted_at: datetime
    granted_by_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}
