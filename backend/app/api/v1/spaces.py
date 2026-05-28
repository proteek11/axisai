"""
Learning Spaces API — full CRUD + publish + share + team access.

GET    /api/v1/spaces                         → list spaces (role-aware)
POST   /api/v1/spaces                         → create space (creator/admin)
GET    /api/v1/spaces/{id}                    → get space
PUT    /api/v1/spaces/{id}                    → update space (owner/admin)
DELETE /api/v1/spaces/{id}                    → delete space (owner/admin)
POST   /api/v1/spaces/{id}/upload             → upload file + queue AI processing (JWT auth)
POST   /api/v1/spaces/{id}/upload-url         → ingest URL (YouTube/Vimeo/showcase) + queue AI processing (JWT auth)
POST   /api/v1/spaces/{id}/items              → add content item
PUT    /api/v1/spaces/{id}/items/{iid}        → update space item
DELETE /api/v1/spaces/{id}/items/{iid}        → remove content item
POST   /api/v1/spaces/{id}/publish            → toggle publish
POST   /api/v1/spaces/{id}/share              → generate share token
POST   /api/v1/spaces/{id}/cover-image        → upload cover image (creator/admin)
GET    /api/v1/spaces/cover-images/{filename} → serve cover image (public)
GET    /api/v1/spaces/{id}/access             → list access grants (users + depts)
POST   /api/v1/spaces/{id}/access/users       → grant user access
DELETE /api/v1/spaces/{id}/access/users/{uid} → revoke user access
POST   /api/v1/spaces/{id}/access/depts       → grant team access
DELETE /api/v1/spaces/{id}/access/depts/{did} → revoke team access
GET    /api/v1/spaces/guest/{token}           → public guest access (no auth)
"""
import json
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import aiofiles
import structlog
from fastapi import Query, APIRouter, Depends, File, Form, HTTPException, Security, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from slugify import slugify
from sqlalchemy import exists, false as sa_false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.auth import get_current_user
from app.config import settings
from app.api.v1.axis_admin import get_current_ai_models as _get_ai_models
from app.core.database import get_db
from app.models.content import ContentItem, ContentOrigin, ContentStatus, ContentType
from app.models.output import AIOutput, OutputStatus, OutputType
from app.models.team import Team, TeamMember
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.space import LearningSpace, ShareToken, SpaceAccess, SpaceItem
from app.models.user import AxisUser
from pydantic import BaseModel
from app.schemas.ingest import IngestResponse
from app.schemas.team import AccessGrantResponse, TeamAccessGrantCreate
from app.schemas.space import (
    AccessGrantCreate,
    BulkReorderRequest,
    PublicSpaceResponse,
    ShareTokenCreate,
    ShareTokenResponse,
    SpaceCreate,
    SpaceItemCreate,
    SpaceItemSummary,
    SpaceItemUpdate,
    SpaceListResponse,
    SpaceResponse,
    SpaceUpdate,
)

router = APIRouter(prefix="/spaces", tags=["Learning Spaces"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_space_response(
    space: LearningSpace,
    items_with_content: list,
    learner_count: int = 0,
) -> SpaceResponse:
    item_summaries = []
    for si, ci in items_with_content:
        item_summaries.append(SpaceItemSummary(
            id=si.id,
            content_item_id=si.content_item_id,
            position=si.position,
            section_title=si.section_title,
            title_override=si.title_override,
            is_visible=si.is_visible,
            visible_outputs=si.visible_outputs,
            content_type=ci.content_type if ci else None,
            content_title=si.title_override or (ci.title if ci else None),
            content_status=ci.status if ci else None,
            source_url=ci.source_url if ci else None,
            experience_mode=ci.experience_mode if ci else None,
            created_at=si.created_at,
        ))

    return SpaceResponse(
        id=space.id,
        tenant_id=space.tenant_id,
        creator_id=space.creator_id,
        creator_name=space.creator.full_name or space.creator.email if space.creator else None,
        title=space.title,
        slug=space.slug,
        description=space.description,
        cover_image_url=space.cover_image_url,
        is_published=space.is_published,
        is_guest_accessible=space.is_guest_accessible,
        tags=space.tags,
        item_count=len(item_summaries),
        learner_count=learner_count,
        items=sorted(item_summaries, key=lambda x: x.position),
        created_at=space.created_at,
        updated_at=space.updated_at,
    )


async def _load_space_with_items(
    space_id: uuid.UUID, db: AsyncSession
) -> tuple[LearningSpace, list]:
    result = await db.execute(
        select(LearningSpace)
        .where(LearningSpace.id == space_id)
        .options(selectinload(LearningSpace.creator))
    )
    space = result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Learning Space not found")

    items_result = await db.execute(
        select(SpaceItem, ContentItem)
        .outerjoin(ContentItem, SpaceItem.content_item_id == ContentItem.id)
        .where(SpaceItem.space_id == space_id)
        .order_by(SpaceItem.position)
    )
    return space, items_result.all()


def _unique_slug(base: str) -> str:
    slug = slugify(base)[:200]
    suffix = secrets.token_hex(4)
    return f"{slug}-{suffix}"


def _check_space_access(space: LearningSpace, user: AxisUser) -> None:
    """Verify user can READ this space (non-DB check for direct access)."""
    if user.role == "admin":
        return
    if user.role == "creator" and space.creator_id == user.id:
        return
    if user.role == "learner" and not space.is_published:
        raise HTTPException(status_code=404, detail="Learning Space not found")


def _check_space_write_access(space: LearningSpace, user: AxisUser) -> None:
    """Verify user can WRITE to this space."""
    if user.role == "admin":
        return
    if user.role == "creator" and space.creator_id == user.id:
        return
    raise HTTPException(status_code=403, detail="You don't have permission to modify this space")


# ── List spaces ────────────────────────────────────────────────────────────────

@router.get("", response_model=SpaceListResponse)
async def list_spaces(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceListResponse:
    """
    List Learning Spaces.
    - admin: all spaces in tenant
    - creator: own spaces only
    - learner: spaces they have direct access to OR access via a team they belong to
    """
    user = await get_current_user(credentials.credentials, db)

    if user.role == "admin":
        result = await db.execute(
            select(LearningSpace)
            .where(LearningSpace.tenant_id == user.tenant_id)
            .options(selectinload(LearningSpace.creator))
            .order_by(LearningSpace.updated_at.desc())
        )
        spaces = result.scalars().all()

    elif user.role == "creator":
        result = await db.execute(
            select(LearningSpace)
            .where(LearningSpace.creator_id == user.id)
            .options(selectinload(LearningSpace.creator))
            .order_by(LearningSpace.updated_at.desc())
        )
        spaces = result.scalars().all()

    else:  # learner — published spaces OR direct/dept grant
        # Resilient team lookup: migration 021 may not have run yet on older deployments.
        # If team_members.team_id doesn't exist, degrade gracefully (no team-based spaces).
        dept_ids: list = []
        try:
            dept_ids_result = await db.execute(
                select(TeamMember.team_id).where(TeamMember.user_id == user.id)
            )
            dept_ids = list(dept_ids_result.scalars().all())
        except Exception:
            # Column doesn't exist yet — migration 021 pending; skip team-based access
            await db.rollback()

        # A learner sees a space if ANY of these is true:
        #   1. The space is published (open to all tenant learners)
        #   2. They have an explicit direct-user SpaceAccess record
        #   3. They belong to a team that was granted access
        access_conditions = [
            LearningSpace.is_published == True,
            exists().where(
                SpaceAccess.space_id == LearningSpace.id,
                SpaceAccess.user_id == user.id,
            ),
        ]
        if dept_ids:
            access_conditions.append(
                exists().where(
                    SpaceAccess.space_id == LearningSpace.id,
                    SpaceAccess.team_id.in_(dept_ids),
                )
            )

        query = (
            select(LearningSpace)
            .where(
                LearningSpace.tenant_id == user.tenant_id,
                LearningSpace.is_published == True,   # learners only see published spaces, even if shared
                or_(*access_conditions),
            )
            .options(selectinload(LearningSpace.creator))
            .distinct()
            .order_by(LearningSpace.updated_at.desc())
        )
        result = await db.execute(query)
        spaces = result.scalars().all()

    # Batch-fetch learner counts for all spaces in one query
    if spaces:
        from sqlalchemy import func as sa_func
        space_ids = [s.id for s in spaces]
        lc_result = await db.execute(
            select(SpaceAccess.space_id, sa_func.count(SpaceAccess.id).label("cnt"))
            .where(SpaceAccess.space_id.in_(space_ids))
            .group_by(SpaceAccess.space_id)
        )
        learner_counts = {row.space_id: row.cnt for row in lc_result}
    else:
        learner_counts = {}

    space_responses = []
    for space in spaces:
        items_result = await db.execute(
            select(SpaceItem, ContentItem)
            .outerjoin(ContentItem, SpaceItem.content_item_id == ContentItem.id)
            .where(SpaceItem.space_id == space.id)
        )
        space_responses.append(_build_space_response(
            space, items_result.all(), learner_count=learner_counts.get(space.id, 0)
        ))

    return SpaceListResponse(spaces=space_responses, total=len(space_responses))


# ── Create space ───────────────────────────────────────────────────────────────

@router.post("", response_model=SpaceResponse, status_code=status.HTTP_201_CREATED)
async def create_space(
    req: SpaceCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceResponse:
    """Create a new Learning Space. Creator or admin only."""
    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    space = LearningSpace(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        creator_id=user.id,
        title=req.title,
        slug=_unique_slug(req.title),
        description=req.description,
        cover_image_url=req.cover_image_url,
        is_published=False,
        is_guest_accessible=req.is_guest_accessible,
        tags=req.tags,
        space_metadata={},
    )
    db.add(space)
    await db.commit()
    await db.refresh(space)

    space, items = await _load_space_with_items(space.id, db)
    log.info("space_created", space_id=str(space.id), creator=str(user.id))
    return _build_space_response(space, items)


# ── Get space ──────────────────────────────────────────────────────────────────

@router.get("/{space_id}", response_model=SpaceResponse)
async def get_space(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceResponse:
    """Get a Learning Space by ID."""
    user = await get_current_user(credentials.credentials, db)
    space, items = await _load_space_with_items(space_id, db)

    if user.role == "admin":
        pass  # full access
    elif user.role == "creator" and space.creator_id == user.id:
        pass  # own space — always accessible
    elif user.role == "learner" and not space.is_published:
        # Unpublished space — check for an explicit SpaceAccess grant before refusing
        access_result = await db.execute(
            select(SpaceAccess.id).where(
                SpaceAccess.space_id == space.id,
                SpaceAccess.user_id == user.id,
            ).limit(1)
        )
        if not access_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Learning Space not found")
        # else: explicit grant exists — allow through
    elif user.role not in ("admin", "creator", "learner"):
        raise HTTPException(status_code=403, detail="Access denied")

    return _build_space_response(space, items)


# ── Update space ───────────────────────────────────────────────────────────────

@router.put("/{space_id}", response_model=SpaceResponse)
async def update_space(
    space_id: uuid.UUID,
    req: SpaceUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceResponse:
    """Update space metadata. Creator (own) or admin."""
    user = await get_current_user(credentials.credentials, db)
    space, items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    if req.title is not None:
        space.title = req.title
    if req.description is not None:
        space.description = req.description
    if req.cover_image_url is not None:
        space.cover_image_url = req.cover_image_url
    if req.tags is not None:
        space.tags = req.tags
    if req.is_guest_accessible is not None:
        space.is_guest_accessible = req.is_guest_accessible

    await db.commit()
    space, items = await _load_space_with_items(space_id, db)
    return _build_space_response(space, items)


# ── Delete space — preview + smart delete ─────────────────────────────────────

class ContentItemBrief(BaseModel):
    id: str
    title: str
    content_type: str

class SharedItemBrief(BaseModel):
    id: str
    title: str
    content_type: str
    other_space_titles: list[str]

class SpaceDeletePreview(BaseModel):
    space_id: str
    space_title: str
    total_items: int
    exclusive_items: list[ContentItemBrief]   # only in this space — user can choose to delete
    shared_items: list[SharedItemBrief]        # also in other spaces — always kept in library


@router.get(
    "/{space_id}/delete-preview",
    response_model=SpaceDeletePreview,
    summary="Preview what happens when this space is deleted",
)
async def delete_space_preview(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceDeletePreview:
    """
    Returns two lists:
    - exclusive_items: content that exists ONLY in this space — can be deleted with the space
    - shared_items: content reused in other spaces — will just be detached, never deleted
    """
    user = await get_current_user(credentials.credentials, db)
    space, items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    if not items:
        return SpaceDeletePreview(
            space_id=str(space_id),
            space_title=space.title,
            total_items=0,
            exclusive_items=[],
            shared_items=[],
        )

    content_item_ids = [si.content_item_id for si in items if si.content_item_id]

    # For each content item, count how many OTHER spaces it appears in
    from sqlalchemy import func as _func, text as _sql_text
    other_usage_result = await db.execute(
        select(
            SpaceItem.content_item_id,
            SpaceItem.space_id,
            LearningSpace.title,
        )
        .join(LearningSpace, LearningSpace.id == SpaceItem.space_id)
        .where(
            SpaceItem.content_item_id.in_(content_item_ids),
            SpaceItem.space_id != space_id,
        )
    )
    other_usage_rows = other_usage_result.all()

    # Build map: content_item_id → [other space titles]
    other_spaces_map: dict[uuid.UUID, list[str]] = {}
    for row in other_usage_rows:
        other_spaces_map.setdefault(row.content_item_id, []).append(row.title)

    exclusive: list[ContentItemBrief] = []
    shared: list[SharedItemBrief] = []

    for si in items:
        if not si.content_item_id:
            continue
        ci = await db.get(ContentItem, si.content_item_id)
        if not ci:
            continue
        other_titles = other_spaces_map.get(si.content_item_id, [])
        if other_titles:
            shared.append(SharedItemBrief(
                id=str(ci.id),
                title=ci.title or "Untitled",
                content_type=ci.content_type.value if hasattr(ci.content_type, "value") else str(ci.content_type),
                other_space_titles=other_titles[:3],  # cap at 3 for UI
            ))
        else:
            exclusive.append(ContentItemBrief(
                id=str(ci.id),
                title=ci.title or "Untitled",
                content_type=ci.content_type.value if hasattr(ci.content_type, "value") else str(ci.content_type),
            ))

    return SpaceDeletePreview(
        space_id=str(space_id),
        space_title=space.title,
        total_items=len(items),
        exclusive_items=exclusive,
        shared_items=shared,
    )


@router.delete("/{space_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_space(
    space_id: uuid.UUID,
    delete_exclusive_content: bool = Query(
        default=False,
        description="If true, also delete content items that exist only in this space. "
                    "Shared items (used in other spaces) are always kept.",
    ),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await get_current_user(credentials.credentials, db)
    space, items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    from sqlalchemy import text as _sql_text

    # Identify exclusive content items (not used in any other space)
    content_item_ids = [si.content_item_id for si in items if si.content_item_id]
    exclusive_ids: list[str] = []

    if content_item_ids and delete_exclusive_content:
        other_usage = await db.execute(
            select(SpaceItem.content_item_id)
            .where(
                SpaceItem.content_item_id.in_(content_item_ids),
                SpaceItem.space_id != space_id,
            )
        )
        shared_ids = {row[0] for row in other_usage.all()}
        exclusive_ids = [str(cid) for cid in content_item_ids if cid not in shared_ids]

    try:
        # Delete exclusive content items first (if requested)
        if exclusive_ids:
            await db.execute(
                _sql_text("DELETE FROM content_items WHERE id = ANY(:ids)"),
                {"ids": exclusive_ids},
            )

        # Delete the space — DB cascades: space_items, space_access, share_tokens, certs
        await db.execute(_sql_text("DELETE FROM learning_spaces WHERE id = :sid"), {"sid": str(space_id)})
        await db.commit()

    except Exception as _del_exc:
        await db.rollback()
        log.error("space_delete_failed", space_id=str(space_id), error=str(_del_exc))
        raise HTTPException(status_code=500, detail=f"Failed to delete space: {_del_exc}")

    # Async Qdrant cleanup for deleted content items
    if exclusive_ids:
        try:
            from app.core.qdrant import get_qdrant
            from app.services.vector.store import QdrantStore
            qdrant_client = get_qdrant()
            store = QdrantStore(client=qdrant_client)
            for cid in exclusive_ids:
                await store.delete_by_content_item(cid)
        except Exception as _qdrant_exc:
            log.warning("qdrant_cleanup_failed_on_space_delete", error=str(_qdrant_exc))

    log.info(
        "space_deleted",
        space_id=str(space_id),
        by=str(user.id),
        exclusive_deleted=len(exclusive_ids),
        shared_detached=len(content_item_ids) - len(exclusive_ids),
    )


# ── Add / update / remove items ────────────────────────────────────────────────

@router.post("/{space_id}/items", response_model=SpaceItemSummary, status_code=201)
async def add_space_item(
    space_id: uuid.UUID,
    req: SpaceItemCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceItemSummary:
    user = await get_current_user(credentials.credentials, db)
    space, existing_items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == req.content_item_id,
            ContentItem.tenant_id == user.tenant_id,
        )
    )
    ci = ci_result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    position = req.position if req.position is not None else len(existing_items)

    space_item = SpaceItem(
        id=uuid.uuid4(),
        space_id=space_id,
        content_item_id=req.content_item_id,
        position=position,
        title_override=req.title_override,
        is_visible=True,
        visible_outputs=req.visible_outputs,
    )
    db.add(space_item)
    await db.commit()
    await db.refresh(space_item)

    return SpaceItemSummary(
        id=space_item.id,
        content_item_id=space_item.content_item_id,
        position=space_item.position,
        title_override=space_item.title_override,
        is_visible=space_item.is_visible,
        visible_outputs=space_item.visible_outputs,
        content_type=ci.content_type,
        content_title=space_item.title_override or ci.title,
        content_status=ci.status,
        source_url=ci.source_url,
        experience_mode=ci.experience_mode,
        created_at=space_item.created_at,
    )


@router.put("/{space_id}/items/{item_id}", response_model=SpaceItemSummary)
async def update_space_item(
    space_id: uuid.UUID,
    item_id: uuid.UUID,
    req: SpaceItemUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceItemSummary:
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(SpaceItem, ContentItem)
        .outerjoin(ContentItem, SpaceItem.content_item_id == ContentItem.id)
        .where(SpaceItem.id == item_id, SpaceItem.space_id == space_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Space item not found")
    si, ci = row

    if req.position is not None:
        si.position = req.position
    if req.section_title is not None:
        si.section_title = req.section_title
    if req.title_override is not None:
        si.title_override = req.title_override
    if req.is_visible is not None:
        si.is_visible = req.is_visible
    if req.visible_outputs is not None:
        si.visible_outputs = req.visible_outputs
    # SCORM config fields
    if req.scorm_completion_trigger is not None:
        si.scorm_completion_trigger = req.scorm_completion_trigger
    if req.scorm_max_attempts is not None:
        si.scorm_max_attempts = req.scorm_max_attempts
    if req.scorm_grade_aggregation is not None:
        si.scorm_grade_aggregation = req.scorm_grade_aggregation

    await db.commit()
    await db.refresh(si)

    return SpaceItemSummary(
        id=si.id,
        content_item_id=si.content_item_id,
        position=si.position,
        section_title=si.section_title,
        title_override=si.title_override,
        is_visible=si.is_visible,
        visible_outputs=si.visible_outputs,
        content_type=ci.content_type if ci else None,
        content_title=si.title_override or (ci.title if ci else None),
        content_status=ci.status if ci else None,
        source_url=ci.source_url if ci else None,
        experience_mode=ci.experience_mode if ci else None,
        created_at=si.created_at,
    )


@router.delete("/{space_id}/items/{item_id}", status_code=204)
async def remove_space_item(
    space_id: uuid.UUID,
    item_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(SpaceItem).where(SpaceItem.id == item_id, SpaceItem.space_id == space_id)
    )
    si = result.scalar_one_or_none()
    if si:
        content_item_id_to_delete = str(si.content_item_id)
        await db.delete(si)
        await db.commit()
        # Clean up Qdrant vectors for this content item
        try:
            from app.core.qdrant import get_qdrant
            from app.services.vector.store import QdrantStore
            qdrant_client = get_qdrant()
            store = QdrantStore(client=qdrant_client)
            await store.delete_by_content_item(content_item_id_to_delete)
        except Exception as _qdrant_exc:
            log.warning("qdrant_cleanup_failed_on_item_remove", error=str(_qdrant_exc))


# ── Learning Path: bulk reorder + section labels ───────────────────────────────

@router.put("/{space_id}/path", status_code=204)
async def reorder_path(
    space_id: uuid.UUID,
    req: BulkReorderRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Bulk-update position and section_title for all items in a space.
    Used by the drag-and-drop Learning Path builder.
    Only the creator of the space (or an admin) can call this.
    """
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    # Load all space items in one query
    rows = (
        await db.execute(
            select(SpaceItem).where(SpaceItem.space_id == space_id)
        )
    ).scalars().all()
    item_map = {si.id: si for si in rows}

    for entry in req.items:
        si = item_map.get(entry.item_id)
        if si is None:
            raise HTTPException(
                status_code=404,
                detail=f"SpaceItem {entry.item_id} not found in this space",
            )
        si.position = entry.position
        # Allow clearing a section label by passing "" (empty string)
        si.section_title = entry.section_title if entry.section_title else None

    await db.commit()
    log.info("path_reordered", space_id=str(space_id), items=len(req.items))


# ── Publish / unpublish ────────────────────────────────────────────────────────

@router.post("/{space_id}/publish", response_model=SpaceResponse)
async def toggle_publish(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceResponse:
    user = await get_current_user(credentials.credentials, db)
    space, items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    space.is_published = not space.is_published
    await db.commit()
    space, items = await _load_space_with_items(space_id, db)
    log.info("space_publish_toggled", space_id=str(space_id), published=space.is_published)
    return _build_space_response(space, items)


# ── Share token ────────────────────────────────────────────────────────────────

@router.post("/{space_id}/share", response_model=ShareTokenResponse)
async def create_share_token(
    space_id: uuid.UUID,
    req: ShareTokenCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> ShareTokenResponse:
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    expires_at = None
    if req.expires_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=req.expires_days)

    raw_token = secrets.token_urlsafe(32)
    st = ShareToken(
        id=uuid.uuid4(),
        space_id=space_id,
        token=raw_token,
        expires_at=expires_at,
        max_access=req.max_access,
        access_count=0,
    )
    db.add(st)

    # BUG-08 FIX: Mark the space as guest-accessible when a share token is created.
    # Without this, the guest endpoint returns 403 ("Space is not publicly accessible").
    space.is_guest_accessible = True

    await db.commit()
    await db.refresh(st)

    return ShareTokenResponse(
        token=st.token,
        share_url=f"/learn/guest?token={st.token}",
        expires_at=st.expires_at,
        max_access=st.max_access,
        access_count=st.access_count,
        created_at=st.created_at,
    )


# ── Access grants — list ───────────────────────────────────────────────────────

@router.get("/{space_id}/access", response_model=list[AccessGrantResponse])
async def list_access_grants(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[AccessGrantResponse]:
    """List all access grants (direct user + team) for this space."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(SpaceAccess, AxisUser, Team)
        .outerjoin(AxisUser, SpaceAccess.user_id == AxisUser.id)
        .outerjoin(Team, SpaceAccess.team_id == Team.id)
        .where(SpaceAccess.space_id == space_id)
    )
    rows = result.all()

    return [
        AccessGrantResponse(
            space_id=row.SpaceAccess.space_id,
            user_id=row.SpaceAccess.user_id,
            user_email=row.AxisUser.email if row.AxisUser else None,
            user_name=row.AxisUser.full_name if row.AxisUser else None,
            team_id=row.SpaceAccess.team_id,
            team_name=row.Team.name if row.Team else None,
            granted_at=row.SpaceAccess.granted_at,
            granted_by_id=row.SpaceAccess.granted_by,
        )
        for row in rows
    ]


# ── Access grants — user ───────────────────────────────────────────────────────

@router.post("/{space_id}/access/users", response_model=AccessGrantResponse, status_code=201)
async def grant_user_access(
    space_id: uuid.UUID,
    req: AccessGrantCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantResponse:
    """Grant a specific user access to a Learning Space."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == req.user_id,
            AxisUser.tenant_id == user.tenant_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    existing = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.user_id == req.user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already has access")

    grant = SpaceAccess(
        id=uuid.uuid4(),
        space_id=space_id,
        user_id=req.user_id,
        team_id=None,
        granted_by=user.id,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)

    # Notify the learner that a space was shared with them
    try:
        from app.api.v1.notifications import create_notification as _create_notif
        await _create_notif(
            user_id=req.user_id,
            title=f"New learning space shared with you",
            body=f'{user.full_name or user.email} shared "{space.title}" with you.',
            link=f"/learn/{space_id}",
            notif_type="space_shared",
            db=db,
        )
        await db.commit()
    except Exception:
        pass  # never fail the share on notification error

    # Phase 13 — space_shared email (fire-and-forget)
    try:
        import asyncio as _aio
        from app.services.email import send_trigger_email as _send_trigger
        from app.config import settings as _cfg
        _frontend_url = getattr(_cfg, "frontend_url", "https://axis.edzlms.com")
        _aio.ensure_future(
            _send_trigger(
                db=db,
                trigger="space_shared",
                to_email=target.email,
                to_name=target.full_name or "",
                variables={
                    "full_name": target.full_name or target.email,
                    "shared_by": user.full_name or user.email,
                    "space_title": space.title,
                    "space_url": f"{_frontend_url}/learn/{space_id}",
                },
            )
        )
    except Exception:
        pass  # never fail the grant on email error

    return AccessGrantResponse(
        space_id=space_id,
        user_id=req.user_id,
        user_email=target.email,
        user_name=target.full_name,
        granted_at=grant.granted_at,
        granted_by_id=user.id,
    )


@router.delete("/{space_id}/access/users/{user_id}", status_code=204)
async def revoke_user_access(
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a user's direct access to a Learning Space."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.user_id == user_id,
            SpaceAccess.team_id.is_(None),
        )
    )
    grant = result.scalar_one_or_none()
    if grant:
        await db.delete(grant)
        await db.commit()


# ── Access grants — team ─────────────────────────────────────────────────

@router.post("/{space_id}/access/depts", response_model=AccessGrantResponse, status_code=201)
async def grant_team_access(
    space_id: uuid.UUID,
    req: TeamAccessGrantCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AccessGrantResponse:
    """Grant an entire team access to a Learning Space."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    # Verify team exists in same tenant
    dept_result = await db.execute(
        select(Team).where(
            Team.id == req.team_id,
            Team.tenant_id == user.tenant_id,
        )
    )
    dept = dept_result.scalar_one_or_none()
    if not dept:
        raise HTTPException(status_code=404, detail="Team not found in this tenant")

    existing = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.team_id == req.team_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Team already has access")

    grant = SpaceAccess(
        id=uuid.uuid4(),
        space_id=space_id,
        user_id=None,
        team_id=req.team_id,
        granted_by=user.id,
    )
    db.add(grant)
    await db.commit()
    await db.refresh(grant)

    return AccessGrantResponse(
        space_id=space_id,
        team_id=req.team_id,
        team_name=dept.name,
        granted_at=grant.granted_at,
        granted_by_id=user.id,
    )


@router.delete("/{space_id}/access/depts/{dept_id}", status_code=204)
async def revoke_team_access(
    space_id: uuid.UUID,
    dept_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a team's access to a Learning Space."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    result = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.team_id == dept_id,
        )
    )
    grant = result.scalar_one_or_none()
    if grant:
        await db.delete(grant)
        await db.commit()


# ── Public guest access ────────────────────────────────────────────────────────

@router.get("/guest/{token}", response_model=PublicSpaceResponse)
async def get_public_space(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> PublicSpaceResponse:
    """Public endpoint — no auth required. Validates share token."""
    result = await db.execute(
        select(ShareToken).where(ShareToken.token == token)
    )
    st = result.scalar_one_or_none()

    if not st:
        raise HTTPException(status_code=404, detail="Share link not found")

    now = datetime.now(timezone.utc)
    if st.expires_at and st.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=410, detail="Share link has expired")

    if st.max_access and st.access_count >= st.max_access:
        raise HTTPException(status_code=410, detail="Share link usage limit reached")

    space, items = await _load_space_with_items(st.space_id, db)

    if not space.is_published or not space.is_guest_accessible:
        raise HTTPException(status_code=403, detail="Space is not publicly accessible")

    st.access_count += 1
    await db.commit()

    item_summaries = [
        SpaceItemSummary(
            id=si.id,
            content_item_id=si.content_item_id,
            position=si.position,
            title_override=si.title_override,
            is_visible=si.is_visible,
            visible_outputs=si.visible_outputs,
            content_type=ci.content_type if ci else None,
            content_title=si.title_override or (ci.title if ci else None),
            content_status=ci.status if ci else None,
            source_url=ci.source_url if ci else None,
            experience_mode=ci.experience_mode if ci else None,
            created_at=si.created_at,
        )
        for si, ci in items
        if si.is_visible
    ]

    return PublicSpaceResponse(
        id=space.id,
        title=space.title,
        description=space.description,
        cover_image_url=space.cover_image_url,
        creator_name=space.creator.full_name or space.creator.email if space.creator else None,
        item_count=len(item_summaries),
        items=item_summaries,
        tags=space.tags or [],
    )


# ── Space-native file upload (JWT auth — no Moodle IDs required) ──────────────

@router.post("/{space_id}/upload", response_model=IngestResponse, status_code=202)
async def upload_file_to_space(
    space_id: uuid.UUID,
    file: UploadFile = File(...),
    content_type: str = Form(default="pdf"),
    title: str | None = Form(None),
    generate_outputs: str = Form(default='["summary"]'),  # JSON array string
    language: str = Form(default="en"),
    experience_mode: str = Form(default="standard"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Upload a file to a Learning Space and queue AI output generation.

    JWT-authenticated — designed for the standalone Next.js frontend.
    No Moodle course or module IDs required.

    Identity model:
      origin   = 'space'
      space_id = the Learning Space UUID (equivalent of moodle_course_id)
      asset_id = a new UUID generated per upload (equivalent of moodle_cmid)

    The content item is automatically linked to the space via a SpaceItem row.
    All Moodle ingest endpoints remain unchanged.
    """
    user = await get_current_user(credentials.credentials, db)

    if user.role not in ("creator", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creators and admins can upload content to a space.",
        )

    # Load space + verify write access
    space, existing_items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    # Parse generate_outputs — accept JSON array or comma-separated string
    try:
        tasks: list[str] = json.loads(generate_outputs)
        if not isinstance(tasks, list):
            tasks = ["summary"]
    except (json.JSONDecodeError, TypeError):
        tasks = [t.strip() for t in generate_outputs.split(",") if t.strip()] or ["summary"]

    # Read + validate file size (admin-controlled limit)
    from app.api.v1.axis_admin import get_upload_limit_bytes
    file_bytes = await file.read()
    max_bytes = await get_upload_limit_bytes(db)
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed: {max_bytes // (1024 * 1024)} MB. Ask your admin to increase the upload limit.",
        )

    # Persist file to upload directory
    upload_dir = getattr(settings, "upload_dir", "/tmp/axis_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    temp_filename = f"{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(upload_dir, temp_filename)
    async with aiofiles.open(temp_path, "wb") as fh:
        await fh.write(file_bytes)

    # Resolve content type — also auto-detect from file extension
    # so .txt files are stored as "text" (not "pdf") for correct UI display.
    file_ext = (file.filename or "").rsplit(".", 1)[-1].lower() if file.filename else ""
    effective_content_type = content_type.lower()
    if file_ext == "txt":
        effective_content_type = "text"

    ct_map = {
        "pdf":          ContentType.PDF,
        "text":         ContentType.TEXT,       # plain text — uses TextExtractor
        "youtube":      ContentType.YOUTUBE,
        "vimeo":        ContentType.VIMEO,
        "video_upload": ContentType.VIDEO_UPLOAD,
    }
    resolved_ct = ct_map.get(effective_content_type, ContentType.PDF)

    # Generate a unique asset_id for this upload — this IS the identity key
    # (analogous to moodle_cmid for Moodle-origin content)
    new_asset_id = uuid.uuid4()

    # Create ContentItem with space origin
    content_item = ContentItem(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        origin=ContentOrigin.SPACE.value,
        # Standalone identity — populated for space-origin content
        space_id=space_id,
        asset_id=new_asset_id,
        # Moodle fields NULL for space-origin
        moodle_course_id=None,
        moodle_cmid=None,
        # Content
        content_type=resolved_ct.value,
        source_url=f"file://{temp_path}",
        title=title or file.filename,
        status=ContentStatus.PENDING.value,
        experience_mode=experience_mode if experience_mode in ("standard", "interactive") else "standard",
        content_hash=str(new_asset_id),         # unique per upload, prevents false dedup
        processing_config={
            "tasks": tasks,
            "options": {"language": language},
        },
        moodle_metadata={
            "uploaded_by": str(user.id),
            "space_id": str(space_id),
        },
    )
    db.add(content_item)

    # Create ProcessingJob
    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "tasks": tasks,
            "options": {"language": language},
        },
    )
    db.add(job)

    # Link content item to space (SpaceItem)
    space_item = SpaceItem(
        id=uuid.uuid4(),
        space_id=space_id,
        content_item_id=content_item.id,
        position=len(existing_items),
        is_visible=True,
        visible_outputs=tasks,
    )
    db.add(space_item)

    await db.flush()

    # Dispatch Celery pipeline task
    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )

    await db.commit()

    log.info(
        "space_upload_queued",
        job_id=str(job.id),
        content_item_id=str(content_item.id),
        asset_id=str(new_asset_id),
        space_id=str(space_id),
        tasks=tasks,
        user_id=str(user.id),
    )

    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Job queued. Poll /api/v1/jobs/{job.id} for status.",
    )



# ── URL-based ingest for a Learning Space (YouTube, Vimeo, Showcase etc.) ─────

from pydantic import BaseModel as _PydanticBaseModel

class SpaceUrlIngestRequest(_PydanticBaseModel):
    source_url: str
    content_type: str  # "youtube", "vimeo", "youtube_playlist" etc.
    title: str | None = None
    generate_outputs: list[str] = ["summary"]
    language: str = "en"
    experience_mode: str = "standard"


@router.post("/{space_id}/upload-url", response_model=IngestResponse, status_code=202)
async def upload_url_to_space(
    space_id: uuid.UUID,
    req: SpaceUrlIngestRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> IngestResponse:
    """
    Ingest a URL-based content (YouTube, Vimeo, Vimeo showcase) into a Learning Space.

    No file upload needed — the pipeline fetches & processes from the URL directly.
    Returns 202 immediately; poll GET /api/v1/jobs/{job_id} for progress.

    URL formats accepted:
      YouTube  : https://www.youtube.com/watch?v=...
      Vimeo    : https://vimeo.com/VIDEO_ID
      Showcase : https://vimeo.com/showcase/SHOWCASE_ID
    """
    user = await get_current_user(credentials.credentials, db)

    if user.role not in ("creator", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only creators and admins can add content to a space.",
        )

    # Load space + verify write access
    space, existing_items = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    # Validate content type
    ct_map = {
        "youtube":   ContentType.YOUTUBE,
        "vimeo":     ContentType.VIMEO,
        "page":      ContentType.HTML_PAGE,   # Web URL / web page
        "html_page": ContentType.HTML_PAGE,   # alternate name
        "url":       ContentType.HTML_PAGE,   # alternate name
    }
    content_type_str = req.content_type.lower()
    # Map vimeo showcase → vimeo extractor (yt-dlp handles showcase natively)
    if content_type_str == "vimeo_showcase":
        content_type_str = "vimeo"
    resolved_ct = ct_map.get(content_type_str)
    if resolved_ct is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported URL content type: '{req.content_type}'. Supported: youtube, vimeo, page.",
        )

    tasks = req.generate_outputs or ["summary"]

    # Unique asset ID for deduplication identity
    new_asset_id = uuid.uuid4()

    content_item = ContentItem(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        origin=ContentOrigin.SPACE.value,
        space_id=space_id,
        asset_id=new_asset_id,
        moodle_course_id=None,
        moodle_cmid=None,
        content_type=resolved_ct.value,
        source_url=req.source_url,
        title=req.title or req.source_url,
        status=ContentStatus.PENDING.value,
        experience_mode=req.experience_mode if req.experience_mode in ("standard", "interactive") else "standard",
        content_hash=str(new_asset_id),   # unique per submission
        processing_config={
            "tasks": tasks,
            "options": {"language": req.language},
        },
        moodle_metadata={
            "uploaded_by": str(user.id),
            "space_id": str(space_id),
        },
    )
    db.add(content_item)

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=user.tenant_id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "tasks": tasks,
            "options": {"language": req.language},
        },
    )
    db.add(job)

    space_item = SpaceItem(
        id=uuid.uuid4(),
        space_id=space_id,
        content_item_id=content_item.id,
        position=len(existing_items),
        is_visible=True,
        visible_outputs=tasks,
    )
    db.add(space_item)

    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(user.tenant_id),
            "job_config": job.job_config,
            "axis_user_id": str(user.id),
        },
        queue="default",
    )

    await db.commit()

    log.info(
        "space_url_ingest_queued",
        job_id=str(job.id),
        content_item_id=str(content_item.id),
        space_id=str(space_id),
        content_type=resolved_ct.value,
        source_url=req.source_url,
        tasks=tasks,
        user_id=str(user.id),
    )

    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Job queued. Poll /api/v1/jobs/{job.id} for status.",
    )


@router.get("/debug/jobs/{content_item_id}", summary="[DEBUG] Get job error for a content item (JWT auth)")
async def debug_get_job_error(
    content_item_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Temporary debug endpoint — returns the latest ProcessingJob error for a content item.
    JWT-authenticated (no tenant API key needed).
    Remove after debugging pipeline failures.
    """
    from sqlalchemy import desc
    from app.models.job import ProcessingJob as PJ

    user = await get_current_user(credentials.credentials, db)

    result = await db.execute(
        select(PJ)
        .where(PJ.content_item_id == content_item_id)
        .order_by(desc(PJ.created_at))
        .limit(1)
    )
    job = result.scalar_one_or_none()
    if not job:
        return {"error": "No job found for this content_item_id"}

    return {
        "job_id": str(job.id),
        "status": job.status,
        "progress": job.progress,
        "progress_message": job.progress_message,
        "error_message": job.error_message,
        "error_traceback": job.error_traceback,
        "created_at": str(job.created_at),
        "updated_at": str(job.updated_at) if job.updated_at else None,
    }


# ── Learner-facing AI output endpoints (JWT auth) ─────────────────────────────
#
# These mirror /api/v1/content/{id}/outputs but authenticate via JWT instead of
# tenant API key, making them accessible from the axis.edzlms.com frontend.
# Access is enforced: the learner must have been granted access to the space.

async def _assert_space_access(
    space_id: uuid.UUID,
    user: "AxisUser",
    db: AsyncSession,
) -> LearningSpace:
    """Verify user can access this space (admin, creator-owner, published, or explicit grant)."""
    result = await db.execute(
        select(LearningSpace).where(LearningSpace.id == space_id)
    )
    space = result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")

    # Admins always have access
    if user.role == "admin":
        return space

    # Creators can access their own spaces
    if user.role == "creator" and space.creator_id == user.id:
        return space

    # Learners: published spaces are accessible to all tenant users
    if space.is_published and space.tenant_id == user.tenant_id:
        return space

    # Check explicit user-level access grant
    access_result = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.user_id == user.id,
        )
    )
    if access_result.scalar_one_or_none():
        return space

    # Check team-level access grant
    dept_ids_result = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    dept_ids = dept_ids_result.scalars().all()
    if dept_ids:
        dept_access_result = await db.execute(
            select(SpaceAccess).where(
                SpaceAccess.space_id == space_id,
                SpaceAccess.team_id.in_(dept_ids),
            )
        )
        if dept_access_result.scalar_one_or_none():
            return space

    raise HTTPException(status_code=403, detail="You do not have access to this space")


@router.get(
    "/{space_id}/items/{content_item_id}/outputs",
    summary="List all AI outputs for a space item (JWT auth)",
)
async def list_space_item_outputs(
    space_id: uuid.UUID,
    content_item_id: uuid.UUID,
    language: str = "en",
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """
    Return all available AI outputs for a content item within a space.
    Only returns output types listed in the SpaceItem.visible_outputs.
    JWT-authenticated — for learners and creators on axis.edzlms.com.
    """
    user = await get_current_user(credentials.credentials, db)
    await _assert_space_access(space_id, user, db)

    # Get SpaceItem to check visible_outputs
    si_result = await db.execute(
        select(SpaceItem).where(
            SpaceItem.space_id == space_id,
            SpaceItem.content_item_id == content_item_id,
        )
    )
    space_item = si_result.scalar_one_or_none()
    if not space_item:
        raise HTTPException(status_code=404, detail="Item not found in this space")

    visible = space_item.visible_outputs or []

    # Fetch all active outputs for this item + language
    outputs_result = await db.execute(
        select(AIOutput).where(
            AIOutput.content_item_id == content_item_id,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
    )
    all_outputs = outputs_result.scalars().all()

    return [
        {
            "output_type": o.output_type,
            "language": o.language,
            "payload": o.edited_content if o.is_teacher_edited else o.payload,
            "created_at": str(o.created_at),
        }
        for o in all_outputs
        if o.output_type in visible
    ]


@router.get(
    "/{space_id}/items/{content_item_id}/outputs/{output_type}",
    summary="Get a specific AI output for a space item (JWT auth)",
)
async def get_space_item_output(
    space_id: uuid.UUID,
    content_item_id: uuid.UUID,
    output_type: str,
    language: str = "en",
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return a single AI output (e.g. summary, quiz, flashcards) for a content item.
    Respects visible_outputs — returns 403 if the output type is not visible.
    JWT-authenticated — for learners and creators on axis.edzlms.com.
    """
    user = await get_current_user(credentials.credentials, db)
    await _assert_space_access(space_id, user, db)

    # Verify item is in this space and output type is visible
    si_result = await db.execute(
        select(SpaceItem).where(
            SpaceItem.space_id == space_id,
            SpaceItem.content_item_id == content_item_id,
        )
    )
    space_item = si_result.scalar_one_or_none()
    if not space_item:
        raise HTTPException(status_code=404, detail="Item not found in this space")

    visible = space_item.visible_outputs or []
    if output_type not in visible:
        raise HTTPException(
            status_code=403,
            detail=f"Output type '{output_type}' is not visible in this space",
        )

    # Check content item is ready
    ci_result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_item_id)
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise HTTPException(status_code=404, detail="Content item not found")
    if content_item.status == ContentStatus.PROCESSING:
        raise HTTPException(
            status_code=202,
            detail="Content is still being processed. Try again shortly.",
        )
    if content_item.status == ContentStatus.FAILED:
        raise HTTPException(
            status_code=422,
            detail="Content processing failed. Please re-upload the file.",
        )

    # Fetch the active output
    output_result = await db.execute(
        select(AIOutput).where(
            AIOutput.content_item_id == content_item_id,
            AIOutput.output_type == output_type,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = output_result.scalar_one_or_none()
    if not output:
        raise HTTPException(
            status_code=404,
            detail=f"No '{output_type}' output found. It may still be generating.",
        )

    return {
        "content_item_id": str(output.content_item_id),
        "output_type": output.output_type,
        "language": output.language,
        "payload": output.edited_content if output.is_teacher_edited else output.payload,
        "is_teacher_edited": output.is_teacher_edited,
        "created_at": str(output.created_at),
    }


# ── Learning Space Reports ─────────────────────────────────────────────────────

@router.get("/{space_id}/report")
async def get_space_report(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Creator/admin analytics dashboard for a space.

    Returns:
      - Per-learner engagement (chat sessions, messages, last active)
      - Per-content-item engagement
      - Overall summary stats

    Security: creator can only see their own space report; admin sees all.
    """
    from app.models.chat import ChatSession, ChatMessageRole
    from app.models.user import AxisUser
    from sqlalchemy import func

    user = await get_current_user(credentials.credentials, db)
    space, items_with_content = await _load_space_with_items(space_id, db)

    # Security: creator may only view their own space
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")
    if user.role == "creator" and space.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You can only view reports for your own spaces")

    # Build set of content_item_ids in this space
    ci_ids = [row[1].id for row in items_with_content if row[1] is not None]

    # ── Learner engagement ────────────────────────────────────────────────────
    # Aggregate chat sessions per axis user, limited to content in this space
    import sqlalchemy as sa
    from app.models.attempt import QuizAttempt, FlashcardReview
    from app.models.interaction import InteractionResponse

    if ci_ids:
        learner_rows = (
            await db.execute(
                select(
                    ChatSession.axis_user_id,
                    func.count(ChatSession.id).label("session_count"),
                    func.sum(ChatSession.message_count).label("total_messages"),
                    func.max(ChatSession.updated_at).label("last_active"),
                )
                .where(
                    ChatSession.axis_user_id.isnot(None),
                    ChatSession.content_item_id.in_(ci_ids),
                )
                .group_by(ChatSession.axis_user_id)
            )
        ).all()
        # Quiz activity per learner
        quiz_learner_rows = (
            await db.execute(
                select(
                    QuizAttempt.axis_user_id,
                    func.count(QuizAttempt.id).label("quiz_attempts"),
                    func.max(QuizAttempt.attempted_at).label("last_quiz"),
                )
                .where(
                    QuizAttempt.space_id == space_id,
                    QuizAttempt.content_item_id.in_(ci_ids),
                )
                .group_by(QuizAttempt.axis_user_id)
            )
        ).all()
        # IC interaction activity per learner — only count enrolled learners
        from app.models.space import SpaceAccess as _SpaceAccess
        _enrolled_subq = (
            select(_SpaceAccess.user_id)
            .where(_SpaceAccess.space_id == space_id, _SpaceAccess.user_id.isnot(None))
            .scalar_subquery()
        )
        ic_learner_rows = (
            await db.execute(
                select(
                    InteractionResponse.user_id,
                    func.count(InteractionResponse.id).label("ic_answers"),
                    func.max(InteractionResponse.answered_at).label("last_ic"),
                )
                .where(
                    InteractionResponse.content_item_id.in_(ci_ids),
                    InteractionResponse.user_id.in_(_enrolled_subq),
                )
                .group_by(InteractionResponse.user_id)
            )
        ).all()
    else:
        learner_rows = []
        quiz_learner_rows = []
        ic_learner_rows = []

    quiz_learner_map = {r.axis_user_id: r for r in quiz_learner_rows}
    ic_learner_map   = {r.user_id: r for r in ic_learner_rows}

    # Collect ALL unique learner IDs from chat, quiz, and IC sources
    all_learner_ids: set = set()
    for r in learner_rows:
        all_learner_ids.add(r.axis_user_id)
    for r in quiz_learner_rows:
        all_learner_ids.add(r.axis_user_id)
    for r in ic_learner_rows:
        all_learner_ids.add(r.user_id)

    # Build chat lookup by learner
    chat_learner_map = {r.axis_user_id: r for r in learner_rows}

    # Fetch user details for all active learners
    user_rows = (
        await db.execute(
            select(AxisUser).where(AxisUser.id.in_(all_learner_ids))
        )
    ).scalars().all() if all_learner_ids else []
    user_map = {u.id: u for u in user_rows}

    learners = []
    for uid in all_learner_ids:
        u   = user_map.get(uid)
        cr  = chat_learner_map.get(uid)
        qr  = quiz_learner_map.get(uid)
        ir  = ic_learner_map.get(uid)

        # Determine most recent activity timestamp across all sources
        timestamps = []
        if cr and cr.last_active:
            timestamps.append(cr.last_active)
        if qr and qr.last_quiz:
            timestamps.append(qr.last_quiz)
        if ir and ir.last_ic:
            timestamps.append(ir.last_ic)
        last_active = max(timestamps) if timestamps else None

        total_msgs = int(cr.total_messages or 0) if cr else 0
        learners.append({
            "user_id": str(uid),
            "email": u.email if u else "Unknown",
            "full_name": u.full_name if u else None,
            "session_count": cr.session_count if cr else 0,
            "total_messages": total_msgs,
            "quiz_attempts": int(qr.quiz_attempts or 0) if qr else 0,
            "ic_answers": int(ir.ic_answers or 0) if ir else 0,
            "last_active": last_active.isoformat() if last_active else None,
        })
    # Sort by most messages, then by quiz attempts
    learners.sort(key=lambda l: -(l["total_messages"] + l["quiz_attempts"] + l["ic_answers"]))

    # ── Per-content engagement ────────────────────────────────────────────────
    if ci_ids:
        content_rows = (
            await db.execute(
                select(
                    ChatSession.content_item_id,
                    func.count(ChatSession.id).label("session_count"),
                    func.count(ChatSession.axis_user_id.distinct()).label("unique_learners"),
                    func.sum(ChatSession.message_count).label("total_messages"),
                )
                .where(ChatSession.content_item_id.in_(ci_ids))
                .group_by(ChatSession.content_item_id)
            )
        ).all()
        # IC interactions per content item — only enrolled users
        ic_content_rows = (
            await db.execute(
                select(
                    InteractionResponse.content_item_id,
                    func.count(InteractionResponse.id).label("total_responses"),
                    func.count(InteractionResponse.user_id.distinct()).label("unique_ic_learners"),
                )
                .where(
                    InteractionResponse.content_item_id.in_(ci_ids),
                    InteractionResponse.user_id.in_(_enrolled_subq),
                )
                .group_by(InteractionResponse.content_item_id)
            )
        ).all()
    else:
        content_rows = []
        ic_content_rows = []

    content_map    = {str(r.content_item_id): r for r in content_rows}
    ic_content_map = {str(r.content_item_id): r for r in ic_content_rows}

    content_stats = []
    for si, ci in items_with_content:
        if ci is None:
            continue
        cid = str(ci.id)
        c  = content_map.get(cid)
        ic = ic_content_map.get(cid)
        content_stats.append({
            "content_item_id": cid,
            "title": si.title_override or ci.title or "Untitled",
            "content_type": ci.content_type,
            "position": si.position,
            "section_title": si.section_title,
            "session_count": c.session_count if c else 0,
            "unique_learners": max(
                c.unique_learners if c else 0,
                ic.unique_ic_learners if ic else 0,
            ),
            "total_messages": int(c.total_messages or 0) if c else 0,
            "ic_total_responses": int(ic.total_responses or 0) if ic else 0,
            "ic_unique_learners": int(ic.unique_ic_learners or 0) if ic else 0,
        })
    content_stats.sort(key=lambda x: x["position"])

    # ── Access grants (who has access) ────────────────────────────────────────
    from app.models.space import SpaceAccess
    grants = (
        await db.execute(
            select(SpaceAccess, AxisUser)
            .outerjoin(AxisUser, SpaceAccess.user_id == AxisUser.id)
            .where(SpaceAccess.space_id == space_id, SpaceAccess.user_id.isnot(None))
        )
    ).all()
    enrolled = [
        {
            "user_id": str(g[0].user_id),
            "email": g[1].email if g[1] else "Unknown",
            "full_name": g[1].full_name if g[1] else None,
        }
        for g in grants
    ]

    total_sessions = sum(l["session_count"] for l in learners)
    total_messages = sum(l["total_messages"] for l in learners)
    total_quiz     = sum(l["quiz_attempts"] for l in learners)
    total_ic       = sum(l["ic_answers"] for l in learners)

    return {
        "space_id": str(space_id),
        "space_title": space.title,
        "enrolled_count": len(enrolled),
        "active_learners": len(learners),
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "total_quiz_attempts": total_quiz,
        "total_ic_answers": total_ic,
        "enrolled": enrolled,
        "learners": learners,
        "content_stats": content_stats,
    }


@router.get("/{space_id}/me/progress")
async def get_my_space_progress(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Learner's own progress within a space they have access to.
    Returns their chat sessions per content item.
    """
    from app.models.chat import ChatSession
    from sqlalchemy import func

    user = await get_current_user(credentials.credentials, db)
    space, items_with_content = await _load_space_with_items(space_id, db)

    # Verify access — learner must have a grant or space is guest-accessible
    if user.role == "learner":
        from app.models.space import SpaceAccess
        grant = (
            await db.execute(
                select(SpaceAccess).where(
                    SpaceAccess.space_id == space_id,
                    SpaceAccess.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if not grant and not space.is_guest_accessible:
            raise HTTPException(status_code=403, detail="You don't have access to this space")

    ci_ids = [row[1].id for row in items_with_content if row[1] is not None]

    if ci_ids:
        session_rows = (
            await db.execute(
                select(
                    ChatSession.content_item_id,
                    func.count(ChatSession.id).label("session_count"),
                    func.sum(ChatSession.message_count).label("total_messages"),
                    func.max(ChatSession.updated_at).label("last_active"),
                )
                .where(
                    ChatSession.axis_user_id == user.id,
                    ChatSession.content_item_id.in_(ci_ids),
                )
                .group_by(ChatSession.content_item_id)
            )
        ).all()
    else:
        session_rows = []

    sessions_by_ci = {str(r.content_item_id): r for r in session_rows}

    # ── Content-level progress (progress_pct) ─────────────────────────────
    from app.models.content import UserContentProgress
    prog_rows = []
    if ci_ids:
        prog_rows = (
            await db.execute(
                select(
                    UserContentProgress.content_item_id,
                    UserContentProgress.progress_pct,
                )
                .where(
                    UserContentProgress.user_id == user.id,
                    UserContentProgress.content_item_id.in_(ci_ids),
                )
            )
        ).all()
    progress_by_ci = {str(r.content_item_id): r.progress_pct for r in prog_rows}

    # ── Quiz + Flashcard stats for this learner ────────────────────────────
    import sqlalchemy as sa
    from app.models.attempt import QuizAttempt, FlashcardReview

    quiz_rows, fc_rows = [], []
    if ci_ids:
        quiz_rows = (
            await db.execute(
                select(
                    QuizAttempt.content_item_id,
                    func.count(QuizAttempt.id).label("total"),
                    func.sum(sa.cast(QuizAttempt.is_correct, sa.Integer)).label("correct"),
                    func.max(QuizAttempt.attempted_at).label("last_attempt"),
                )
                .where(
                    QuizAttempt.space_id == space_id,
                    QuizAttempt.axis_user_id == user.id,
                    QuizAttempt.content_item_id.in_(ci_ids),
                )
                .group_by(QuizAttempt.content_item_id)
            )
        ).all()
        fc_rows = (
            await db.execute(
                select(
                    FlashcardReview.content_item_id,
                    func.count(FlashcardReview.id).label("total"),
                    func.sum(sa.cast(FlashcardReview.known, sa.Integer)).label("known"),
                )
                .where(
                    FlashcardReview.space_id == space_id,
                    FlashcardReview.axis_user_id == user.id,
                    FlashcardReview.content_item_id.in_(ci_ids),
                )
                .group_by(FlashcardReview.content_item_id)
            )
        ).all()

    quiz_by_ci = {str(r.content_item_id): r for r in quiz_rows}
    fc_by_ci   = {str(r.content_item_id): r for r in fc_rows}

    # ── Interactive content response stats ────────────────────────────────────
    from app.models.interaction import InteractionResponse
    ic_rows = []
    if ci_ids:
        ic_rows = (
            await db.execute(
                select(
                    InteractionResponse.content_item_id,
                    func.count(InteractionResponse.id).label("answered"),
                    func.sum(
                        sa.cast(
                            sa.case((InteractionResponse.is_correct.is_(True), 1), else_=0),
                            sa.Integer,
                        )
                    ).label("correct"),
                )
                .where(
                    InteractionResponse.content_item_id.in_(ci_ids),
                    InteractionResponse.user_id == user.id,
                )
                .group_by(InteractionResponse.content_item_id)
            )
        ).all()
    ic_by_ci = {str(r.content_item_id): r for r in ic_rows}

    items_progress = []
    for si, ci in items_with_content:
        if ci is None or not si.is_visible:
            continue
        cid = str(ci.id)
        r   = sessions_by_ci.get(cid)
        qa  = quiz_by_ci.get(cid)
        fr  = fc_by_ci.get(cid)
        ic  = ic_by_ci.get(cid)

        # Total interactions defined on this content item (IC overlay count)
        interactions_list = ci.interactions if ci.interactions else []
        ic_total    = len(interactions_list)
        ic_answered = int(ic.answered or 0) if ic else 0
        ic_correct  = int(ic.correct  or 0) if ic else 0

        items_progress.append({
            "content_item_id": cid,
            "title": si.title_override or ci.title or "Untitled",
            "content_type": ci.content_type,
            "position": si.position,
            "section_title": si.section_title,
            "content_status": ci.status,
            "session_count":   r.session_count if r else 0,
            "total_messages":  int(r.total_messages or 0) if r else 0,
            "last_active":     r.last_active.isoformat() if r and r.last_active else None,
            "progress_pct":    progress_by_ci.get(cid, 0),
            "studied":         bool(
                (r and r.session_count > 0)
                or progress_by_ci.get(cid, 0) >= 100
            ),
            "quiz_attempts":   int(qa.total or 0) if qa else 0,
            "quiz_correct":    int(qa.correct or 0) if qa else 0,
            "last_quiz_at":    qa.last_attempt.isoformat() if qa and qa.last_attempt else None,
            "flashcard_reviews": int(fr.total or 0) if fr else 0,
            "flashcard_known":   int(fr.known or 0) if fr else 0,
            # IC-specific progress
            "ic_interactions_total":    ic_total,
            "ic_interactions_answered": ic_answered,
            "ic_interactions_correct":  ic_correct,
        })
    items_progress.sort(key=lambda x: x["position"])

    studied = sum(
        1 for i in items_progress
        if i["studied"] or i["quiz_attempts"] > 0 or i["flashcard_reviews"] > 0
        or i["ic_interactions_answered"] > 0
    )
    total   = len(items_progress)
    pct     = round((studied / total) * 100) if total else 0

    return {
        "space_id": str(space_id),
        "space_title": space.title,
        "total_items": total,
        "studied_items": studied,
        "completion_pct": pct,
        "total_messages": sum(i["total_messages"] for i in items_progress),
        "total_quiz_attempts":    sum(i["quiz_attempts"] for i in items_progress),
        "total_quiz_correct":     sum(i["quiz_correct"] for i in items_progress),
        "total_flashcard_reviews": sum(i["flashcard_reviews"] for i in items_progress),
        "total_flashcard_known":   sum(i["flashcard_known"] for i in items_progress),
        "items": items_progress,
    }


# ── Learner detail report (creator/admin) ─────────────────────────────────────

@router.get("/{space_id}/report/learners/{target_user_id}")
async def get_learner_detail_report(
    space_id: uuid.UUID,
    target_user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Detailed view of one learner's engagement within a space.
    Creator can only see learners in their own space; admin sees all.
    Returns per-content sessions, messages, and a chronological chat timeline.
    """
    from app.models.chat import ChatSession, ChatMessage, ChatMessageRole
    from app.models.user import AxisUser
    from app.models.attempt import QuizAttempt, FlashcardReview
    from sqlalchemy import func
    import sqlalchemy as sa

    user = await get_current_user(credentials.credentials, db)
    space, items_with_content = await _load_space_with_items(space_id, db)

    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")
    if user.role == "creator" and space.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You can only view reports for your own spaces")

    # Fetch learner profile
    learner = (
        await db.execute(select(AxisUser).where(AxisUser.id == target_user_id))
    ).scalar_one_or_none()
    if not learner:
        raise HTTPException(status_code=404, detail="Learner not found")

    ci_ids = [row[1].id for row in items_with_content if row[1] is not None]

    # ── Per-content session summary ────────────────────────────────────────────
    session_rows = []
    if ci_ids:
        session_rows = (
            await db.execute(
                select(
                    ChatSession.content_item_id,
                    func.count(ChatSession.id).label("session_count"),
                    func.sum(ChatSession.message_count).label("total_messages"),
                    func.sum(ChatSession.total_tokens_used).label("total_tokens"),
                    func.max(ChatSession.updated_at).label("last_active"),
                )
                .where(
                    ChatSession.axis_user_id == target_user_id,
                    ChatSession.content_item_id.in_(ci_ids),
                )
                .group_by(ChatSession.content_item_id)
            )
        ).all()

    sessions_by_ci = {str(r.content_item_id): r for r in session_rows}

    items_detail = []
    for si, ci in items_with_content:
        if ci is None or not si.is_visible:
            continue
        cid = str(ci.id)
        r = sessions_by_ci.get(cid)
        # Quiz attempt stats per content item
        qa = (await db.execute(
            select(
                func.count(QuizAttempt.id).label("total"),
                func.sum(sa.cast(QuizAttempt.is_correct, sa.Integer)).label("correct"),
            ).where(
                QuizAttempt.content_item_id == ci.id,
                QuizAttempt.axis_user_id == target_user_id,
            )
        )).first()
        # Flashcard review stats per content item
        fr = (await db.execute(
            select(
                func.count(FlashcardReview.id).label("total"),
                func.sum(sa.cast(FlashcardReview.known, sa.Integer)).label("known"),
            ).where(
                FlashcardReview.content_item_id == ci.id,
                FlashcardReview.axis_user_id == target_user_id,
            )
        )).first()

        items_detail.append({
            "content_item_id": cid,
            "title": si.title_override or ci.title or "Untitled",
            "content_type": ci.content_type,
            "position": si.position,
            "section_title": si.section_title,
            "session_count": r.session_count if r else 0,
            "total_messages": int(r.total_messages or 0) if r else 0,
            "total_tokens": int(r.total_tokens or 0) if r else 0,
            "last_active": r.last_active.isoformat() if r and r.last_active else None,
            "studied": bool(r and r.session_count > 0),
            "quiz_attempts": int(qa.total or 0) if qa else 0,
            "quiz_correct": int(qa.correct or 0) if qa else 0,
            "flashcard_reviews": int(fr.total or 0) if fr else 0,
            "flashcard_known": int(fr.known or 0) if fr else 0,
        })
    items_detail.sort(key=lambda x: x["position"])

    # ── Chronological chat timeline ────────────────────────────────────────────
    all_sessions = (
        await db.execute(
            select(ChatSession)
            .where(
                ChatSession.axis_user_id == target_user_id,
                ChatSession.content_item_id.in_(ci_ids) if ci_ids else False,
            )
            .order_by(ChatSession.updated_at.desc())
            .limit(100)
        )
    ).scalars().all() if ci_ids else []

    # Get content titles for timeline
    ci_title_map = {
        str(ci.id): si.title_override or ci.title or "Untitled"
        for si, ci in items_with_content if ci is not None
    }

    timeline = [
        {
            "session_id": str(s.id),
            "content_item_id": str(s.content_item_id) if s.content_item_id else None,
            "content_title": ci_title_map.get(str(s.content_item_id), "Unknown") if s.content_item_id else None,
            "message_count": s.message_count or 0,
            "total_tokens": s.total_tokens_used or 0,
            "started_at": s.created_at.isoformat(),
            "last_active": s.updated_at.isoformat() if s.updated_at else s.created_at.isoformat(),
        }
        for s in all_sessions
    ]

    total_msgs = sum(i["total_messages"] for i in items_detail)
    studied = sum(1 for i in items_detail if i["studied"])

    return {
        "space_id": str(space_id),
        "space_title": space.title,
        "learner": {
            "user_id": str(learner.id),
            "email": learner.email,
            "full_name": learner.full_name,
            "avatar_url": learner.avatar_url,
        },
        "summary": {
            "total_items": len(items_detail),
            "studied_items": studied,
            "completion_pct": round((studied / len(items_detail)) * 100) if items_detail else 0,
            "total_sessions": sum(i["session_count"] for i in items_detail),
            "total_messages": total_msgs,
            "total_quiz_attempts": sum(i["quiz_attempts"] for i in items_detail),
            "total_quiz_correct": sum(i["quiz_correct"] for i in items_detail),
            "total_flashcard_reviews": sum(i["flashcard_reviews"] for i in items_detail),
            "total_flashcard_known": sum(i["flashcard_known"] for i in items_detail),
        },
        "items": items_detail,
        "timeline": timeline,
    }


# ── Remove learner from space ─────────────────────────────────────────────────

@router.delete("/{space_id}/members/{target_user_id}", status_code=204)
async def remove_space_member(
    space_id: uuid.UUID,
    target_user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Remove a learner's access grant from a space.
    Creator can only remove from their own space; admin can remove from any.
    """
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)

    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")
    if user.role == "creator" and space.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You can only manage your own spaces")

    result = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            SpaceAccess.user_id == target_user_id,
        )
    )
    grant = result.scalar_one_or_none()
    if grant:
        await db.delete(grant)
        await db.commit()


# ── Quiz attempt recording ─────────────────────────────────────────────────────

class QuizAttemptRequest(BaseModel):
    question_index: int
    question_text: str | None = None
    selected_index: int
    correct_index: int
    is_correct: bool
    bloom_level: str | None = None


class FlashcardReviewRequest(BaseModel):
    card_index: int
    front_text: str | None = None
    known: bool


@router.post("/{space_id}/content/{content_id}/quiz-attempt", status_code=204)
async def record_quiz_attempt(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    req: QuizAttemptRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Record a learner's answer to one quiz question. Idempotent — just appends a row."""
    user = await get_current_user(credentials.credentials, db)
    from app.models.attempt import QuizAttempt
    attempt = QuizAttempt(
        space_id=space_id,
        content_item_id=content_id,
        axis_user_id=user.id,
        question_index=req.question_index,
        question_text=req.question_text,
        selected_index=req.selected_index,
        correct_index=req.correct_index,
        is_correct=req.is_correct,
        bloom_level=req.bloom_level,
    )
    db.add(attempt)
    await db.commit()


@router.post("/{space_id}/content/{content_id}/flashcard-review", status_code=204)
async def record_flashcard_review(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    req: FlashcardReviewRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Record a learner's known/unknown result for one flashcard."""
    user = await get_current_user(credentials.credentials, db)
    from app.models.attempt import FlashcardReview
    review = FlashcardReview(
        space_id=space_id,
        content_item_id=content_id,
        axis_user_id=user.id,
        card_index=req.card_index,
        front_text=req.front_text,
        known=req.known,
    )
    db.add(review)
    await db.commit()


# ── Per-learner quiz + flashcard attempt detail (creator/admin) ───────────────

@router.get("/{space_id}/report/learner/{user_id}/quiz-attempts")
async def get_learner_attempt_detail(
    space_id: uuid.UUID,
    user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return every individual quiz attempt and flashcard review for a learner
    within a space, grouped by content item.  Creator/admin only.
    """
    from app.models.attempt import QuizAttempt, FlashcardReview
    from collections import defaultdict

    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    space, items_with_content = await _load_space_with_items(space_id, db)
    if user.role == "creator" and space.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You can only view reports for your own spaces")

    content_titles = {
        str(ci.id): (si.title_override or ci.title or "Untitled")
        for si, ci in items_with_content if ci is not None
    }

    attempts = (await db.execute(
        select(QuizAttempt)
        .where(QuizAttempt.space_id == space_id, QuizAttempt.axis_user_id == user_id)
        .order_by(QuizAttempt.content_item_id, QuizAttempt.attempted_at.asc())
    )).scalars().all()

    reviews = (await db.execute(
        select(FlashcardReview)
        .where(FlashcardReview.space_id == space_id, FlashcardReview.axis_user_id == user_id)
        .order_by(FlashcardReview.content_item_id, FlashcardReview.reviewed_at.asc())
    )).scalars().all()

    by_content: dict = defaultdict(lambda: {"quiz_attempts": [], "flashcard_reviews": []})

    for a in attempts:
        cid = str(a.content_item_id)
        by_content[cid]["quiz_attempts"].append({
            "id": str(a.id),
            "question_index": a.question_index,
            "question_text": a.question_text,
            "selected_index": a.selected_index,
            "correct_index": a.correct_index,
            "is_correct": a.is_correct,
            "bloom_level": a.bloom_level,
            "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
        })

    for r in reviews:
        cid = str(r.content_item_id)
        by_content[cid]["flashcard_reviews"].append({
            "id": str(r.id),
            "card_index": r.card_index,
            "front_text": r.front_text,
            "known": r.known,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })

    result = [
        {
            "content_item_id": cid,
            "title": content_titles.get(cid, "Unknown"),
            **data,
        }
        for cid, data in by_content.items()
    ]
    result.sort(key=lambda x: x["title"])
    return {"contents": result}


# ── Learner's own quiz/flashcard attempt history ──────────────────────────────

@router.get("/{space_id}/me/quiz-attempts")
async def get_my_quiz_attempts(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return every individual quiz attempt and flashcard review
    for the *current* learner within a space.  Grouped by content item.
    """
    from collections import defaultdict
    from app.models.attempt import QuizAttempt, FlashcardReview

    user = await get_current_user(credentials.credentials, db)
    space, items_with_content = await _load_space_with_items(space_id, db)

    # Verify access
    if user.role == "learner":
        from app.models.space import SpaceAccess
        grant = (
            await db.execute(
                select(SpaceAccess).where(
                    SpaceAccess.space_id == space_id,
                    SpaceAccess.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if not grant and not space.is_guest_accessible:
            raise HTTPException(status_code=403, detail="Access denied")

    ci_ids = [row[1].id for row in items_with_content if row[1] is not None]
    content_titles = {
        str(row[1].id): (row[0].title_override or row[1].title or "Untitled")
        for row in items_with_content
        if row[1] is not None
    }

    attempts = (
        await db.execute(
            select(QuizAttempt)
            .where(QuizAttempt.space_id == space_id, QuizAttempt.axis_user_id == user.id)
            .order_by(QuizAttempt.content_item_id, QuizAttempt.attempted_at.asc())
        )
    ).scalars().all()

    reviews = (
        await db.execute(
            select(FlashcardReview)
            .where(FlashcardReview.space_id == space_id, FlashcardReview.axis_user_id == user.id)
            .order_by(FlashcardReview.content_item_id, FlashcardReview.reviewed_at.asc())
        )
    ).scalars().all()

    by_content: dict = defaultdict(lambda: {"quiz_attempts": [], "flashcard_reviews": []})

    for a in attempts:
        cid = str(a.content_item_id)
        by_content[cid]["quiz_attempts"].append({
            "id": str(a.id),
            "question_index": a.question_index,
            "question_text": a.question_text,
            "selected_index": a.selected_index,
            "correct_index": a.correct_index,
            "is_correct": a.is_correct,
            "bloom_level": a.bloom_level,
            "attempted_at": a.attempted_at.isoformat() if a.attempted_at else None,
        })

    for r in reviews:
        cid = str(r.content_item_id)
        by_content[cid]["flashcard_reviews"].append({
            "id": str(r.id),
            "card_index": r.card_index,
            "front_text": r.front_text,
            "known": r.known,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        })

    result = [
        {"content_item_id": cid, "title": content_titles.get(cid, "Unknown"), **data}
        for cid, data in by_content.items()
    ]
    result.sort(key=lambda x: x["title"])
    return {"contents": result}


# ── Content generation settings (creator) ────────────────────────────────────

class ContentGenSettingsRequest(BaseModel):
    """PATCH /{space_id}/content/{content_id}/gen-settings"""
    quiz_count: int | None = None               # initial questions count (content_items)
    flashcard_count: int | None = None          # initial flashcards count (content_items)
    allow_learner_regen: bool | None = None     # enable Add-More button (space_items)
    max_quiz_count: int | None = None           # cap on total quiz questions
    max_flashcard_count: int | None = None      # cap on total flashcards


@router.patch("/{space_id}/content/{content_id}/gen-settings")
async def update_content_gen_settings(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    req: ContentGenSettingsRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Creator/admin: update generation count settings for a content item
    within a specific space.
    """
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    # Load the space_item (links this content to this space)
    si_row = (
        await db.execute(
            select(SpaceItem)
            .where(SpaceItem.space_id == space_id, SpaceItem.content_item_id == content_id)
        )
    ).scalar_one_or_none()
    if not si_row:
        raise HTTPException(status_code=404, detail="Content item not found in this space")

    # Load the content item itself
    ci = (await db.execute(select(ContentItem).where(ContentItem.id == content_id))).scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    # Update space_item fields
    if req.allow_learner_regen is not None:
        si_row.allow_learner_regen = req.allow_learner_regen
    if req.max_quiz_count is not None:
        si_row.max_quiz_count = max(1, req.max_quiz_count)
    if req.max_flashcard_count is not None:
        si_row.max_flashcard_count = max(1, req.max_flashcard_count)

    # Update content_item fields
    if req.quiz_count is not None:
        ci.quiz_count = max(1, req.quiz_count)
    if req.flashcard_count is not None:
        ci.flashcard_count = max(1, req.flashcard_count)

    await db.commit()

    return {
        "space_id": str(space_id),
        "content_item_id": str(content_id),
        "quiz_count": ci.quiz_count,
        "flashcard_count": ci.flashcard_count,
        "allow_learner_regen": si_row.allow_learner_regen,
        "max_quiz_count": si_row.max_quiz_count,
        "max_flashcard_count": si_row.max_flashcard_count,
    }


# ── Get gen settings + current counts (for UI) ───────────────────────────────

@router.get("/{space_id}/content/{content_id}/gen-settings")
async def get_content_gen_settings(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return generation settings + current AI output counts for a content item."""
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)

    # Learner can read to know if regen is allowed
    if user.role == "learner":
        from app.models.space import SpaceAccess
        grant = (
            await db.execute(
                select(SpaceAccess).where(
                    SpaceAccess.space_id == space_id, SpaceAccess.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if not grant and not space.is_guest_accessible:
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        _check_space_write_access(space, user)

    si_row = (
        await db.execute(
            select(SpaceItem)
            .where(SpaceItem.space_id == space_id, SpaceItem.content_item_id == content_id)
        )
    ).scalar_one_or_none()
    if not si_row:
        raise HTTPException(status_code=404, detail="Not found")

    ci = (await db.execute(select(ContentItem).where(ContentItem.id == content_id))).scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Not found")

    # Count current quiz questions and flashcards in ai_outputs
    from app.models.output import AIOutput, OutputStatus, OutputType
    quiz_out = (
        await db.execute(
            select(AIOutput)
            .where(
                AIOutput.content_item_id == content_id,
                AIOutput.output_type == OutputType.QUIZ,
                AIOutput.status == OutputStatus.ACTIVE,
            )
            .order_by(AIOutput.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    fc_out = (
        await db.execute(
            select(AIOutput)
            .where(
                AIOutput.content_item_id == content_id,
                AIOutput.output_type == OutputType.FLASHCARDS,
                AIOutput.status == OutputStatus.ACTIVE,
            )
            .order_by(AIOutput.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    current_quiz = len((quiz_out.payload or {}).get("questions", [])) if quiz_out else 0
    current_fc   = len((fc_out.payload or {}).get("cards", [])) if fc_out else 0

    return {
        "space_id": str(space_id),
        "content_item_id": str(content_id),
        "quiz_count": ci.quiz_count,
        "flashcard_count": ci.flashcard_count,
        "allow_learner_regen": si_row.allow_learner_regen,
        "max_quiz_count": si_row.max_quiz_count,
        "max_flashcard_count": si_row.max_flashcard_count,
        "current_quiz_count": current_quiz,
        "current_flashcard_count": current_fc,
        "quiz_regen_available": si_row.allow_learner_regen and current_quiz < si_row.max_quiz_count,
        "flashcard_regen_available": si_row.allow_learner_regen and current_fc < si_row.max_flashcard_count,
    }


# ── Generate more (learner/creator) ──────────────────────────────────────────

class GenerateMoreRequest(BaseModel):
    output_type: str   # "quiz" | "flashcards"
    count: int = 5     # how many to add


@router.post("/{space_id}/content/{content_id}/generate-more")
async def generate_more_content(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    req: GenerateMoreRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Learner or creator requests additional quiz questions or flashcards.
    Appends the new items to the existing AIOutput payload — learners never
    see fewer cards than before.

    Flow:
      1. Auth + access check
      2. Check allow_learner_regen (learner) or write access (creator/admin)
      3. Check current count vs max_*_count
      4. Load extracted text for the content item
      5. Call the generator with existing items injected → model avoids repeats
      6. Append new items to the existing payload + save
      7. Return the updated payload
    """
    if req.output_type not in ("quiz", "flashcards"):
        raise HTTPException(status_code=400, detail="output_type must be 'quiz' or 'flashcards'")
    if req.count < 1 or req.count > 20:
        raise HTTPException(status_code=400, detail="count must be 1–20")

    from app.models.output import AIOutput, OutputStatus, OutputType
    from app.models.content import ExtractedContent

    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)

    # ── Access + permission check ──────────────────────────────────────────
    si_row = (
        await db.execute(
            select(SpaceItem)
            .where(SpaceItem.space_id == space_id, SpaceItem.content_item_id == content_id)
        )
    ).scalar_one_or_none()
    if not si_row:
        raise HTTPException(status_code=404, detail="Content item not found in this space")

    if user.role == "learner":
        # Must have space access AND allow_learner_regen must be enabled
        from app.models.space import SpaceAccess
        grant = (
            await db.execute(
                select(SpaceAccess).where(
                    SpaceAccess.space_id == space_id, SpaceAccess.user_id == user.id
                )
            )
        ).scalar_one_or_none()
        if not grant and not space.is_guest_accessible:
            raise HTTPException(status_code=403, detail="Access denied")
        if not si_row.allow_learner_regen:
            raise HTTPException(status_code=403, detail="Content regeneration is disabled for this item")
    else:
        _check_space_write_access(space, user)

    # ── Load content item ─────────────────────────────────────────────────
    ci = (await db.execute(select(ContentItem).where(ContentItem.id == content_id))).scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    # ── Load existing AIOutput ────────────────────────────────────────────
    out_type = OutputType.QUIZ if req.output_type == "quiz" else OutputType.FLASHCARDS
    existing_output = (
        await db.execute(
            select(AIOutput)
            .where(
                AIOutput.content_item_id == content_id,
                AIOutput.output_type == out_type,
                AIOutput.status == OutputStatus.ACTIVE,
            )
            .order_by(AIOutput.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if not existing_output:
        raise HTTPException(status_code=404, detail="No existing output found — generate initial content first")

    # ── Count check ───────────────────────────────────────────────────────
    max_allowed = si_row.max_quiz_count if req.output_type == "quiz" else si_row.max_flashcard_count
    existing_items_list = (
        existing_output.payload.get("questions", []) if req.output_type == "quiz"
        else existing_output.payload.get("cards", [])
    )
    current_count = len(existing_items_list)

    if current_count >= max_allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Maximum {req.output_type} count ({max_allowed}) already reached for this content",
        )

    # Cap count to not exceed max
    count_to_add = min(req.count, max_allowed - current_count)

    # ── Load extracted text ───────────────────────────────────────────────
    extracted = (
        await db.execute(
            select(ExtractedContent)
            .where(ExtractedContent.content_item_id == content_id)
            .order_by(ExtractedContent.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not extracted or not extracted.raw_text:
        raise HTTPException(status_code=422, detail="Content text not available for generation")

    # ── Call generator ────────────────────────────────────────────────────
    from app.services.ai.client import AIClient
    from app.core.database import AsyncSessionFactory
    from app.config import settings as app_settings

    ai_client = AIClient(
        session_factory=AsyncSessionFactory,
        tenant_id=str(ci.tenant_id) if ci.tenant_id else None,
        content_item_id=str(ci.id),
    )
    _main_m, _fast_m = await _get_ai_models(db)
    _fast_output_types = {'flashcards', 'glossary', 'faq', 'mindmap', 'objectives', 'blooms', 'summary'}
    model = _fast_m if req.output_type in _fast_output_types else _main_m

    if req.output_type == "flashcards":
        from app.services.generators.flashcards import FlashcardsGenerator
        gen = FlashcardsGenerator(ai_client=ai_client)
        new_payload = await gen.generate(
            content_item=ci,
            full_text=extracted.raw_text,
            model=model,
            output_language=existing_output.language or "en",
            count=count_to_add,
            existing_items=existing_items_list,
        )
        new_items = new_payload.get("cards", [])
        merged = {**existing_output.payload, "cards": existing_items_list + new_items}
    else:
        from app.services.generators.quiz import QuizGenerator
        gen = QuizGenerator(ai_client=ai_client)
        new_payload = await gen.generate(
            content_item=ci,
            full_text=extracted.raw_text,
            model=model,
            output_language=existing_output.language or "en",
            question_count=count_to_add,
            existing_items=existing_items_list,
        )
        new_items = new_payload.get("questions", [])
        merged = {**existing_output.payload, "questions": existing_items_list + new_items}

    # ── Persist ───────────────────────────────────────────────────────────
    existing_output.payload = merged
    await db.commit()
    await db.refresh(existing_output)

    total = len(merged.get("questions", merged.get("cards", [])))
    return {
        "output_type": req.output_type,
        "added": len(new_items),
        "total": total,
        "payload": merged,
    }


# ── C-09: Update content item source URL ─────────────────────────────────────

class ContentURLUpdateRequest(BaseModel):
    """PATCH /{space_id}/content/{content_id}/url"""
    source_url: str
    title: str | None = None          # optional new title


@router.patch("/{space_id}/content/{content_id}/url")
async def update_content_url(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    req: ContentURLUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Creator/admin: update source_url (and optionally title) on a content item.
    After updating the URL the old extracted content / vectors are stale —
    the caller should trigger a regenerate job to re-process.
    """
    user = await get_current_user(credentials.credentials, db)
    space, _ = await _load_space_with_items(space_id, db)
    _check_space_write_access(space, user)

    ci = (
        await db.execute(
            select(ContentItem).where(ContentItem.id == content_id)
        )
    ).scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    ci.source_url = req.source_url
    if req.title:
        ci.title = req.title
    # Reset hash so next ingest picks up the change
    ci.source_hash = None

    await db.commit()

    return {
        "content_item_id": str(content_id),
        "source_url": ci.source_url,
        "title": ci.title,
    }


# ── C-12: AI output quality rating ───────────────────────────────────────────

class OutputQualityRequest(BaseModel):
    """PATCH /{space_id}/content/{content_id}/outputs/{output_type}/quality"""
    rating: float          # 1.0 = good, -1.0 = poor
    comment: str | None = None


@router.patch("/{space_id}/content/{content_id}/outputs/{output_type}/quality")
async def rate_output_quality(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    output_type: str,
    req: OutputQualityRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Learner or creator: rate the quality of an AI output.
    Sets quality_rating + quality_reviewed on the ai_outputs row.
    Used for future fine-tuning; does not trigger auto-regeneration.
    """
    user = await get_current_user(credentials.credentials, db)

    # Verify user has access to this space
    space, _ = await _load_space_with_items(space_id, db)
    # Allow owner/admin or any user who has explicit access
    has_access = (
        str(space.creator_id) == str(user.id)
        or user.role == "admin"
        or (await db.execute(
            select(SpaceAccess).where(
                SpaceAccess.space_id == space_id,
                SpaceAccess.user_id == user.id,
            )
        )).scalar_one_or_none() is not None
    )
    if not has_access:
        raise HTTPException(status_code=403, detail="No access to this space")

    output = (
        await db.execute(
            select(AIOutput).where(
                AIOutput.content_item_id == content_id,
                AIOutput.output_type == output_type,
            )
        )
    ).scalar_one_or_none()

    if not output:
        raise HTTPException(status_code=404, detail="Output not found")

    output.quality_rating = req.rating
    output.quality_reviewed = True
    await db.commit()

    return {
        "content_item_id": str(content_id),
        "output_type": output_type,
        "quality_rating": output.quality_rating,
        "quality_reviewed": output.quality_reviewed,
    }


# ── L-13: Translate / generate output in a different language ─────────────────

class TranslateRequest(BaseModel):
    output_type: str
    target_language: str  # e.g. "ta", "hi", "fr", "de"


@router.post("/{space_id}/items/{content_item_id}/translate")
async def translate_output(
    space_id: uuid.UUID,
    content_item_id: uuid.UUID,
    req: TranslateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Generate (or return cached) AI output in a different language.
    Learner-facing: requires space read access.
    """
    import structlog as _slog
    _log = _slog.get_logger(__name__)

    try:
        user = await get_current_user(credentials.credentials, db)
        await _assert_space_access(space_id, user, db)

        from app.models.output import AIOutput, OutputStatus, OutputType
        from app.models.content import ExtractedContent

        # Check if output in target language already exists
        existing = (
            await db.execute(
                select(AIOutput).where(
                    AIOutput.content_item_id == content_item_id,
                    AIOutput.output_type == req.output_type,
                    AIOutput.language == req.target_language,
                    AIOutput.status == OutputStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()

        if existing:
            return {
                "output_type": req.output_type,
                "language": req.target_language,
                "cached": True,
                "payload": existing.edited_content if existing.is_teacher_edited else existing.payload,
            }

        # Get content item
        ci = (
            await db.execute(
                select(ContentItem).where(ContentItem.id == content_item_id)
            )
        ).scalar_one_or_none()
        if not ci:
            raise HTTPException(404, "Content item not found")

        # Get extracted text
        extracted = (
            await db.execute(
                select(ExtractedContent)
                .where(ExtractedContent.content_item_id == content_item_id)
                .order_by(ExtractedContent.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if not extracted or not extracted.raw_text:
            raise HTTPException(422, "Content text not available for translation")

        # Resolve generator
        try:
            output_type_enum = OutputType(req.output_type)
        except ValueError:
            raise HTTPException(400, f"Unknown output_type: {req.output_type}")

        from app.services.generators import GENERATOR_REGISTRY
        from app.services.ai.client import AIClient
        from app.core.database import AsyncSessionFactory
        from app.config import settings as app_settings

        GenClass = GENERATOR_REGISTRY.get(output_type_enum)
        if not GenClass:
            raise HTTPException(400, f"No generator for output_type: {req.output_type}")

        ai_client = AIClient(
            session_factory=AsyncSessionFactory,
            content_item_id=str(content_item_id),
        )
        _main_m, _fast_m = await _get_ai_models(db)
        _fast_types = {'flashcards', 'glossary', 'faq', 'mindmap', 'objectives', 'blooms', 'summary'}
        model = _fast_m if req.output_type in _fast_types else _main_m
        gen = GenClass(ai_client=ai_client)

        payload = await gen.generate(
            content_item=ci,
            full_text=extracted.raw_text,
            model=model,
            output_language=req.target_language,
        )

        # Persist translated output
        new_output = AIOutput(
            id=uuid.uuid4(),
            content_item_id=content_item_id,
            tenant_id=ci.tenant_id,
            output_type=req.output_type,
            language=req.target_language,
            payload=payload,
            status=OutputStatus.ACTIVE,
        )
        db.add(new_output)
        await db.commit()

    except HTTPException:
        raise
    except Exception as exc:
        _log.error(
            "translate_endpoint_failed",
            output_type=req.output_type,
            target_language=req.target_language,
            content_item_id=str(content_item_id),
            space_id=str(space_id),
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Translation failed: {type(exc).__name__}: {exc}",
        ) from exc

    return {
        "output_type": req.output_type,
        "language": req.target_language,
        "cached": False,
        "payload": payload,
    }


# ── Cover image upload / serve ─────────────────────────────────────────────────

_COVER_IMAGE_DIR = os.getenv(
    "COVER_IMAGE_DIR",
    os.path.join(os.path.expanduser("~"), ".axis-cover-images"),
)
_ALLOWED_COVER_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_COVER_BYTES = 2 * 1024 * 1024  # 2 MB
_COVER_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@router.post("/{space_id}/cover-image", response_model=SpaceResponse)
async def upload_cover_image(
    space_id: uuid.UUID,
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> SpaceResponse:
    """Upload or replace the cover image for a learning space (max 2 MB, JPEG/PNG/WebP)."""
    user = await get_current_user(credentials.credentials, db)
    space = await _assert_space_write(space_id, user, db)

    if file.content_type not in _ALLOWED_COVER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{file.content_type}'. Use JPEG, PNG, or WebP.",
        )

    data = await file.read()
    if len(data) > _MAX_COVER_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Cover image must be smaller than 2 MB.",
        )

    ext = _COVER_EXT_MAP[file.content_type]  # type: ignore[index]
    os.makedirs(_COVER_IMAGE_DIR, exist_ok=True)
    filename = f"{space_id}.{ext}"

    # Remove any old cover with a different extension
    for old_ext in _COVER_EXT_MAP.values():
        old_path = os.path.join(_COVER_IMAGE_DIR, f"{space_id}.{old_ext}")
        if old_path != os.path.join(_COVER_IMAGE_DIR, filename) and os.path.exists(old_path):
            os.remove(old_path)

    dest = os.path.join(_COVER_IMAGE_DIR, filename)
    with open(dest, "wb") as f:
        f.write(data)

    space.cover_image_url = f"/api/v1/spaces/cover-images/{filename}"
    await db.commit()
    await db.refresh(space)

    log.info("cover_image_uploaded", space_id=str(space_id), size=len(data))
    items_result = await db.execute(
        select(SpaceItem, ContentItem)
        .outerjoin(ContentItem, SpaceItem.content_item_id == ContentItem.id)
        .where(SpaceItem.space_id == space.id)
    )
    return _build_space_response(space, items_result.all())


async def _assert_space_write(
    space_id: uuid.UUID, user: "AxisUser", db: AsyncSession
) -> LearningSpace:
    """Fetch space and verify write access — raises 403/404 on failure."""
    result = await db.execute(
        select(LearningSpace)
        .where(LearningSpace.id == space_id)
        .options(selectinload(LearningSpace.creator))
    )
    space = result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    _check_space_write_access(space, user)
    return space


# ── Creator Output Viewer ─────────────────────────────────────────────────────

@router.get("/{space_id}/content/{content_id}/creator-outputs")
async def get_creator_outputs(
    space_id: uuid.UUID,
    content_id: uuid.UUID,
    language: str = "en",
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return all AI-generated outputs for a content item — creator review page.

    Returns quiz questions (with correct answers), flashcards (front/back),
    glossary terms, summary, FAQ, and stats for all types.
    Creator/admin only — verifies space ownership.
    """
    from app.models.flashcard import FlashcardItem
    from app.models.glossary import GlossaryTerm
    from app.models.output import QuizQuestion

    user = await get_current_user(credentials.credentials, db)
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    # Verify space exists and belongs to this user
    sp_result = await db.execute(
        select(LearningSpace).where(LearningSpace.id == space_id)
    )
    space = sp_result.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    if space.creator_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="Not your space")

    # Verify content item exists in this space (via SpaceItem)
    si_result = await db.execute(
        select(SpaceItem).where(
            SpaceItem.space_id == space_id,
            SpaceItem.content_item_id == content_id,
        )
    )
    if not si_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Content item not in this space")

    # Load content item for title/type info
    ci_result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_id)
    )
    ci = ci_result.scalar_one_or_none()
    if not ci:
        raise HTTPException(status_code=404, detail="Content item not found")

    # ── Quiz questions ─────────────────────────────────────────────────────────
    qq_result = await db.execute(
        select(QuizQuestion)
        .where(QuizQuestion.content_item_id == content_id)
        .where(QuizQuestion.is_active.is_(True))
        .order_by(QuizQuestion.created_at)
    )
    quiz_questions = qq_result.scalars().all()

    # ── Flashcards ─────────────────────────────────────────────────────────────
    fc_result = await db.execute(
        select(FlashcardItem)
        .where(FlashcardItem.content_item_id == content_id)
        .where(FlashcardItem.is_active.is_(True))
        .order_by(FlashcardItem.created_at)
    )
    flashcards = fc_result.scalars().all()

    # ── Glossary terms ─────────────────────────────────────────────────────────
    gt_result = await db.execute(
        select(GlossaryTerm)
        .where(GlossaryTerm.content_item_id == content_id)
        .where(GlossaryTerm.is_active.is_(True))
        .order_by(GlossaryTerm.term)
    )
    glossary = gt_result.scalars().all()

    # ── AI outputs (summary, faq, mindmap, objectives, blooms) ────────────────
    ao_result = await db.execute(
        select(AIOutput)
        .where(AIOutput.content_item_id == content_id)
        .where(AIOutput.language == language)
        .where(AIOutput.status == OutputStatus.ACTIVE)
        .order_by(AIOutput.output_type, AIOutput.created_at.desc())
    )
    all_outputs = ao_result.scalars().all()

    # Deduplicate — keep most recent per type
    seen_types: set[str] = set()
    ai_outputs_map: dict[str, dict] = {}
    for o in all_outputs:
        ot = o.output_type
        if ot not in seen_types:
            seen_types.add(ot)
            payload = o.edited_content if o.is_teacher_edited else o.payload
            ai_outputs_map[ot] = {
                "output_type": ot,
                "payload": payload,
                "is_teacher_edited": o.is_teacher_edited,
                "model": o.model,
                "prompt_version": o.prompt_version,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }

    return {
        "content_item_id": str(content_id),
        "content_title": ci.title,
        "content_type": ci.content_type,
        "content_status": ci.status,
        "stats": {
            "quiz_questions": len(quiz_questions),
            "flashcards": len(flashcards),
            "glossary_terms": len(glossary),
            "ai_output_types": list(ai_outputs_map.keys()),
        },
        "quiz_questions": [
            {
                "id": str(q.id),
                "question_type": q.question_type,
                "question_text": q.question_text,
                "options": q.options,
                "correct_answer": q.correct_answer,
                "explanation": q.explanation,
                "blooms_level": q.blooms_level,
                "difficulty_label": q.difficulty_label,
                "topic_primary": q.topic_primary,
                "is_active": q.is_active,
            }
            for q in quiz_questions
        ],
        "flashcards": [
            {
                "id": str(f.id),
                "front": f.front,
                "back": f.back,
                "hint": f.hint,
                "card_type": f.card_type,
                "difficulty": f.difficulty,
                "topic": f.topic,
                "is_active": f.is_active,
            }
            for f in flashcards
        ],
        "glossary_terms": [
            {
                "id": str(g.id),
                "term": g.term,
                "definition": g.definition,
                "context": g.context,
                "category": g.category,
                "is_active": g.is_active,
            }
            for g in glossary
        ],
        "ai_outputs": ai_outputs_map,
    }


@router.get("/cover-images/{filename}", include_in_schema=False)
async def serve_cover_image(filename: str) -> FileResponse:
    """Serve a space cover image (no auth required — filenames are opaque UUIDs)."""
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = os.path.join(_COVER_IMAGE_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Cover image not found")
    ext = filename.rsplit(".", 1)[-1].lower()
    media_type = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}.get(ext, "image/jpeg")
    return FileResponse(path, media_type=media_type)


# ── Learner self-report (JWT auth, comprehensive progress for PDF export) ─────

@router.get("/{space_id}/me/report")
async def get_my_space_report(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Comprehensive progress report for the current learner in a space.
    Returns the same shape as GET /{space_id}/report/learners/{user_id}
    (creator endpoint) but scoped to the authenticated user.
    """
    from app.models.attempt import QuizAttempt, FlashcardReview
    from app.models.space import SpaceAccess
    from app.models.user import AxisUser
    import sqlalchemy as sa
    from sqlalchemy import func

    user = await get_current_user(credentials.credentials, db)
    space, items_with_content = await _load_space_with_items(space_id, db)

    # Learners must have access (creators/admins can always view their own)
    if user.role == "learner":
        grant = (
            await db.execute(
                select(SpaceAccess).where(
                    SpaceAccess.space_id == space_id,
                    SpaceAccess.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if not grant and not space.is_guest_accessible:
            raise HTTPException(status_code=403, detail="Access denied")

    ci_ids = [row[1].id for row in items_with_content if row[1] is not None]

    # Per-content quiz + flashcard stats
    items_detail = []
    for si, ci in items_with_content:
        if ci is None or not si.is_visible:
            continue
        qa = (await db.execute(
            select(
                func.count(QuizAttempt.id).label("total"),
                func.sum(sa.cast(QuizAttempt.is_correct, sa.Integer)).label("correct"),
            ).where(
                QuizAttempt.content_item_id == ci.id,
                QuizAttempt.axis_user_id == user.id,
            )
        )).first()
        fr = (await db.execute(
            select(
                func.count(FlashcardReview.id).label("total"),
                func.sum(sa.cast(FlashcardReview.known, sa.Integer)).label("known"),
            ).where(
                FlashcardReview.content_item_id == ci.id,
                FlashcardReview.axis_user_id == user.id,
            )
        )).first()
        # Determine studied status from chat sessions
        from app.models.chat import ChatSession
        has_session = (await db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.axis_user_id == user.id,
                ChatSession.content_item_id == ci.id,
            )
        )).scalar_one()
        items_detail.append({
            "content_item_id": str(ci.id),
            "title": si.title_override or ci.title or "Untitled",
            "content_type": ci.content_type,
            "position": si.position,
            "section_title": si.section_title,
            "studied": bool(has_session > 0 or (qa and qa.total > 0) or (fr and fr.total > 0)),
            "quiz_attempts": int(qa.total or 0) if qa else 0,
            "quiz_correct": int(qa.correct or 0) if qa else 0,
            "flashcard_reviews": int(fr.total or 0) if fr else 0,
            "flashcard_known": int(fr.known or 0) if fr else 0,
        })
    items_detail.sort(key=lambda x: x["position"])

    # Assessment history (if assessments model exists)
    assessment_rows = []
    try:
        from app.models.assessment import Assessment, AssessmentAttempt
        assessments = (await db.execute(
            select(Assessment).where(Assessment.space_id == space_id)
        )).scalars().all()
        for a in assessments:
            attempts = (await db.execute(
                select(AssessmentAttempt)
                .where(
                    AssessmentAttempt.assessment_id == a.id,
                    AssessmentAttempt.axis_user_id == user.id,
                )
                .order_by(AssessmentAttempt.submitted_at.asc())
            )).scalars().all()
            if attempts:
                best = max((x.score_pct for x in attempts if x.score_pct is not None), default=None)
                assessment_rows.append({
                    "assessment_id": str(a.id),
                    "title": a.title,
                    "attempt_count": len(attempts),
                    "best_score": round(best, 1) if best is not None else None,
                    "passed": any(x.passed for x in attempts if x.passed),
                    "latest_at": max(x.submitted_at for x in attempts if x.submitted_at).isoformat(),
                })
    except Exception:
        pass  # Assessments table may not exist in all environments

    # Certificate status
    cert_info = None
    try:
        from app.models.certificate import SpaceCertificate
        cert = (await db.execute(
            select(SpaceCertificate).where(
                SpaceCertificate.space_id == space_id,
                SpaceCertificate.user_id == user.id,
            ).order_by(SpaceCertificate.issued_at.desc()).limit(1)
        )).scalar_one_or_none()
        if cert:
            cert_info = {
                "issued_at": cert.issued_at.isoformat() if cert.issued_at else None,
                "learner_name": cert.learner_name,
                "learner_email": cert.learner_email,
            }
    except Exception:
        pass

    studied = sum(1 for i in items_detail if i["studied"])
    total_items = len(items_detail)

    return {
        "space_id": str(space_id),
        "space_title": space.title,
        "space_description": space.description or "",
        "learner": {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
        },
        "summary": {
            "total_items": total_items,
            "studied_items": studied,
            "completion_pct": round((studied / total_items) * 100) if total_items else 0,
            "total_quiz_attempts": sum(i["quiz_attempts"] for i in items_detail),
            "total_quiz_correct": sum(i["quiz_correct"] for i in items_detail),
            "total_flashcard_reviews": sum(i["flashcard_reviews"] for i in items_detail),
            "total_flashcard_known": sum(i["flashcard_known"] for i in items_detail),
        },
        "items": items_detail,
        "assessments": assessment_rows,
        "certificate": cert_info,
        "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
