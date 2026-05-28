"""
Admin API schemas — tenant management and user token override management.

Only accessible with a master API key (scopes: ["admin"]).
Called by the Moodle edzaiaxisfront plugin when admin saves settings.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantFeatureFlags(BaseModel):
    """Which AI output types are enabled for this tenant."""
    feature_summary: bool = True
    feature_glossary: bool = True
    feature_flashcards: bool = True
    feature_quiz: bool = True
    feature_faq: bool = True
    feature_infographic: bool = True
    feature_chatbot: bool = True
    feature_kb_chat: bool = True


class TenantRateLimits(BaseModel):
    """Rate limit baselines. 0 = unlimited."""
    chat_session_msg_limit: int = Field(50, ge=0, description="Max messages per session (0=unlimited)")
    chat_daily_msg_limit: int = Field(200, ge=0, description="Max messages per user per day (0=unlimited)")
    chat_monthly_msg_limit: int = Field(2000, ge=0, description="Max messages per user per month (0=unlimited)")
    token_monthly_limit: int = Field(5_000_000, ge=0, description="Max tokens consumed tenant-wide per month (0=unlimited)")


class TenantCreateRequest(BaseModel):
    """Create a new tenant. Called by Moodle on first plugin setup."""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable tenant name (e.g. 'Acme University')")
    moodle_url: str = Field(..., description="Base URL of the Moodle installation (must be unique)")
    features: TenantFeatureFlags = Field(default_factory=TenantFeatureFlags)
    rate_limits: TenantRateLimits = Field(default_factory=TenantRateLimits)
    config: dict = Field(default_factory=dict, description="Optional provider/model overrides")


class TenantUpdateRequest(BaseModel):
    """
    Partial update — only supply fields that changed.
    Called by Moodle every time admin saves plugin settings.
    """
    name: str | None = Field(None, max_length=255)
    is_active: bool | None = None
    features: TenantFeatureFlags | None = None
    rate_limits: TenantRateLimits | None = None
    config: dict | None = None


class TenantResponse(BaseModel):
    """Full tenant record — returned after create/update/get."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    moodle_url: str
    is_active: bool

    # Feature flags
    feature_summary: bool
    feature_glossary: bool
    feature_flashcards: bool
    feature_quiz: bool
    feature_faq: bool
    feature_infographic: bool
    feature_chatbot: bool
    feature_kb_chat: bool

    # Rate limits
    chat_session_msg_limit: int
    chat_daily_msg_limit: int
    chat_monthly_msg_limit: int
    token_monthly_limit: int

    config: dict
    created_at: datetime
    updated_at: datetime | None = None


class TenantStatusResponse(BaseModel):
    """Quick health/status for a tenant — used by Moodle plugin health check."""
    tenant_id: uuid.UUID
    name: str
    is_active: bool
    content_items_count: int
    kb_items_count: int
    active_chat_sessions: int
    features_enabled: list[str]


# ── User Token Overrides ──────────────────────────────────────────────────────

class UserTokenOverrideRequest(BaseModel):
    """Create or update a per-user rate limit override."""
    moodle_user_id: int = Field(..., description="Moodle user ID to override")
    chat_session_msg_limit: int | None = Field(None, ge=0, description="Override session msg limit (null = use tenant default)")
    chat_daily_msg_limit: int | None = Field(None, ge=0)
    chat_monthly_msg_limit: int | None = Field(None, ge=0)
    token_monthly_limit: int | None = Field(None, ge=0)
    note: str | None = Field(None, max_length=500, description="Admin note explaining this override")
    set_by_moodle_user_id: int | None = None


class UserTokenOverrideResponse(BaseModel):
    """A single user token override record."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    moodle_user_id: int
    chat_session_msg_limit: int | None
    chat_daily_msg_limit: int | None
    chat_monthly_msg_limit: int | None
    token_monthly_limit: int | None
    note: str | None
    set_by_moodle_user_id: int | None
    created_at: datetime
    updated_at: datetime | None = None


# ── Self-service tenant settings (Moodle plugin sync) ────────────────────────

class TenantSyncRateLimitsRequest(BaseModel):
    """
    Sync rate limit settings from Moodle to the tenant record.
    The tenant is identified by the API key — no tenant UUID required.
    Called by the Moodle plugin's "Sync to axis-ai" button.
    """
    chat_session_msg_limit: int = Field(..., ge=0, description="Max messages per session (0=unlimited)")
    chat_daily_msg_limit: int = Field(..., ge=0, description="Max messages per user per day (0=unlimited)")
    chat_monthly_msg_limit: int = Field(..., ge=0, description="Max messages per user per month (0=unlimited)")
    token_monthly_limit: int = Field(..., ge=0, description="Max tokens tenant-wide per month (0=unlimited)")


class TenantSyncResponse(BaseModel):
    """Response after syncing rate limits."""
    success: bool
    tenant_id: str
    message: str


# ── KB Item ───────────────────────────────────────────────────────────────────

class KBIngestRequest(BaseModel):
    """Ingest a support/KB document from a URL."""
    source_url: str = Field(..., description="Publicly accessible URL to the document (PDF preferred)")
    title: str = Field(..., min_length=1, max_length=512)
    doc_type: str = Field("support", description="support|policy|how_to|faq|announcement|other")
    language: str = Field("en", description="BCP-47 language code; 'auto' for auto-detection")
    uploaded_by_moodle_user_id: int | None = None


class KBItemResponse(BaseModel):
    """KB item record — returned after ingest and on list."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    doc_type: str
    status: str
    source_url: str | None
    chunk_count: int
    word_count: int
    is_active: bool
    uploaded_by_moodle_user_id: int | None
    created_at: datetime


class KBIngestResponse(BaseModel):
    """Response after submitting a KB document for ingestion."""
    kb_item_id: str
    job_id: str
    status: str
    message: str
