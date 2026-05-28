"""
LTI 1.3 API endpoints.

Public endpoints (no auth):
  GET  /.well-known/jwks.json        — axis-ai JWKS (our public key for Moodle)
  GET  /lti/login                    — OIDC login initiation
  POST /lti/login                    — OIDC login initiation (some LMS use POST)
  POST /lti/launch                   — JWT validation + user provisioning

Internal token exchange:
  POST /api/v1/auth/lti-exchange     — OTT → access+refresh tokens (Next.js calls this)

Admin platform CRUD (requires admin JWT):
  GET  /api/v1/admin/lti/platforms
  POST /api/v1/admin/lti/platforms
  GET  /api/v1/admin/lti/platforms/{id}
  PUT  /api/v1/admin/lti/platforms/{id}
  DELETE /api/v1/admin/lti/platforms/{id}
  POST /api/v1/admin/lti/generate-keypair
"""
from __future__ import annotations

import os
import urllib.parse
import uuid

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    refresh_token_expiry,
)
from app.api.v1.auth import get_current_user, require_role
# require_admin: FastAPI dependency that enforces admin role
require_admin = require_role("admin")
from app.models.lti import LTIPlatform
from app.models.space import LearningSpace
from app.schemas.lti import (
    LTIPlatformCreate,
    LTIPlatformListResponse,
    LTIPlatformResponse,
    LTIPlatformUpdate,
    LTIKeyPairResponse,
)
from app.services import lti as lti_svc
from app.services.lti import (
    build_jwks_safe,
    consume_oidc_state,
    consume_ott,
    create_oidc_state,
    create_ott,
    generate_rsa_keypair,
    get_platform,
    jit_provision_user,
    map_lti_role,
    validate_id_token,
)
from app.models.user import RefreshToken
from sqlalchemy import delete as sa_delete

log = structlog.get_logger(__name__)

# Frontend base URL — used for OTT redirect
_FRONTEND_URL = os.getenv("FRONTEND_URL", "https://axis.edzlms.com")
_BACKEND_URL  = os.getenv("BACKEND_URL",  "https://axisai.edzlms.com")

# ── Routers ───────────────────────────────────────────────────────────────────
# Public (mounted at app root — no /api/v1 prefix)
public_router = APIRouter(tags=["LTI 1.3 — Public"])

# Admin (mounted under /api/v1/admin/lti)
admin_router = APIRouter(
    prefix="/admin/lti",
    tags=["LTI 1.3 — Admin"],
)

# Internal auth exchange (mounted under /api/v1/auth)
auth_router = APIRouter(tags=["LTI 1.3 — Token Exchange"])


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@public_router.get("/.well-known/jwks.json", include_in_schema=False)
async def jwks():
    """axis-ai public JWKS — Moodle fetches this to verify our tokens."""
    return JSONResponse(build_jwks_safe())


async def _handle_oidc_login(
    iss: str | None,
    login_hint: str | None,
    target_link_uri: str | None,
    client_id: str | None,
    lti_message_hint: str | None,
    db: AsyncSession,
):
    """Shared logic for GET and POST /lti/login."""
    if not iss or not login_hint or not target_link_uri or not client_id:
        raise HTTPException(400, "Missing required LTI login params: iss, login_hint, target_link_uri, client_id")

    platform = await get_platform(db, iss, client_id)
    if not platform:
        log.warning("lti.login.unknown_platform", iss=iss, client_id=client_id)
        raise HTTPException(400, f"Unknown LTI platform: iss={iss!r} client_id={client_id!r}")

    state, nonce = await create_oidc_state(
        issuer=iss,
        client_id=client_id,
        target_link_uri=target_link_uri,
        login_hint=login_hint,
        lti_message_hint=lti_message_hint,
    )

    redirect_uri = f"{_BACKEND_URL}/lti/launch"
    params = {
        "scope": "openid",
        "response_type": "id_token",
        "client_id": platform.client_id,
        "redirect_uri": redirect_uri,
        "login_hint": login_hint,
        "state": state,
        "response_mode": "form_post",
        "nonce": nonce,
        "prompt": "none",
    }
    if lti_message_hint:
        params["lti_message_hint"] = lti_message_hint

    auth_url = platform.auth_login_url + "?" + urllib.parse.urlencode(params)
    return RedirectResponse(auth_url, status_code=302)


@public_router.get("/lti/login", include_in_schema=False)
async def lti_login_get(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    q = request.query_params
    return await _handle_oidc_login(
        iss=q.get("iss"),
        login_hint=q.get("login_hint"),
        target_link_uri=q.get("target_link_uri"),
        client_id=q.get("client_id"),
        lti_message_hint=q.get("lti_message_hint"),
        db=db,
    )


@public_router.post("/lti/login", include_in_schema=False)
async def lti_login_post(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    return await _handle_oidc_login(
        iss=form.get("iss"),
        login_hint=form.get("login_hint"),
        target_link_uri=form.get("target_link_uri"),
        client_id=form.get("client_id"),
        lti_message_hint=form.get("lti_message_hint"),
        db=db,
    )


@public_router.post("/lti/launch", include_in_schema=False)
async def lti_launch(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Moodle POSTs the signed id_token here.
    Validates JWT, provisions user, issues OTT, redirects to frontend.
    """
    form = await request.form()
    id_token = form.get("id_token")
    state     = form.get("state")

    if not id_token or not state:
        raise HTTPException(400, "Missing id_token or state")

    # 1. Retrieve + delete OIDC state (one-time)
    state_data = await consume_oidc_state(state)
    if not state_data:
        log.warning("lti.launch.invalid_state", state=state[:20])
        raise HTTPException(400, "Invalid or expired state — please retry the launch")

    issuer    = state_data["issuer"]
    client_id = state_data["client_id"]

    # 2. Look up platform
    platform = await get_platform(db, issuer, client_id)
    if not platform:
        raise HTTPException(400, "LTI platform not found or inactive")

    # 3. Validate JWT
    try:
        claims = await validate_id_token(id_token, platform, state_data["nonce"])
    except ValueError as exc:
        log.warning("lti.launch.jwt_invalid", error=str(exc), issuer=issuer)
        raise HTTPException(400, f"LTI token validation failed: {exc}") from exc

    # 4. Map role
    lti_roles = claims.get(_CLAIM_ROLES_KEY, [])
    axis_role = map_lti_role(lti_roles)

    # 5. JIT provision user
    try:
        user = await jit_provision_user(
            db=db,
            tenant_id=platform.tenant_id,
            claims=claims,
            role=axis_role,
            issuer=issuer,
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        log.error("lti.launch.provision_failed", error=str(exc))
        raise HTTPException(500, "User provisioning failed") from exc

    # 6. Issue axis-ai JWT tokens
    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
    )
    # Revoke all previous refresh tokens (single-session policy)
    await db.execute(sa_delete(RefreshToken).where(RefreshToken.user_id == user.id))
    raw_refresh, refresh_hash = generate_refresh_token()
    from datetime import datetime, timezone
    rt = RefreshToken(
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(rt)

    # 7. Resolve redirect target from space_slug custom param
    custom = claims.get(_CLAIM_CUSTOM_KEY, {})
    space_slug = custom.get("space_slug") if isinstance(custom, dict) else None
    redirect_to = "/learn"

    if space_slug:
        result = await db.execute(
            select(LearningSpace).where(
                LearningSpace.slug == space_slug,
                LearningSpace.tenant_id == platform.tenant_id,
            )
        )
        space = result.scalar_one_or_none()
        if space:
            redirect_to = f"/learn/{space.id}"
            log.info("lti.launch.slug_resolved", slug=space_slug, space_id=str(space.id))
        else:
            log.warning("lti.launch.slug_not_found", slug=space_slug)

    # 8. Create OTT for cookie handoff
    ott = await create_ott(access_token, raw_refresh)

    # 9. Redirect frontend to exchange OTT for cookies
    redirect_url = (
        f"{_FRONTEND_URL}/lti/complete"
        f"?ott={ott}"
        f"&to={urllib.parse.quote(redirect_to)}"
    )
    return RedirectResponse(redirect_url, status_code=302)


# Claim key constants (can't use the strings directly in the function before they're defined)
_CLAIM_ROLES_KEY  = "https://purl.imsglobal.org/spec/lti/claim/roles"
_CLAIM_CUSTOM_KEY = "https://purl.imsglobal.org/spec/lti/claim/custom"


# ═══════════════════════════════════════════════════════════════════════════════
# INTERNAL TOKEN EXCHANGE
# ═══════════════════════════════════════════════════════════════════════════════

@auth_router.post("/lti-exchange")
async def lti_token_exchange(request: Request):
    """
    Exchange a one-time token (OTT) for axis-ai access + refresh tokens.
    Called by the Next.js /api/auth/lti-exchange server route.
    OTT is valid for 30 seconds and single-use.
    """
    body = await request.json()
    ott = body.get("ott")
    if not ott:
        raise HTTPException(400, "Missing ott")

    data = await consume_ott(ott)
    if not data:
        raise HTTPException(401, "Invalid or expired one-time token")

    return {
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN PLATFORM CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def _platform_to_response(p: LTIPlatform) -> LTIPlatformResponse:
    r = LTIPlatformResponse.model_validate(p)
    r.axis_tool_url  = f"{_BACKEND_URL}/lti/launch"
    r.axis_login_url = f"{_BACKEND_URL}/lti/login"
    r.axis_jwks_url  = f"{_BACKEND_URL}/.well-known/jwks.json"
    return r


@admin_router.get("/platforms", response_model=LTIPlatformListResponse)
async def list_platforms(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    result = await db.execute(select(LTIPlatform).order_by(LTIPlatform.created_at.desc()))
    platforms = result.scalars().all()
    return LTIPlatformListResponse(
        platforms=[_platform_to_response(p) for p in platforms],
        total=len(platforms),
    )


@admin_router.post("/platforms", response_model=LTIPlatformResponse, status_code=201)
async def create_platform(
    payload: LTIPlatformCreate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    platform = LTIPlatform(**payload.model_dump())
    db.add(platform)
    try:
        await db.commit()
        await db.refresh(platform)
    except Exception as exc:
        await db.rollback()
        if "uq_lti_platforms_issuer_client_id" in str(exc):
            raise HTTPException(409, "A platform with this issuer + client_id already exists")
        raise
    return _platform_to_response(platform)


@admin_router.get("/platforms/{platform_id}", response_model=LTIPlatformResponse)
async def get_platform_detail(
    platform_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    result = await db.execute(
        select(LTIPlatform).where(LTIPlatform.id == platform_id)
    )
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(404, "Platform not found")
    return _platform_to_response(platform)


@admin_router.put("/platforms/{platform_id}", response_model=LTIPlatformResponse)
async def update_platform(
    platform_id: uuid.UUID,
    payload: LTIPlatformUpdate,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    result = await db.execute(
        select(LTIPlatform).where(LTIPlatform.id == platform_id)
    )
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(404, "Platform not found")

    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(platform, field, value)

    await db.commit()
    await db.refresh(platform)
    return _platform_to_response(platform)


@admin_router.delete("/platforms/{platform_id}", status_code=204)
async def delete_platform(
    platform_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_admin),
):
    result = await db.execute(
        select(LTIPlatform).where(LTIPlatform.id == platform_id)
    )
    platform = result.scalar_one_or_none()
    if not platform:
        raise HTTPException(404, "Platform not found")
    await db.delete(platform)
    await db.commit()


@admin_router.post("/generate-keypair", response_model=LTIKeyPairResponse)
async def generate_keypair(_user=Depends(require_admin)):
    """
    Generate a new RSA-2048 key pair.
    Paste the env_lines output into your .env file, then restart axis-ai.
    """
    return generate_rsa_keypair()
