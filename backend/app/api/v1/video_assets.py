"""
Video Asset Library API.

Endpoints:
  POST   /api/v1/video/assets           — register a new asset
  GET    /api/v1/video/assets           — list assets (filterable by type)
  GET    /api/v1/video/assets/{id}      — get single asset
  PATCH  /api/v1/video/assets/{id}      — update asset fields
  DELETE /api/v1/video/assets/{id}      — soft-delete (is_active = False)

All endpoints are tenant-scoped via the X-Tenant-Key header.

Pagination: ?page=1&page_size=20 (max 100 per page)
Filtering:  ?asset_type=character
Active-only: ?active_only=true (default true)
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant
from app.models.tenant import Tenant
from app.models.video_asset import ASSET_TYPES, VideoAsset
from app.schemas.video_asset import (
    VideoAssetCreate,
    VideoAssetListResponse,
    VideoAssetResponse,
    VideoAssetUpdate,
)

router = APIRouter()
log = structlog.get_logger(__name__)


# ── POST /api/v1/video/assets ─────────────────────────────────────────────────

@router.post(
    "",
    response_model=VideoAssetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_video_asset(
    body: VideoAssetCreate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoAssetResponse:
    """
    Register a new reusable asset URL for this tenant.

    The asset is immediately available for renderers to use via
    GET /api/v1/video/assets?asset_type=<type>&active_only=true.
    """
    asset = VideoAsset(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name=body.name,
        asset_type=body.asset_type,
        url=body.url,
        mime_type=body.mime_type,
        file_size_bytes=body.file_size_bytes,
        asset_metadata=body.metadata,
        is_active=True,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)

    log.info(
        "video_asset_created",
        asset_id=str(asset.id),
        tenant_id=str(tenant.id),
        asset_type=asset.asset_type,
        name=asset.name,
    )

    return VideoAssetResponse.from_orm_model(asset)


# ── GET /api/v1/video/assets ──────────────────────────────────────────────────

@router.get(
    "",
    response_model=VideoAssetListResponse,
)
async def list_video_assets(
    asset_type: str | None = Query(
        default=None,
        description=f"Filter by type. One of: {sorted(ASSET_TYPES)}",
    ),
    active_only: bool = Query(
        default=True,
        description="Only return is_active=True assets (default: true)",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoAssetListResponse:
    """
    List reusable assets owned by this tenant.

    Use ?asset_type=character to fetch all character images for a renderer.
    """
    if asset_type and asset_type not in ASSET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown asset_type '{asset_type}'. Valid: {sorted(ASSET_TYPES)}",
        )

    base_q = select(VideoAsset).where(VideoAsset.tenant_id == tenant.id)

    if asset_type:
        base_q = base_q.where(VideoAsset.asset_type == asset_type)
    if active_only:
        base_q = base_q.where(VideoAsset.is_active.is_(True))

    # Total count
    count_q = select(func.count()).select_from(base_q.subquery())
    total: int = (await db.execute(count_q)).scalar_one()

    # Paginated rows
    offset = (page - 1) * page_size
    rows_q = (
        base_q
        .order_by(VideoAsset.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).scalars().all()

    return VideoAssetListResponse(
        items=[VideoAssetResponse.from_orm_model(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(rows)) < total,
    )


# ── GET /api/v1/video/assets/{id} ────────────────────────────────────────────

@router.get(
    "/{asset_id}",
    response_model=VideoAssetResponse,
)
async def get_video_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoAssetResponse:
    """Get a single asset by its UUID."""
    asset = await _get_asset_or_404(db, tenant.id, asset_id)
    return VideoAssetResponse.from_orm_model(asset)


# ── PATCH /api/v1/video/assets/{id} ──────────────────────────────────────────

@router.patch(
    "/{asset_id}",
    response_model=VideoAssetResponse,
)
async def update_video_asset(
    asset_id: str,
    body: VideoAssetUpdate,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoAssetResponse:
    """
    Partial update — only supplied (non-None) fields are written.

    Use is_active=false to archive an asset without permanent deletion.
    """
    asset = await _get_asset_or_404(db, tenant.id, asset_id)

    if body.name is not None:
        asset.name = body.name
    if body.url is not None:
        asset.url = body.url
    if body.mime_type is not None:
        asset.mime_type = body.mime_type
    if body.file_size_bytes is not None:
        asset.file_size_bytes = body.file_size_bytes
    if body.metadata is not None:
        # Merge: existing keys preserved unless explicitly overridden
        merged = dict(asset.metadata or {})
        merged.update(body.metadata)
        asset.metadata = merged
    if body.is_active is not None:
        asset.is_active = body.is_active

    await db.commit()
    await db.refresh(asset)

    log.info(
        "video_asset_updated",
        asset_id=str(asset.id),
        tenant_id=str(tenant.id),
    )
    return VideoAssetResponse.from_orm_model(asset)


# ── DELETE /api/v1/video/assets/{id} ─────────────────────────────────────────

@router.delete(
    "/{asset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_video_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """
    Soft-delete: sets is_active = False.

    The row and URL are preserved so existing VideoJob records that already
    used this asset continue to work.  Use PATCH with is_active=true to
    restore a soft-deleted asset.
    """
    asset = await _get_asset_or_404(db, tenant.id, asset_id)
    asset.is_active = False
    await db.commit()

    log.info(
        "video_asset_soft_deleted",
        asset_id=str(asset.id),
        tenant_id=str(tenant.id),
    )


# ── Private helpers ───────────────────────────────────────────────────────────

async def _get_asset_or_404(
    db: AsyncSession, tenant_id: uuid.UUID, asset_id: str
) -> VideoAsset:
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid asset_id '{asset_id}'. Must be a UUID.",
        )

    result = await db.execute(
        select(VideoAsset).where(
            VideoAsset.id == asset_uuid,
            VideoAsset.tenant_id == tenant_id,
        )
    )
    asset = result.scalar_one_or_none()
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found for this tenant.",
        )
    return asset
