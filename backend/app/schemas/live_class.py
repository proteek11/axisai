"""
Pydantic schemas for Live Class (Zoom) feature.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Request schemas ───────────────────────────────────────────────────────────

class ScheduleLiveClassRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: Optional[str] = None
    scheduled_at: datetime          # UTC datetime — frontend must send in ISO 8601
    duration_minutes: int = Field(60, ge=15, le=480)
    # Per-class toggles (fall back to tenant defaults if not provided)
    auto_record: bool = True
    import_recording: bool = True
    import_attendance: bool = True
    generate_ai_outputs: bool = True
    notify_learners: bool = True


class UpdateLiveClassRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=512)
    description: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    duration_minutes: Optional[int] = Field(None, ge=15, le=480)
    import_recording: Optional[bool] = None
    import_attendance: Optional[bool] = None
    generate_ai_outputs: Optional[bool] = None
    notify_learners: Optional[bool] = None


# ── Response schemas ──────────────────────────────────────────────────────────

class AttendanceRecord(BaseModel):
    id: uuid.UUID
    user_email: Optional[str]
    user_name: Optional[str]
    joined_at: Optional[datetime]
    left_at: Optional[datetime]
    duration_seconds: Optional[int]
    attentiveness_score: Optional[float]

    class Config:
        from_attributes = True


class LiveClassSessionResponse(BaseModel):
    id: uuid.UUID
    space_id: uuid.UUID
    provider: str
    external_meeting_id: Optional[str]
    title: str
    description: Optional[str]
    scheduled_at: datetime
    duration_minutes: int
    join_url: Optional[str]
    host_url: Optional[str]
    password: Optional[str]
    status: str
    auto_record: bool
    import_recording: bool
    import_attendance: bool
    generate_ai_outputs: bool
    notify_learners: bool
    content_item_id: Optional[uuid.UUID]
    recording_duration_seconds: Optional[int]
    actual_start_at: Optional[datetime]
    actual_end_at: Optional[datetime]
    participant_count: Optional[int]
    import_error: Optional[str]
    created_by_email: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LiveClassListResponse(BaseModel):
    sessions: list[LiveClassSessionResponse]
    total: int


# ── Admin config schemas ──────────────────────────────────────────────────────

class ZoomConfigRequest(BaseModel):
    """Save Zoom credentials for a tenant (admin only)."""
    zoom_account_id: str = Field(..., min_length=1)
    zoom_client_id: str = Field(..., min_length=1)
    zoom_client_secret: str = Field(..., min_length=1)    # Plain — will be encrypted before storing
    zoom_webhook_secret: str = Field(..., min_length=1)   # Plain — will be encrypted before storing
    zoom_enabled: bool = True
    # Platform defaults (creator can override per class)
    zoom_default_auto_record: bool = True
    zoom_default_import_recording: bool = True
    zoom_default_import_attendance: bool = True
    zoom_default_generate_ai: bool = True


class ZoomConfigResponse(BaseModel):
    """Zoom config returned to admin UI — secrets are masked."""
    zoom_enabled: bool
    zoom_account_id: str
    zoom_client_id: str
    zoom_client_secret_set: bool    # True if secret is stored (never return plaintext)
    zoom_webhook_secret_set: bool
    webhook_url: str                # Shown read-only so admin knows where to point Zoom
    zoom_default_auto_record: bool
    zoom_default_import_recording: bool
    zoom_default_import_attendance: bool
    zoom_default_generate_ai: bool


class ZoomTestResponse(BaseModel):
    ok: bool
    email: Optional[str] = None
    account_id: Optional[str] = None
    plan_type: Optional[int] = None
    error: Optional[str] = None
