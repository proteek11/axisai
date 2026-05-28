"""
JWT utilities for the axis.edzlms.com frontend auth system.
Access token: 15-min expiry, HS256, carries user_id + role + tenant_id.
Refresh token: 7-day expiry, opaque random bytes, SHA-256 hash stored in DB.
"""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt as _bcrypt
import structlog
from jose import JWTError, jwt

from app.config import settings

log = structlog.get_logger(__name__)

ACCESS_TOKEN_EXPIRE_MINUTES = 15
REFRESH_TOKEN_EXPIRE_DAYS = 7
ALGORITHM = "HS256"


# ── Password hashing (bcrypt direct — passlib 1.7.4 is incompatible with bcrypt>=4) ──

def hash_password(plain: str) -> str:
    """bcrypt hash of a plaintext password. Cost factor = 12."""
    salt = _bcrypt.gensalt(rounds=12)
    return _bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verification. Compatible with hashes created by passlib."""
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ── JWT access token ──────────────────────────────────────────────────────────

def create_access_token(
    user_id: uuid.UUID,
    email: str,
    role: str,
    tenant_id: uuid.UUID,
) -> str:
    """
    Create a short-lived JWT access token.
    Returns the raw token string — include in Authorization: Bearer header.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "tenant_id": str(tenant_id),
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT access token.
    Raises JWTError (from python-jose) on invalid/expired token.
    """
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


# ── Refresh token ─────────────────────────────────────────────────────────────

def generate_refresh_token() -> tuple[str, str]:
    """
    Generate a secure refresh token.
    Returns (raw_token, token_hash) — store hash, send raw to client.
    """
    raw = secrets.token_urlsafe(48)  # 64-char URL-safe string
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, token_hash


def refresh_token_expiry() -> datetime:
    """Returns the expiry datetime for a new refresh token (7 days from now)."""
    return datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)


def hash_refresh_token(raw: str) -> str:
    """SHA-256 hash of raw refresh token. Used for DB lookup."""
    return hashlib.sha256(raw.encode()).hexdigest()
