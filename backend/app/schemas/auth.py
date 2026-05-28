"""
Pydantic schemas for the auth API (/api/v1/auth/*).
"""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 900  # seconds (15 min)
    user: "UserResponse"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None  # Populated on token rotation
    token_type: str = "bearer"
    expires_in: int = 900


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    role: str
    tenant_id: uuid.UUID
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    avatar_url: str | None = None
    # Team membership (populated separately, not from ORM attributes)
    team_id: uuid.UUID | None = None
    team_name: str | None = None

    model_config = {"from_attributes": True}


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class UserCreateRequest(BaseModel):
    """Admin-only: create a new user."""
    email: EmailStr
    password: str
    full_name: str | None = None
    role: Literal["admin", "creator", "learner"] = "learner"

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class UserUpdateRequest(BaseModel):
    """Admin-only: update an existing user."""
    email: EmailStr | None = None
    full_name: str | None = None
    role: Literal["admin", "creator", "learner"] | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class ProfileUpdateRequest(BaseModel):
    """Self-service: any user can update their own name, email, or password."""
    full_name: str | None = None
    email: EmailStr | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v
