"""
VideoAsset — reusable media assets uploaded by a tenant for use in video jobs.

Asset types:
  character  — RGBA PNG character image (used by ConversationalRenderer, IllustrativeRenderer)
  logo       — transparent-background PNG logo (overlaid on videos)
  music      — background music MP3/WAV
  background — full-frame background image/video
  font       — custom TTF/OTF font file

Assets are tenant-scoped.  A renderer loads assets by querying:
  SELECT * FROM video_assets
  WHERE tenant_id = :tid AND asset_type = :type AND is_active = TRUE

The `url` column stores either:
  - A public CDN URL (uploaded via Moodle pluginfile or external CDN)
  - An axis-ai-managed object storage URL (future Phase 9)

`metadata` JSONB stores type-specific fields:
  character : {"name": "Alex", "voice_hint": "female_friendly", "position": "left"}
  music     : {"bpm": 120, "genre": "corporate", "duration_sec": 180}
  font      : {"weight": "bold", "style": "normal"}
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


# Valid asset types — checked at API layer
ASSET_TYPES: frozenset[str] = frozenset({
    "character", "logo", "music", "background", "font",
})


class VideoAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    One row per reusable media asset owned by a tenant.

    Assets are never deleted immediately — is_active = False marks them as
    archived so existing VideoJob records that reference the URL still work.
    """

    __tablename__ = "video_assets"

    # ── Tenant isolation ──────────────────────────────────────────────────────
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Asset identity ────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Public or CDN URL where the asset can be fetched by renderers
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Optional MIME type for download hints (image/png, audio/mpeg, etc.)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # File size for storage reporting (populated at upload time)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Type-specific extra fields (see module docstring)
    asset_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False, name="metadata")

    # Soft-delete: False = archived, hidden from renderers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    def __repr__(self) -> str:
        return (
            f"<VideoAsset type={self.asset_type} "
            f"name={self.name!r} tenant={self.tenant_id}>"
        )
