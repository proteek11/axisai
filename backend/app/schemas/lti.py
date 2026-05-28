"""
Pydantic schemas for LTI 1.3 platform management (/api/v1/admin/lti/*).
"""
import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, HttpUrl, field_validator


class LTIPlatformCreate(BaseModel):
    """Admin registers a new Moodle (or other LMS) as an LTI platform."""
    name: str
    tenant_id: uuid.UUID
    issuer: str                  # e.g. https://lms.acme.edu
    client_id: str               # issued by Moodle
    auth_login_url: str          # Moodle OIDC auth endpoint
    auth_token_url: str          # Moodle token endpoint
    key_set_url: str             # Moodle public JWKS URL
    deployment_ids: list[str] = ["1"]


class LTIPlatformUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    auth_login_url: str | None = None
    auth_token_url: str | None = None
    key_set_url: str | None = None
    deployment_ids: list[str] | None = None


class LTIPlatformResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    issuer: str
    client_id: str
    auth_login_url: str
    auth_token_url: str
    key_set_url: str
    deployment_ids: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    # axis-ai config values to paste into Moodle (computed, not stored)
    axis_tool_url: str = ""
    axis_login_url: str = ""
    axis_jwks_url: str = ""

    model_config = {"from_attributes": True}


class LTIPlatformListResponse(BaseModel):
    platforms: list[LTIPlatformResponse]
    total: int


class LTIKeyPairResponse(BaseModel):
    """Response from POST /admin/lti/generate-keypair — paste into .env"""
    private_key_pem: str
    public_key_pem: str
    key_id: str
    env_lines: str   # Ready-to-paste .env lines
