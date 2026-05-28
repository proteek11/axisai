"""
LTI 1.3 core service.

Handles:
- RSA key pair (JWKS generation + loading)
- OIDC login initiation (state/nonce generation)
- id_token JWT validation (signature, claims, nonce)
- LTI role → axis-ai role mapping
- JIT user provisioning (create-or-update on launch)
- One-time token (OTT) cookie handoff between backend and frontend
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from typing import Any

import httpx
import structlog
from jose import jwt, JWTError
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.lti import LTIPlatform
from app.models.user import AxisUser
from app.models.tenant import Tenant

log = structlog.get_logger(__name__)

# ── LTI claim namespaces ──────────────────────────────────────────────────────
_CLAIM_ROLES        = "https://purl.imsglobal.org/spec/lti/claim/roles"
_CLAIM_CUSTOM       = "https://purl.imsglobal.org/spec/lti/claim/custom"
_CLAIM_DEPLOYMENT   = "https://purl.imsglobal.org/spec/lti/claim/deployment_id"
_CLAIM_MSG_TYPE     = "https://purl.imsglobal.org/spec/lti/claim/message_type"
_CLAIM_CONTEXT      = "https://purl.imsglobal.org/spec/lti/claim/context"
_CLAIM_VERSION      = "https://purl.imsglobal.org/spec/lti/claim/version"

# ── LTI role → axis-ai role ──────────────────────────────────────────────────
_ROLE_ADMIN = {
    "http://purl.imsglobal.org/vocab/lis/v2/institution/person#Administrator",
    "http://purl.imsglobal.org/vocab/lis/v2/system/person#SysAdmin",
}
_ROLE_CREATOR = {
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#ContentDeveloper",
    "http://purl.imsglobal.org/vocab/lis/v2/membership#TeachingAssistant",
}
_ROLE_LEARNER = {
    "http://purl.imsglobal.org/vocab/lis/v2/membership#Learner",
}


# ── RSA Key Management ────────────────────────────────────────────────────────

def _load_private_key():
    """Load RSA private key from LTI_PRIVATE_KEY_PEM env var (PEM string)."""
    pem = os.getenv("LTI_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
    if not pem:
        raise RuntimeError(
            "LTI_PRIVATE_KEY_PEM not set. Run POST /api/v1/admin/lti/generate-keypair "
            "and paste the output into your .env file."
        )
    return serialization.load_pem_private_key(pem.encode(), password=None)


def generate_rsa_keypair() -> dict[str, str]:
    """Generate a new RSA-2048 key pair. Returns PEM strings + ready .env lines."""
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    key_id = f"axis-ai-{secrets.token_hex(4)}"
    env_private = private_pem.replace("\n", "\\n")
    env_lines = (
        f'LTI_KEY_ID="{key_id}"\n'
        f'LTI_PRIVATE_KEY_PEM="{env_private}"\n'
    )
    return {
        "private_key_pem": private_pem,
        "public_key_pem": public_pem,
        "key_id": key_id,
        "env_lines": env_lines,
    }


def build_jwks() -> dict:
    """Build the JWKS JSON object from the configured RSA key."""
    try:
        private_key = _load_private_key()
    except RuntimeError:
        return {"keys": []}

    pub = private_key.public_key()
    pub_numbers = pub.public_key().key_size  # just to check it loads
    # Get the raw numbers
    pub_key_obj = private_key.public_key()
    numbers = pub_key_obj.public_key().public_numbers() if hasattr(pub_key_obj, 'public_key') else pub_key_obj.public_numbers()

    def _b64url(n: int, length: int) -> str:
        return base64.urlsafe_b64encode(
            n.to_bytes(length, byteorder="big")
        ).rstrip(b"=").decode()

    key_size_bytes = (numbers.n.bit_length() + 7) // 8
    key_id = os.getenv("LTI_KEY_ID", "axis-ai-key-1")
    return {
        "keys": [{
            "kty": "RSA",
            "kid": key_id,
            "use": "sig",
            "alg": "RS256",
            "n": _b64url(numbers.n, key_size_bytes),
            "e": _b64url(numbers.e, 3),
        }]
    }


def _get_public_numbers(private_key):
    """Extract RSA public numbers from a private key object."""
    pub = private_key.public_key()
    return pub.public_numbers()


def build_jwks_safe() -> dict:
    """Build JWKS — handles missing key gracefully."""
    try:
        pem = os.getenv("LTI_PRIVATE_KEY_PEM", "").replace("\\n", "\n").strip()
        if not pem:
            return {"keys": []}
        private_key = serialization.load_pem_private_key(pem.encode(), password=None)
        pub_numbers = private_key.public_key().public_numbers()

        def b64url(n: int, length: int) -> str:
            return base64.urlsafe_b64encode(
                n.to_bytes(length, byteorder="big")
            ).rstrip(b"=").decode()

        key_size_bytes = (pub_numbers.n.bit_length() + 7) // 8
        key_id = os.getenv("LTI_KEY_ID", "axis-ai-key-1")
        return {
            "keys": [{
                "kty": "RSA",
                "kid": key_id,
                "use": "sig",
                "alg": "RS256",
                "n": b64url(pub_numbers.n, key_size_bytes),
                "e": b64url(pub_numbers.e, 3),
            }]
        }
    except Exception as exc:
        log.warning("lti.jwks.build_failed", error=str(exc))
        return {"keys": []}


# ── Platform lookup ───────────────────────────────────────────────────────────

async def get_platform(
    db: AsyncSession, issuer: str, client_id: str
) -> LTIPlatform | None:
    result = await db.execute(
        select(LTIPlatform).where(
            LTIPlatform.issuer == issuer,
            LTIPlatform.client_id == client_id,
            LTIPlatform.is_active == True,
        )
    )
    return result.scalar_one_or_none()


# ── OIDC login / state management ────────────────────────────────────────────

async def create_oidc_state(
    issuer: str,
    client_id: str,
    target_link_uri: str,
    login_hint: str,
    lti_message_hint: str | None,
) -> tuple[str, str]:
    """
    Generate state + nonce, store in Redis (10 min TTL).
    Returns (state, nonce).
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    redis = await get_redis()
    payload = json.dumps({
        "nonce": nonce,
        "issuer": issuer,
        "client_id": client_id,
        "target_link_uri": target_link_uri,
        "login_hint": login_hint,
        "lti_message_hint": lti_message_hint,
        "created_at": time.time(),
    })
    await redis.setex(f"lti:state:{state}", 600, payload)
    return state, nonce


async def consume_oidc_state(state: str) -> dict | None:
    """Retrieve and DELETE state from Redis (one-time use)."""
    redis = await get_redis()
    key = f"lti:state:{state}"
    payload = await redis.get(key)
    if not payload:
        return None
    await redis.delete(key)
    return json.loads(payload)


# ── JWKS fetch + caching ──────────────────────────────────────────────────────

async def fetch_platform_jwks(key_set_url: str) -> list[dict]:
    """Fetch the platform's JWKS (Moodle public keys). Cached in Redis 1h."""
    redis = await get_redis()
    cache_key = f"lti:jwks:{hashlib.sha256(key_set_url.encode()).hexdigest()}"
    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached).get("keys", [])
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(key_set_url)
        resp.raise_for_status()
        jwks = resp.json()
    await redis.setex(cache_key, 3600, json.dumps(jwks))
    return jwks.get("keys", [])


def _jwk_to_public_key(jwk: dict):
    """Convert a JWK dict (RSA) to a cryptography public key object."""
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers

    def b64url_to_int(s: str) -> int:
        padded = s + "=" * (4 - len(s) % 4)
        return int.from_bytes(base64.urlsafe_b64decode(padded), "big")

    n = b64url_to_int(jwk["n"])
    e = b64url_to_int(jwk["e"])
    return RSAPublicNumbers(e, n).public_key(default_backend())


# ── JWT validation ────────────────────────────────────────────────────────────

async def validate_id_token(
    id_token: str,
    platform: LTIPlatform,
    stored_nonce: str,
) -> dict[str, Any]:
    """
    Validate the LTI 1.3 id_token JWT.

    Steps:
    1. Decode header (no verify) → get kid
    2. Fetch platform JWKS, find matching key
    3. Validate signature + standard claims
    4. Check nonce, deployment_id, message_type

    Returns the full claims dict on success.
    Raises ValueError on any validation failure.
    """
    # 1. Decode header
    try:
        header = jwt.get_unverified_header(id_token)
    except JWTError as exc:
        raise ValueError(f"Malformed JWT header: {exc}") from exc

    kid = header.get("kid")

    # 2. Fetch JWKS and find matching key
    try:
        keys = await fetch_platform_jwks(platform.key_set_url)
    except Exception as exc:
        raise ValueError(f"Failed to fetch platform JWKS: {exc}") from exc

    matching_key = None
    for k in keys:
        if kid is None or k.get("kid") == kid:
            matching_key = k
            break

    if matching_key is None:
        # kid mismatch — bust the JWKS cache and retry once
        redis = await get_redis()
        cache_key = f"lti:jwks:{hashlib.sha256(platform.key_set_url.encode()).hexdigest()}"
        await redis.delete(cache_key)
        keys = await fetch_platform_jwks(platform.key_set_url)
        for k in keys:
            if kid is None or k.get("kid") == kid:
                matching_key = k
                break

    if matching_key is None:
        raise ValueError(f"No matching JWK found for kid={kid!r}")

    # 3. Convert JWK → public key and decode JWT
    try:
        public_key = _jwk_to_public_key(matching_key)
        # Convert to PEM for python-jose
        pub_pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        claims = jwt.decode(
            id_token,
            pub_pem,
            algorithms=["RS256"],
            audience=platform.client_id,
            issuer=platform.issuer,
        )
    except JWTError as exc:
        raise ValueError(f"JWT validation failed: {exc}") from exc

    # 4. Application-level checks
    if claims.get("nonce") != stored_nonce:
        raise ValueError("Nonce mismatch — possible replay attack")

    deployment_id = claims.get(_CLAIM_DEPLOYMENT)
    if platform.deployment_ids and deployment_id not in platform.deployment_ids:
        raise ValueError(
            f"Deployment ID {deployment_id!r} not in platform's allowed list"
        )

    msg_type = claims.get(_CLAIM_MSG_TYPE)
    if msg_type and msg_type != "LtiResourceLinkRequest":
        raise ValueError(f"Unsupported LTI message type: {msg_type!r}")

    return claims


# ── Role mapping ──────────────────────────────────────────────────────────────

def map_lti_role(roles: list[str]) -> str:
    """Map LTI 1.3 role URIs to an axis-ai role string."""
    role_set = set(roles)
    if role_set & _ROLE_ADMIN:
        return "admin"
    if role_set & _ROLE_CREATOR:
        return "creator"
    return "learner"  # safe default


# ── JIT user provisioning ─────────────────────────────────────────────────────

async def jit_provision_user(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    claims: dict[str, Any],
    role: str,
    issuer: str,
) -> AxisUser:
    """
    Find or create an axis-ai user from LTI claims.

    Identity resolution order:
    1. Match lti_sub = "<issuer>::<sub>"  (most reliable — survives email changes)
    2. Match email within tenant           (handles re-provisioned accounts)
    3. Create new user                     (first-ever launch)
    """
    import bcrypt

    sub = claims.get("sub", "")
    email = (claims.get("email") or f"lti_{sub}@lti.local").lower().strip()
    full_name = claims.get("name") or claims.get("given_name", "")
    lti_sub_key = f"{issuer}::{sub}"

    # 1. By lti_sub
    result = await db.execute(
        select(AxisUser).where(
            AxisUser.lti_sub == lti_sub_key,
            AxisUser.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()

    if user:
        # Update name if changed
        if full_name and user.full_name != full_name:
            user.full_name = full_name
        # Update role if it changed (e.g. teacher was later unenrolled)
        if user.role != role:
            user.role = role
        await db.flush()
        return user

    # 2. By email within tenant
    result = await db.execute(
        select(AxisUser).where(
            AxisUser.email == email,
            AxisUser.tenant_id == tenant_id,
        )
    )
    user = result.scalar_one_or_none()
    if user:
        user.lti_sub = lti_sub_key
        user.full_name = full_name or user.full_name
        user.role = role
        await db.flush()
        return user

    # 3. Create new user
    # LTI users get a random unusable password (they authenticate via LTI only)
    random_pw = secrets.token_urlsafe(32)
    pw_hash = bcrypt.hashpw(random_pw.encode(), bcrypt.gensalt()).decode()

    user = AxisUser(
        tenant_id=tenant_id,
        email=email,
        password_hash=pw_hash,
        full_name=full_name,
        role=role,
        is_active=True,
        lti_sub=lti_sub_key,
    )
    db.add(user)
    await db.flush()
    log.info("lti.user.provisioned", user_id=str(user.id), email=email, role=role)
    return user


# ── One-Time Token (OTT) handoff ──────────────────────────────────────────────

async def create_ott(access_token: str, refresh_token: str) -> str:
    """
    Store access+refresh tokens under a one-time token (30s TTL).
    Used to hand off tokens across the backend→frontend domain boundary.
    """
    ott = secrets.token_urlsafe(32)
    redis = await get_redis()
    payload = json.dumps({
        "access_token": access_token,
        "refresh_token": refresh_token,
    })
    await redis.setex(f"lti:ott:{ott}", 30, payload)
    return ott


async def consume_ott(ott: str) -> dict | None:
    """Retrieve and DELETE the OTT payload (one-time use, 30s window)."""
    redis = await get_redis()
    key = f"lti:ott:{ott}"
    payload = await redis.get(key)
    if not payload:
        return None
    await redis.delete(key)
    return json.loads(payload)
