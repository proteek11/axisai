"""
Pydantic schemas for Teams (/api/v1/teams/*).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Team ────────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str
    description: str | None = None


class TeamUpdate(BaseModel):
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


class TeamResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    member_count: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamDetailResponse(TeamResponse):
    """Full team with member list."""
    members: list[MemberSummary] = []


class TeamListResponse(BaseModel):
    teams: list[TeamResponse]
    total: int


# ── Membership ────────────────────────────────────────────────────────────────

class MemberAddRequest(BaseModel):
    """Add one or more users to a team."""
    user_ids: list[uuid.UUID]


class MemberRemoveRequest(BaseModel):
    """Remove one or more users from a team."""
    user_ids: list[uuid.UUID]


# ── Space access (team grants) ─────────────────────────────────────────

class TeamAccessGrantCreate(BaseModel):
    """Grant an entire team access to a Learning Space."""
    team_id: uuid.UUID


class AccessGrantResponse(BaseModel):
    space_id: uuid.UUID
    user_id: uuid.UUID | None = None
    user_email: str | None = None
    user_name: str | None = None
    team_id: uuid.UUID | None = None
    team_name: str | None = None
    granted_at: datetime
    granted_by_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}
