"""
API key authentication middleware.
Keys are hashed with SHA-256 before storage — raw key is never stored.

Flow:
  1. Client sends: Authorization: Bearer axisai_<raw_key>
  2. We SHA-256 hash the raw key, look up key_hash in api_keys table
  3. Attach the resolved Tenant to request state
"""
import hashlib
from typing import Annotated

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.core.database import get_db
from app.models.tenant import ApiKey, Tenant

bearer_scheme = HTTPBearer(auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hash of raw API key (what we store in the DB)."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key pair.
    Returns (raw_key, key_hash) — store hash, give raw to client.
    """
    import secrets
    raw = f"axisai_{secrets.token_urlsafe(32)}"
    return raw, hash_api_key(raw)


async def get_current_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    FastAPI dependency: validates API key and returns the authenticated Tenant.

    Usage:
        async def my_endpoint(tenant: Tenant = Depends(get_current_tenant)):
            ...
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Bearer <api_key>",
        )

    raw_key = credentials.credentials

    # Allow master key bypass for admin/setup operations
    if raw_key == settings.master_api_key:
        # Return a synthetic "master" tenant for admin operations
        # (Tenant lookup not required for master key)
        return _get_master_tenant()

    key_hash = hash_api_key(raw_key)

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .options(selectinload(ApiKey.tenant))
    )
    api_key = result.scalar_one_or_none()

    if api_key is None or not api_key.tenant.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
        )

    # Update last_used_at (fire-and-forget, don't block response)
    from datetime import datetime, timezone
    api_key.last_used_at = datetime.now(timezone.utc).isoformat()

    return api_key.tenant


def _get_master_tenant() -> Tenant:
    """Synthetic tenant for master key operations (not persisted)."""
    import uuid
    t = Tenant()
    t.id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    t.name = "master"
    t.moodle_url = "internal"
    t.is_active = True
    t.config = {}
    return t


# ── Optional auth (for public endpoints that benefit from tenant context) ─────
async def get_optional_tenant(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)],
    db: AsyncSession = Depends(get_db),
) -> Tenant | None:
    """Like get_current_tenant but returns None instead of raising 401."""
    try:
        return await get_current_tenant(credentials, db)
    except HTTPException:
        return None
