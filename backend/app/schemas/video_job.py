"""
Pydantic schemas for the video job API.

VideoJobCreateRequest    — inbound payload from Moodle plugin (POST /api/v1/video/jobs)
VideoJobCreateResponse   — 202 Accepted reply to Moodle
VideoJobStatusResponse   — GET /api/v1/video/jobs/{id} poll response
VideoJobPreviewResponse  — 202 Accepted reply to POST /{id}/preview

Note on _resolved_assets:
  Moodle sends this key with a leading underscore.  In Pydantic V2, fields
  starting with _ are private by default, so we alias it: the Python attribute
  is `resolved_assets` but the JSON key remains `_resolved_assets`.
  ConfigDict(populate_by_name=True) allows both names during deserialization.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.video_job import VIDEO_TYPES


# ── Nested schemas ────────────────────────────────────────────────────────────

class ResolvedAssets(BaseModel):
    """
    Pre-resolved public URLs for Moodle-stored assets.
    Populated by api_helper.php::resolve_asset_ids() before dispatch.
    extra="allow" accepts any future asset fields without a schema change.
    """
    model_config = ConfigDict(extra="allow")

    # Universal
    music_url: str | None = None
    logo_url: str | None = None

    # Kinetic typography
    kinetic_music_url: str | None = None

    # Slideshow / illustrative — list of image URLs
    image_urls: list[str] = Field(default_factory=list)

    # Avatar / illustrative / conversational — character image URLs
    character_urls: list[str] = Field(default_factory=list)
    character_url: str | None = None    # convenience single-char alias

    # Screencast — the uploaded screen recording
    screencast_url: str | None = None


class VideoSettings(BaseModel):
    """
    Rendering settings sent by Moodle alongside the script.
    extra="allow" means unknown fields are preserved in DB without schema changes.
    """
    model_config = ConfigDict(populate_by_name=True, extra="allow")

    # Core
    duration_seconds: int = Field(default=120, ge=5, le=600)
    resolution: Literal["720p", "1080p", "4k"] = "1080p"
    aspect_ratio: str = "16:9"

    # Voice / language
    voice: str | None = None            # TTS voice ID (e.g. "en-US-AriaNeural")

    # Branding
    brand_color_primary: str = "#2563EB"
    brand_color_secondary: str = "#FFFFFF"
    font_name: str = "Montserrat"

    # Animation
    transition: Literal["fade", "slide", "zoom", "none"] = "fade"
    kinetic_style: Literal["fadein", "zoomin", "slideup", "typewriter"] = "fadein"
    music_volume: float = Field(default=0.3, ge=0.0, le=1.0)

    # Avatar-specific (HeyGen)
    heygen_avatar_id: str | None = None
    heygen_voice_id: str | None = None

    # Conversational-specific (Step 7)
    voice_a: str | None = None          # TTS voice for character 0
    voice_b: str | None = None          # TTS voice for character 1
    voice_c: str | None = None          # TTS voice for character 2
    character_names: str | None = None  # Comma-separated, e.g. "Alex,Jamie"
    show_names: bool = True             # Show name labels above characters

    # _resolved_assets — alias so JSON key with underscore is handled correctly
    resolved_assets: ResolvedAssets = Field(
        default_factory=ResolvedAssets,
        alias="_resolved_assets",
    )


# ── Request / Response schemas ────────────────────────────────────────────────

class VideoJobCreateRequest(BaseModel):
    """
    Body of POST /api/v1/video/jobs.
    Matches the payload built by api_helper.php::dispatch_axisai().
    """
    model_config = ConfigDict(populate_by_name=True)

    job_id: int = Field(..., description="Integer PK from local_edzaxisvideo_jobs")
    video_type: str
    title: str = Field(..., min_length=1, max_length=500)
    script: str | None = None
    language: str = Field(default="en", min_length=2, max_length=10)
    settings: VideoSettings = Field(default_factory=VideoSettings)
    callback_url: str = Field(..., description="Moodle callback.php URL")

    @field_validator("video_type")
    @classmethod
    def validate_video_type(cls, v: str) -> str:
        if v not in VIDEO_TYPES:
            raise ValueError(
                f"Unknown video_type: '{v}'. "
                f"Valid types: {sorted(VIDEO_TYPES)}"
            )
        return v

    @field_validator("callback_url")
    @classmethod
    def validate_callback_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("callback_url must be a full HTTP/HTTPS URL")
        return v


class VideoJobCreateResponse(BaseModel):
    """202 Accepted — returned immediately after job is queued."""
    job_id: str          # Internal UUID (use for polling)
    moodle_job_id: int   # Echo back Moodle's original job_id
    status: str          # "queued" at creation time
    message: str


class VideoJobPreviewResponse(BaseModel):
    """202 Accepted — returned immediately after preview is queued."""
    job_id: str
    moodle_job_id: int
    status: str          # "preview_pending"
    message: str


class VideoJobStatusResponse(BaseModel):
    """GET /api/v1/video/jobs/{id} — poll response."""
    model_config = ConfigDict(from_attributes=True)

    job_id: str
    moodle_job_id: int
    video_type: str
    status: str
    progress: int
    progress_message: str | None = None
    output_url: str | None = None
    thumbnail_url: str | None = None
    preview_url: str | None = None      # Step 10 — populated when status=preview_ready
    duration_seconds: int | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class VideoJobListResponse(BaseModel):
    """GET /api/v1/video/jobs — paginated list."""
    items: list[VideoJobStatusResponse]
    total: int
    page: int
    page_size: int
    has_more: bool
