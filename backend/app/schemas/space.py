"""
Pydantic schemas for the Learning Spaces API (/api/v1/spaces/*).
"""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ── Space ─────────────────────────────────────────────────────────────────────

class SpaceCreate(BaseModel):
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    tags: list[str] = []
    is_guest_accessible: bool = False


class SpaceUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    tags: Optional[list[str]] = None
    is_guest_accessible: Optional[bool] = None


class SpaceItemSummary(BaseModel):
    """Lightweight item summary embedded in SpaceResponse."""
    id: uuid.UUID
    content_item_id: uuid.UUID
    position: int
    section_title: Optional[str] = None
    title_override: Optional[str]
    is_visible: bool
    visible_outputs: list[str]
    content_type: Optional[str] = None   # populated from join
    content_title: Optional[str] = None  # populated from join
    content_status: Optional[str] = None # populated from join
    source_url: Optional[str] = None     # populated from join
    experience_mode: Optional[str] = None  # populated from join
    created_at: datetime

    model_config = {"from_attributes": True}


class SpaceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    creator_id: uuid.UUID
    creator_name: Optional[str] = None   # populated from join
    title: str
    slug: str
    description: Optional[str]
    cover_image_url: Optional[str]
    is_published: bool
    is_guest_accessible: bool
    tags: list[str]
    item_count: int = 0
    learner_count: int = 0
    items: list[SpaceItemSummary] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SpaceListResponse(BaseModel):
    spaces: list[SpaceResponse]
    total: int


# ── Space Item ────────────────────────────────────────────────────────────────

class SpaceItemCreate(BaseModel):
    content_item_id: uuid.UUID
    position: Optional[int] = None
    title_override: Optional[str] = None
    visible_outputs: list[str] = [
        "summary", "glossary", "flashcards", "quiz",
        "faq", "infographic", "chapters",
        "mindmap", "objectives", "blooms",
    ]


class SpaceItemUpdate(BaseModel):
    position: Optional[int] = None
    section_title: Optional[str] = None
    title_override: Optional[str] = None
    is_visible: Optional[bool] = None
    visible_outputs: Optional[list[str]] = None
    # SCORM-specific config (only relevant when content_type == 'scorm')
    scorm_completion_trigger: Optional[str] = None   # "completion_only" | "pass_required"
    scorm_max_attempts: Optional[int] = None          # None = unlimited
    scorm_grade_aggregation: Optional[str] = None     # "highest" | "average" | "latest"


class PathItemOrder(BaseModel):
    """One entry in a bulk reorder request."""
    item_id: uuid.UUID
    position: int
    section_title: Optional[str] = None


class BulkReorderRequest(BaseModel):
    """PUT /spaces/{id}/path — set new positions and section labels for all items."""
    items: list[PathItemOrder]


# ── Share Token ───────────────────────────────────────────────────────────────

class ShareTokenCreate(BaseModel):
    expires_days: Optional[int] = None   # None = never expires
    max_access: Optional[int] = None     # None = unlimited


class ShareTokenResponse(BaseModel):
    token: str
    share_url: str
    expires_at: Optional[datetime]
    max_access: Optional[int]
    access_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Access Grant ──────────────────────────────────────────────────────────────

class AccessGrantCreate(BaseModel):
    user_id: uuid.UUID


class AccessGrantResponse(BaseModel):
    space_id: uuid.UUID
    user_id: uuid.UUID
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    granted_at: datetime

    model_config = {"from_attributes": True}


# ── Public (guest) space ──────────────────────────────────────────────────────

class PublicSpaceResponse(BaseModel):
    """Stripped-down space data for unauthenticated guest access."""
    id: uuid.UUID
    title: str
    description: Optional[str]
    cover_image_url: Optional[str]
    creator_name: Optional[str]
    item_count: int
    items: list[SpaceItemSummary]
    tags: list[str] = []
