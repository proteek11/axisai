"""
Pydantic schemas for the Video Asset Library API.

VideoAssetCreate       — POST /api/v1/video/assets
VideoAssetUpdate       — PATCH /api/v1/video/assets/{id}
VideoAssetResponse     — single asset representation
VideoAssetListResponse — paginated list wrapper
"""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.video_asset import ASSET_TYPES


# ── Request schemas ───────────────────────────────────────────────────────────

class VideoAssetCreate(BaseModel):
    """Body of POST /api/v1/video/assets — register a new asset URL."""

    name: str = Field(..., min_length=1, max_length=255, description="Human label")
    asset_type: str = Field(..., description=f"One of: {sorted(ASSET_TYPES)}")
    url: str = Field(..., description="Public URL of the asset")
    mime_type: str | None = Field(default=None, max_length=100)
    file_size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("asset_type")
    @classmethod
    def validate_asset_type(cls, v: str) -> str:
        if v not in ASSET_TYPES:
            raise ValueError(
                f"Unknown asset_type '{v}'. "
                f"Valid types: {sorted(ASSET_TYPES)}"
            )
        return v

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must be a full HTTP/HTTPS URL")
        return v


class VideoAssetUpdate(BaseModel):
    """
    Body of PATCH /api/v1/video/assets/{id}.
    All fields optional — only supplied fields are updated.
    """
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = None
    mime_type: str | None = None
    file_size_bytes: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str | None) -> str | None:
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("url must be a full HTTP/HTTPS URL")
        return v


# ── Response schemas ──────────────────────────────────────────────────────────

class VideoAssetResponse(BaseModel):
    """Full asset representation returned by GET / POST / PATCH."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    name: str
    asset_type: str
    url: str
    mime_type: str | None
    file_size_bytes: int | None
    metadata: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    @classmethod
    def from_orm_model(cls, obj: Any) -> "VideoAssetResponse":
        return cls(
            id=str(obj.id),
            tenant_id=str(obj.tenant_id),
            name=obj.name,
            asset_type=obj.asset_type,
            url=obj.url,
            mime_type=obj.mime_type,
            file_size_bytes=obj.file_size_bytes,
            metadata=obj.asset_metadata or {},
            is_active=obj.is_active,
            created_at=obj.created_at,
            updated_at=obj.updated_at if hasattr(obj, "updated_at") else None,
        )


class VideoAssetListResponse(BaseModel):
    """Paginated list of assets."""
    items: list[VideoAssetResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
