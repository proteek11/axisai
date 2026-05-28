"""
Auth API — login, refresh, logout, me, user management.

POST /api/v1/auth/login          → email+password → access_token + refresh_token
POST /api/v1/auth/refresh        → {refresh_token} → new access_token
POST /api/v1/auth/logout         → invalidate refresh token
GET  /api/v1/auth/me             → current user from access_token
GET  /api/v1/auth/users          → list all users (admin only)
POST /api/v1/auth/users          → create user (admin only)
PUT  /api/v1/auth/users/{id}     → update user (admin only)
DELETE /api/v1/auth/users/{id}   → deactivate user (admin only)
GET  /api/v1/auth/learners       → list learner-role users (creator or admin)
"""
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Query, Security, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.jwt import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.models.user import AxisUser, RefreshToken
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    TokenResponse,
    UserCreateRequest,
    UserListResponse,
    UserResponse,
    UserUpdateRequest,
)

router = APIRouter(prefix="/auth", tags=["Auth"])
log = structlog.get_logger(__name__)

# ── Team enrichment helper ──────────────────────────────────────────────

async def _enrich_user_response(user: "AxisUser", db: AsyncSession) -> UserResponse:
    """Build a UserResponse, enriched with the user's primary team (if any).

    Resilient: if migration 021 hasn't run yet (team_members.team_id column missing),
    we skip team enrichment rather than crashing /me with a 500.
    """
    from app.models.team import Team, TeamMember
    resp = UserResponse.model_validate(user)
    try:
        dept_row = (
            await db.execute(
                select(Team, TeamMember)
                .join(TeamMember, TeamMember.team_id == Team.id)
                .where(TeamMember.user_id == user.id, Team.is_active == True)
                .limit(1)
            )
        ).first()
        if dept_row:
            resp.team_id = dept_row[0].id
            resp.team_name = dept_row[0].name
    except Exception:
        # Column doesn't exist yet (migration 021 pending) — return user without team info
        await db.rollback()
    return resp



_bearer = HTTPBearer(auto_error=True)


# ── Core dependency: get current user from Bearer JWT ─────────────────────────

async def get_current_user(
    credentials: str,
    db: AsyncSession,
) -> AxisUser:
    """Validate JWT and return the active AxisUser. Raises 401 on any failure."""
    from jose import JWTError

    try:
        payload = decode_access_token(credentials)
        user_id = uuid.UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
        )

    result = await db.execute(
        select(AxisUser).where(AxisUser.id == user_id, AxisUser.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


def require_role(*roles: str) -> Callable:
    """
    FastAPI dependency factory that enforces one of the given roles.

    Usage:
        @router.get("/admin-only")
        async def endpoint(
            credentials: HTTPAuthorizationCredentials = Security(_bearer),
            db: AsyncSession = Depends(get_db),
            _: AxisUser = Depends(require_role("admin")),
        ):
            ...

    Because require_role needs the bearer token + db that are injected by FastAPI,
    the returned dependency closes over credentials+db via inner Depends.
    The calling route must accept (credentials, db) separately and pass them through,
    OR use the shorthand get_current_user_with_role helper below.
    """
    async def _dependency(
        credentials: HTTPAuthorizationCredentials = Security(_bearer),
        db: AsyncSession = Depends(get_db),
    ) -> AxisUser:
        user = await get_current_user(credentials.credentials, db)
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted to: {', '.join(roles)}",
            )
        return user

    return _dependency


async def get_current_user_dep(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> AxisUser:
    """
    FastAPI dependency that extracts + validates the Bearer JWT and returns the active user.
    Use with Depends(): `current_user: AxisUser = Depends(get_current_user_dep)`
    """
    return await get_current_user(credentials.credentials, db)


# ── Login ─────────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate with email + password.
    Returns access token in body and refresh token in response body.
    The Next.js layer stores the refresh token in an HttpOnly cookie.
    """
    result = await db.execute(
        select(AxisUser).where(AxisUser.email == req.email, AxisUser.is_active == True)
    )
    user = result.scalar_one_or_none()

    # Constant-time path to prevent timing-based user enumeration
    dummy_hash = "$2b$12$invalidhash000000000000000000000000000000000000000000"
    if user is None:
        verify_password(req.password, dummy_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
    )
    # ── Single-session enforcement ────────────────────────────────────────
    # Revoke ALL existing refresh tokens for this user before issuing a new one.
    # This ensures only one browser / device session is active at a time.
    # When user logs in on Browser B, Browser A's refresh token is invalidated;
    # the next request from A will get 401 and redirect to the login page.
    await db.execute(sa_delete(RefreshToken).where(RefreshToken.user_id == user.id))

    raw_refresh, refresh_hash = generate_refresh_token()

    rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(rt)

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)

    log.info("user_login", user_id=str(user.id), email=user.email, role=user.role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user=UserResponse.model_validate(user),
    )


# ── Refresh ───────────────────────────────────────────────────────────────────

@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_token(
    req: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> AccessTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    token_hash = hash_refresh_token(req.refresh_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if rt is None or rt.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    result = await db.execute(
        select(AxisUser).where(AxisUser.id == rt.user_id, AxisUser.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    access_token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        tenant_id=user.tenant_id,
    )

    # ── Refresh token rotation ─────────────────────────────────────────────
    # Replace the consumed refresh token with a new one.
    # Prevents token replay and detects token theft (a reused revoked token
    # means someone else has it — both sessions should be killed).
    await db.delete(rt)
    raw_new_refresh, new_refresh_hash = generate_refresh_token()
    new_rt = RefreshToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=new_refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(new_rt)
    await db.commit()

    log.info("token_refreshed", user_id=str(user.id))
    return AccessTokenResponse(access_token=access_token, refresh_token=raw_new_refresh)


# ── Logout ────────────────────────────────────────────────────────────────────

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    req: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Invalidate a refresh token."""
    token_hash = hash_refresh_token(req.refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    rt = result.scalar_one_or_none()
    if rt:
        await db.delete(rt)
        await db.commit()


# ── Me ────────────────────────────────────────────────────────────────────────

@router.get("/me", response_model=UserResponse)
async def get_me(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Current user from JWT Bearer token."""
    user = await get_current_user(credentials.credentials, db)
    return await _enrich_user_response(user, db)


# ── User management (admin only) ───────────────────────────────────────────────

@router.get("/users", response_model=UserListResponse)
async def list_users(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """List all users in this tenant. Admin only."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    result = await db.execute(
        select(AxisUser)
        .where(AxisUser.tenant_id == current.tenant_id)
        .order_by(AxisUser.created_at)
    )
    users = result.scalars().all()
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    req: UserCreateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Create a new user in this tenant. Admin only."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    # Check for duplicate email
    existing = await db.execute(
        select(AxisUser).where(AxisUser.email == req.email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    new_user = AxisUser(
        id=uuid.uuid4(),
        tenant_id=current.tenant_id,
        email=req.email,
        password_hash=hash_password(req.password),
        full_name=req.full_name,
        role=req.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    log.info("user_created", user_id=str(new_user.id), email=new_user.email, by=str(current.id))

    # Phase 13 — send welcome email (fire-and-forget, never blocks the response)
    try:
        from app.services.email import send_trigger_email
        from app.config import settings as _cfg
        asyncio.ensure_future(send_trigger_email(
            db=db,
            trigger="welcome",
            to_email=new_user.email,
            to_name=new_user.full_name or "",
            variables={
                "full_name": new_user.full_name or new_user.email,
                "email": new_user.email,
                "password": req.password,
                "login_url": getattr(_cfg, "frontend_url", "https://axis.edzlms.com") + "/login",
            },
        ))
    except Exception:
        pass  # never fail user creation on email error

    return UserResponse.model_validate(new_user)


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    req: UserUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update a user. Admin only."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id,
            AxisUser.tenant_id == current.tenant_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if req.email is not None:
        # Check for duplicate email across any tenant
        dup = await db.execute(
            select(AxisUser).where(AxisUser.email == req.email, AxisUser.id != user_id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )
        target.email = req.email
    if req.full_name is not None:
        target.full_name = req.full_name
    if req.role is not None:
        target.role = req.role
    if req.is_active is not None:
        target.is_active = req.is_active
    if req.password is not None:
        target.password_hash = hash_password(req.password)

    await db.commit()
    await db.refresh(target)

    log.info("user_updated", user_id=str(user_id), by=str(current.id))
    return UserResponse.model_validate(target)


# ── Self-service profile update ────────────────────────────────────────────────

@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    req: ProfileUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the current user's own name, email, or password."""
    current = await get_current_user(credentials.credentials, db)

    if req.email is not None and req.email != current.email:
        dup = await db.execute(
            select(AxisUser).where(AxisUser.email == req.email, AxisUser.id != current.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )
        current.email = req.email
    if req.full_name is not None:
        current.full_name = req.full_name
    if req.password is not None:
        current.password_hash = hash_password(req.password)

    await db.commit()
    await db.refresh(current)

    log.info("profile_updated", user_id=str(current.id))
    return await _enrich_user_response(current, db)


_AVATAR_DIR = os.getenv("AVATAR_DIR", os.path.join(os.path.expanduser("~"), ".axis-avatars"))
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_MAX_AVATAR_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/me/avatar", response_model=UserResponse)
async def upload_my_avatar(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Upload or replace the current user's profile picture (max 5 MB, JPEG/PNG/WebP/GIF)."""
    current = await get_current_user(credentials.credentials, db)

    # Validate content type
    if file.content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type '{file.content_type}'. Use JPEG, PNG, WebP, or GIF.",
        )

    # Read & size-check
    data = await file.read()
    if len(data) > _MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Avatar must be smaller than 5 MB.",
        )

    # Derive extension from content type
    ext_map = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }
    ext = ext_map[file.content_type]  # type: ignore[index]

    # Save to disk — one file per user, overwrites previous
    os.makedirs(_AVATAR_DIR, exist_ok=True)
    dest = os.path.join(_AVATAR_DIR, f"{current.id}.{ext}")

    # Remove any old avatar files for this user (different extension)
    for old_ext in ext_map.values():
        old_path = os.path.join(_AVATAR_DIR, f"{current.id}.{old_ext}")
        if old_path != dest and os.path.exists(old_path):
            os.remove(old_path)

    with open(dest, "wb") as f:
        f.write(data)

    # Store relative path so the frontend can build the full URL
    current.avatar_url = f"/api/v1/auth/avatars/{current.id}.{ext}"
    await db.commit()
    await db.refresh(current)

    log.info("avatar_uploaded", user_id=str(current.id), size=len(data))
    return await _enrich_user_response(current, db)


@router.get("/avatars/{filename}", include_in_schema=False)
async def serve_avatar(filename: str) -> FileResponse:
    """Serve a user avatar image directly (no auth required — URLs are opaque)."""
    # Sanitise: only allow {uuid}.{ext} filenames — no path traversal
    if "/" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    path = os.path.join(_AVATAR_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Avatar not found")
    return FileResponse(path)


@router.get("/me/activity")
async def get_my_activity(
    days: int = Query(default=15, ge=1, le=90),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Return recent activity for the current user.
    - Learners: chat sessions grouped by day.
    - Creators/Admins: content uploads + AI processing jobs grouped by day.
    Covers the last `days` days (default 15, max 90).
    """
    from app.models.chat import ChatSession, ChatMessage, ChatMessageRole
    from app.models.content import ContentItem
    from collections import defaultdict

    current = await get_current_user(credentials.credentials, db)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    events: list[dict] = []

    if current.role in ("creator", "admin"):
        # ── Creator/Admin: content upload events ─────────────────────────────
        # Content items belong to spaces the creator owns
        from app.models.space import LearningSpace, SpaceItem
        from app.models.space import SpaceItem
        # Join via SpaceItem so we capture IC library items (space_id=None)
        # that have been attached to a creator's space via SpaceItem records.
        content_rows = (
            await db.execute(
                select(ContentItem, LearningSpace)
                .join(SpaceItem, SpaceItem.content_item_id == ContentItem.id)
                .join(LearningSpace, SpaceItem.space_id == LearningSpace.id)
                .where(
                    LearningSpace.creator_id == current.id,
                    ContentItem.created_at >= since,
                )
                .distinct(ContentItem.id)
                .order_by(ContentItem.id, ContentItem.created_at.desc())
                .limit(200)
            )
        ).all()

        seen_ci_ids: set[str] = set()
        for ci, space in content_rows:
            ci_id = str(ci.id)
            if ci_id in seen_ci_ids:
                continue
            seen_ci_ids.add(ci_id)
            ts = ci.updated_at or ci.created_at
            events.append({
                "type": "upload",
                "content_item_id": ci_id,
                "content_title": ci.title or (ci.source_url or "Untitled")[:60],
                "content_type": ci.content_type,
                "content_status": ci.status,
                "space_id": str(space.id),
                "space_title": space.title,
                "ts": ts.isoformat(),
                "date": ts.date().isoformat(),
            })

    else:
        # ── Learner: chat sessions ────────────────────────────────────────────
        rows = (
            await db.execute(
                select(ChatSession, ContentItem)
                .outerjoin(ContentItem, ChatSession.content_item_id == ContentItem.id)
                .where(
                    ChatSession.axis_user_id == current.id,
                    ChatSession.created_at >= since,
                )
                .order_by(ChatSession.created_at.desc())
                .limit(200)
            )
        ).all()

        session_ids = [r[0].id for r in rows]
        msg_counts: dict[uuid.UUID, int] = {}
        if session_ids:
            mc_rows = (
                await db.execute(
                    select(ChatMessage.session_id, func.count(ChatMessage.id).label("cnt"))
                    .where(
                        ChatMessage.session_id.in_(session_ids),
                        ChatMessage.role == ChatMessageRole.USER,
                    )
                    .group_by(ChatMessage.session_id)
                )
            ).all()
            msg_counts = {r.session_id: r.cnt for r in mc_rows}

        for session, ci in rows:
            content_title = None
            if ci:
                content_title = ci.title or (ci.source_url or "Untitled")[:60]
            events.append({
                "type": "chat",
                "session_id": str(session.id),
                "content_item_id": str(session.content_item_id) if session.content_item_id else None,
                "content_title": content_title,
                "session_title": session.title,
                "message_count": msg_counts.get(session.id, 0),
                "total_tokens": session.total_tokens_used or 0,
                "ts": session.updated_at.isoformat() if session.updated_at else session.created_at.isoformat(),
                "date": (session.updated_at or session.created_at).date().isoformat(),
            })

    # ── Group by date ─────────────────────────────────────────────────────────
    by_day: dict[str, list] = defaultdict(list)
    for ev in events:
        by_day[ev["date"]].append(ev)

    timeline = [
        {"date": date, "events": day_events}
        for date, day_events in sorted(by_day.items(), reverse=True)
    ]

    return {
        "days": days,
        "role": current.role,
        "total_events": len(events),
        "timeline": timeline,
    }


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Deactivate (soft-delete) a user. Admin only. Cannot deactivate yourself."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if user_id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id,
            AxisUser.tenant_id == current.tenant_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    target.is_active = False
    await db.commit()
    log.info("user_deactivated", user_id=str(user_id), by=str(current.id))




@router.delete("/users/{user_id}/purge", status_code=status.HTTP_200_OK)
async def purge_user(
    user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Permanently delete a user and ALL their data (hard delete with full cascade).
    Admin only. Cannot purge yourself.

    Cascade deletes (via DB ondelete=CASCADE):
    - Learning spaces created by this user (+ all their items, access grants, content)
    - Space access grants where this user was granted access
    - Chat sessions and messages
    - Quiz attempts and flashcard reviews
    - Team memberships
    - Token budget overrides
    - Refresh tokens
    - Audit log entries with user_id set
    """
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if user_id == current.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id,
            AxisUser.tenant_id == current.tenant_id,
        )
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    email_snapshot = target.email
    name_snapshot = target.full_name

    # Hard delete — all CASCADE FK relationships in DB handle the rest
    await db.delete(target)
    await db.commit()

    log.info(
        "user_purged",
        purged_user_id=str(user_id),
        purged_email=email_snapshot,
        by=str(current.id),
    )
    return {"deleted": True, "email": email_snapshot, "full_name": name_snapshot}

# ── Learner list (creator + admin) ─────────────────────────────────────────────

@router.get("/learners", response_model=UserListResponse)
async def list_learners(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> UserListResponse:
    """
    List all active learner-role users in this tenant.
    Accessible to creators and admins (used by share modal to find grantable users).
    """
    current = await get_current_user(credentials.credentials, db)
    if current.role not in ("admin", "creator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Creator or admin access required",
        )

    result = await db.execute(
        select(AxisUser)
        .where(
            AxisUser.tenant_id == current.tenant_id,
            AxisUser.role == "learner",
            AxisUser.is_active == True,
        )
        .order_by(AxisUser.full_name)
    )
    users = result.scalars().all()
    return UserListResponse(
        users=[UserResponse.model_validate(u) for u in users],
        total=len(users),
    )


# ── Bulk CSV Import ────────────────────────────────────────────────────────────

import csv as _csv
import io as _io
from pydantic import BaseModel, BaseModel as _PydBase, EmailStr, field_validator


class BulkImportResult(_PydBase):
    created: int
    skipped: int
    errors: list[str]
    created_users: list[str]


@router.post("/users/bulk-import", response_model=BulkImportResult, status_code=status.HTTP_200_OK)
async def bulk_import_users(
    file: UploadFile = File(...),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> BulkImportResult:
    """
    POST /api/v1/auth/users/bulk-import
    Upload a CSV file (columns: email, full_name, role, password).
    Admin-only. Creates users in bulk within the caller's tenant.
    Rows with duplicate emails or validation errors are skipped and reported.
    """
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be a .csv")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = _csv.DictReader(_io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV file is empty or has no data rows")

    # Normalise header names to lowercase + stripped
    rows = [{k.strip().lower(): (v or "").strip() for k, v in row.items()} for row in rows]

    created = 0
    skipped = 0
    errors: list[str] = []
    created_users: list[str] = []
    VALID_ROLES = {"admin", "creator", "learner"}

    for i, row in enumerate(rows, start=2):  # row 1 is the header
        email = row.get("email", "").strip().lower()
        full_name = (
            row.get("full_name")
            or row.get("name")
            or row.get("fullname")
            or ""
        ).strip() or None
        role = row.get("role", "learner").strip().lower()
        password = row.get("password", "Axis@1234").strip() or "Axis@1234"

        if not email:
            errors.append(f"Row {i}: missing email — skipped")
            skipped += 1
            continue

        if role not in VALID_ROLES:
            errors.append(f"Row {i} ({email}): unknown role '{role}' — defaulting to learner")
            role = "learner"

        if len(password) < 6:
            errors.append(f"Row {i} ({email}): password too short — using default")
            password = "Axis@1234"

        existing = await db.execute(select(AxisUser).where(AxisUser.email == email))
        if existing.scalar_one_or_none():
            errors.append(f"Row {i} ({email}): email already exists — skipped")
            skipped += 1
            continue

        new_user = AxisUser(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            role=role,
            tenant_id=current.tenant_id,
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(new_user)
        created += 1
        created_users.append(email)

    if created > 0:
        await db.commit()

    log.info("bulk_import_users", created=created, skipped=skipped, errors=len(errors), by=str(current.id))
    return BulkImportResult(
        created=created,
        skipped=skipped,
        errors=errors,
        created_users=created_users,
    )


# ── Tenant Branding endpoints ──────────────────────────────────────────────────

from app.models.tenant import Tenant as _Tenant

class BrandingTokens(_PydBase):
    """CSS custom-property values stored per-tenant."""
    primary: str | None = None
    primary_foreground: str | None = None
    background: str | None = None
    foreground: str | None = None
    card: str | None = None
    muted: str | None = None
    muted_foreground: str | None = None
    border: str | None = None
    sidebar_background: str | None = None
    sidebar_primary: str | None = None
    radius: str | None = None
    site_name: str | None = None
    logo_url: str | None = None


@router.get("/settings/branding/public", response_model=BrandingTokens)
async def get_branding_public(
    db: AsyncSession = Depends(get_db),
):
    """
    Public (no-auth) endpoint that returns branding for the active tenant.
    Used on the login page and any unauthenticated surface so custom colours
    are applied before the user signs in.
    For single-tenant deployments this returns the first active tenant's config.
    """
    result = await db.execute(
        select(_Tenant).where(_Tenant.is_active == True).limit(1)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        return BrandingTokens()
    branding = (tenant.config or {}).get("branding", {})
    return BrandingTokens(**branding)


@router.get("/settings/branding", response_model=BrandingTokens)
async def get_branding(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Return current tenant branding config (admin or creator read access)."""
    current = await get_current_user(credentials.credentials, db)

    result = await db.execute(select(_Tenant).where(_Tenant.id == current.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    branding = (tenant.config or {}).get("branding", {})
    return BrandingTokens(**branding)


@router.put("/settings/branding", response_model=BrandingTokens)
async def update_branding(
    payload: BrandingTokens,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Save tenant branding config (admin only)."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(_Tenant).where(_Tenant.id == current.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Merge branding into config (keep other config keys)
    config = dict(tenant.config or {})
    config["branding"] = payload.model_dump(exclude_none=False)

    # SQLAlchemy JSONB requires explicit assignment to trigger dirty detection
    from sqlalchemy.orm.attributes import flag_modified
    tenant.config = config
    flag_modified(tenant, "config")

    await db.commit()
    await db.refresh(tenant)

    log.info("branding_updated", tenant=str(tenant.id), by=str(current.id))
    branding = (tenant.config or {}).get("branding", {})
    return BrandingTokens(**branding)


# ══════════════════════════════════════════════════════════════════════════════
# Forgot Password / OTP / Reset Password
# ══════════════════════════════════════════════════════════════════════════════

import hashlib
import random
import string

from app.services.email import send_otp_email
from app.core.redis import get_redis

_OTP_PREFIX = "axis:otp:"
_OTP_RESET_PREFIX = "axis:reset:"
_OTP_TTL = 600  # 10 minutes


def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class VerifyOtpRequest(BaseModel):
    email: EmailStr
    otp: str


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def pw_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class OtpResponse(BaseModel):
    detail: str


class ResetTokenResponse(BaseModel):
    reset_token: str
    detail: str


@router.post("/forgot-password", response_model=OtpResponse)
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a 6-digit OTP and email it. Always returns 200 to prevent email enumeration.
    OTP is stored in Redis with a 10-minute TTL.
    """
    result = await db.execute(
        select(AxisUser).where(AxisUser.email == req.email, AxisUser.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()

    if user:
        otp = _gen_otp()
        redis = await get_redis()
        await redis.setex(f"{_OTP_PREFIX}{req.email}", _OTP_TTL, _hash_otp(otp))

        # Fetch tenant branding for a styled email
        t_result = await db.execute(select(_Tenant).where(_Tenant.id == user.tenant_id))
        tenant = t_result.scalar_one_or_none()
        branding = (tenant.config or {}).get("branding", {}) if tenant else {}
        site_name = branding.get("site_name") or "Axis AI"
        primary = branding.get("primary") or "#1447e6"

        await send_otp_email(req.email, otp, site_name=site_name, primary_color=primary)
        log.info("otp_sent", email=req.email)

    return OtpResponse(detail="If that email is registered, a reset code has been sent.")


@router.post("/verify-otp", response_model=ResetTokenResponse)
async def verify_otp(req: VerifyOtpRequest):
    """
    Verify the OTP. On success, return a short-lived reset token (15 min).
    The reset token is stored in Redis and consumed once on password reset.
    """
    redis = await get_redis()
    stored_hash = await redis.get(f"{_OTP_PREFIX}{req.email}")
    if not stored_hash or stored_hash != _hash_otp(req.otp):
        raise HTTPException(status_code=400, detail="Invalid or expired code")

    # Burn the OTP immediately
    await redis.delete(f"{_OTP_PREFIX}{req.email}")

    # Issue a one-time reset token (UUID stored in Redis for 15 min)
    import uuid as _uuid
    reset_token = str(_uuid.uuid4())
    await redis.setex(f"{_OTP_RESET_PREFIX}{reset_token}", 900, req.email)

    return ResetTokenResponse(reset_token=reset_token, detail="Code verified. Set your new password.")


@router.post("/reset-password", response_model=OtpResponse)
async def reset_password(req: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Consume the reset token and update the user's password."""
    redis = await get_redis()
    email_bytes = await redis.get(f"{_OTP_RESET_PREFIX}{req.reset_token}")
    if not email_bytes:
        raise HTTPException(status_code=400, detail="Reset link expired or already used")

    email = email_bytes if isinstance(email_bytes, str) else email_bytes.decode()
    await redis.delete(f"{_OTP_RESET_PREFIX}{req.reset_token}")

    result = await db.execute(
        select(AxisUser).where(AxisUser.email == email, AxisUser.is_active == True)  # noqa: E712
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.password_hash = hash_password(req.new_password)
    # Revoke all refresh tokens for security
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(RefreshToken).where(RefreshToken.user_id == user.id))
    await db.commit()

    log.info("password_reset", email=email)
    return OtpResponse(detail="Password updated successfully. Please sign in.")


# ══════════════════════════════════════════════════════════════════════════════
# Google OAuth
# ══════════════════════════════════════════════════════════════════════════════

import httpx as _httpx

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(req: GoogleCallbackRequest, db: AsyncSession = Depends(get_db)):
    """
    Exchange a Google OAuth authorization code for an access + refresh token.
    Creates a new user account if none exists for this Google email.
    Requires GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.
    """
    from app.config import settings as _cfg

    if not _cfg.google_client_id or not _cfg.google_client_secret:
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server")

    # Exchange code for Google tokens
    async with _httpx.AsyncClient() as client:
        token_resp = await client.post(_GOOGLE_TOKEN_URL, data={
            "code": req.code,
            "client_id": _cfg.google_client_id,
            "client_secret": _cfg.google_client_secret,
            "redirect_uri": req.redirect_uri,
            "grant_type": "authorization_code",
        })
        if token_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to exchange Google code")
        google_tokens = token_resp.json()

        # Fetch Google user info
        userinfo_resp = await client.get(
            _GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_tokens['access_token']}"},
        )
        if userinfo_resp.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to fetch Google profile")
        g_user = userinfo_resp.json()

    google_email: str = g_user.get("email", "")
    if not google_email:
        raise HTTPException(status_code=400, detail="Google account has no email address")

    # Find or create the user
    result = await db.execute(select(AxisUser).where(AxisUser.email == google_email))
    user = result.scalar_one_or_none()

    if not user:
        # Auto-provision: find the first active tenant, create learner account
        t_result = await db.execute(
            select(_Tenant).where(_Tenant.is_active == True).limit(1)  # noqa: E712
        )
        tenant = t_result.scalar_one_or_none()
        if not tenant:
            raise HTTPException(status_code=503, detail="No active tenant found")

        import uuid as _uuid
        import secrets as _sec
        user = AxisUser(
            id=_uuid.uuid4(),
            tenant_id=tenant.id,
            email=google_email,
            full_name=g_user.get("name"),
            password_hash=hash_password(_sec.token_hex(32)),  # random unusable password
            role="learner",
            is_active=True,
            avatar_url=g_user.get("picture"),
        )
        db.add(user)

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    # Update avatar from Google if not set
    if g_user.get("picture") and not user.avatar_url:
        user.avatar_url = g_user["picture"]

    # Single-session: revoke old refresh tokens
    from sqlalchemy import delete as sa_delete
    await db.execute(sa_delete(RefreshToken).where(RefreshToken.user_id == user.id))

    # Issue axis tokens
    import uuid as _uuid2
    access_token = create_access_token(email=user.email, user_id=str(user.id), role=user.role)
    raw_refresh, refresh_hash = generate_refresh_token()
    rt = RefreshToken(
        id=_uuid2.uuid4(),
        user_id=user.id,
        token_hash=refresh_hash,
        expires_at=refresh_token_expiry(),
    )
    db.add(rt)
    user.last_login_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    await db.commit()

    user_resp = await _enrich_user_response(user, db)
    log.info("google_login", user_id=str(user.id), email=user.email)
    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        user=user_resp,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Auth settings — admin toggle + public read
# ══════════════════════════════════════════════════════════════════════════════

class AuthSettingsPublic(BaseModel):
    google_auth_enabled: bool = False


class AuthSettingsUpdate(BaseModel):
    google_auth_enabled: bool


@router.get("/settings/auth/public", response_model=AuthSettingsPublic)
async def get_auth_settings_public(db: AsyncSession = Depends(get_db)):
    """Public: returns which auth methods are enabled (no credentials required)."""
    result = await db.execute(
        select(_Tenant).where(_Tenant.is_active == True).limit(1)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        return AuthSettingsPublic()
    cfg = (tenant.config or {}).get("auth_settings", {})
    return AuthSettingsPublic(google_auth_enabled=cfg.get("google_auth_enabled", False))


@router.get("/settings/auth", response_model=AuthSettingsPublic)
async def get_auth_settings(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    current = await get_current_user(credentials.credentials, db)
    result = await db.execute(select(_Tenant).where(_Tenant.id == current.tenant_id))
    tenant = result.scalar_one_or_none()
    cfg = (tenant.config or {}).get("auth_settings", {}) if tenant else {}
    return AuthSettingsPublic(google_auth_enabled=cfg.get("google_auth_enabled", False))


@router.put("/settings/auth", response_model=AuthSettingsPublic)
async def update_auth_settings(
    payload: AuthSettingsUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Admin only: toggle Google login on/off."""
    current = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(select(_Tenant).where(_Tenant.id == current.tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from sqlalchemy.orm.attributes import flag_modified
    config = dict(tenant.config or {})
    config["auth_settings"] = {"google_auth_enabled": payload.google_auth_enabled}
    tenant.config = config
    flag_modified(tenant, "config")
    await db.commit()

    log.info("auth_settings_updated", tenant=str(tenant.id), by=str(current.id))
    return AuthSettingsPublic(google_auth_enabled=payload.google_auth_enabled)


# ── Learner Consolidated Report ────────────────────────────────────────────────

@router.get("/my/report")
async def get_my_report(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Learner's consolidated learning report across all their enrolled spaces.
    Returns KPI totals + per-space breakdown + recent activity.
    """
    import sqlalchemy as sa
    from app.models.space import LearningSpace, SpaceAccess, SpaceItem
    from app.models.chat import ChatSession
    from app.models.certificate import SpaceCertificate
    from app.models.attempt import QuizAttempt, FlashcardReview
    from app.models.content import ContentItem

    user = await get_current_user(credentials.credentials, db)

    # ── 1. All spaces this learner has access to ───────────────────────────
    access_rows = (
        await db.execute(
            select(SpaceAccess.space_id).where(SpaceAccess.user_id == user.id)
        )
    ).scalars().all()
    space_ids = list(access_rows)

    if not space_ids:
        return {
            "total_spaces": 0,
            "completed_spaces": 0,
            "certificates_earned": 0,
            "total_chat_messages": 0,
            "total_quiz_attempts": 0,
            "quiz_accuracy_pct": 0,
            "total_flashcard_reviews": 0,
            "spaces": [],
            "recent_activity": [],
        }

    # ── 2. Fetch all spaces metadata ──────────────────────────────────────
    spaces_res = (
        await db.execute(
            select(LearningSpace.id, LearningSpace.title, LearningSpace.updated_at)
            .where(LearningSpace.id.in_(space_ids))
            .order_by(LearningSpace.title)
        )
    ).all()

    # ── 3. Item counts per space ──────────────────────────────────────────
    item_counts_res = (
        await db.execute(
            select(SpaceItem.space_id, func.count(SpaceItem.id).label("cnt"))
            .where(SpaceItem.space_id.in_(space_ids), SpaceItem.is_visible == True)
            .group_by(SpaceItem.space_id)
        )
    ).all()
    item_counts = {str(r.space_id): r.cnt for r in item_counts_res}

    # ── 4. Content item IDs across all accessible spaces ─────────────────
    ci_rows = (
        await db.execute(
            select(SpaceItem.space_id, SpaceItem.content_item_id)
            .where(SpaceItem.space_id.in_(space_ids), SpaceItem.is_visible == True)
        )
    ).all()
    # Map: space_id → [content_item_id]
    from collections import defaultdict
    space_to_cis: dict = defaultdict(list)
    all_ci_ids = []
    for row in ci_rows:
        if row.content_item_id:
            space_to_cis[str(row.space_id)].append(row.content_item_id)
            all_ci_ids.append(row.content_item_id)

    # ── 5. Studied items per space (via ChatSession engagement) ──────────
    studied_res = (
        await db.execute(
            select(
                ChatSession.space_id,
                func.count(func.distinct(ChatSession.content_item_id)).label("studied"),
                func.count(ChatSession.id).label("sessions"),
                func.sum(ChatSession.message_count).label("messages"),
            )
            .where(
                ChatSession.axis_user_id == user.id,
                ChatSession.space_id.in_(space_ids),
            )
            .group_by(ChatSession.space_id)
        )
    ).all()
    studied_map = {
        str(r.space_id): {
            "studied": r.studied or 0,
            "sessions": r.sessions or 0,
            "messages": r.messages or 0,
        }
        for r in studied_res
    }

    # ── 6. Certificates earned ────────────────────────────────────────────
    cert_res = (
        await db.execute(
            select(SpaceCertificate.space_id, SpaceCertificate.issued_at)
            .where(
                SpaceCertificate.user_id == user.id,
                SpaceCertificate.space_id.in_(space_ids),
            )
        )
    ).all()
    cert_map = {str(r.space_id): r.issued_at.isoformat() for r in cert_res}

    # ── 7. Quiz stats across all content ─────────────────────────────────
    quiz_total = quiz_correct = 0
    if all_ci_ids:
        quiz_res = (
            await db.execute(
                select(
                    func.count(QuizAttempt.id).label("total"),
                    func.sum(sa.cast(QuizAttempt.is_correct, sa.Integer)).label("correct"),
                )
                .where(
                    QuizAttempt.user_id == user.id,
                    QuizAttempt.content_item_id.in_(all_ci_ids),
                )
            )
        ).one()
        quiz_total = quiz_res.total or 0
        quiz_correct = int(quiz_res.correct or 0)

    # ── 8. Flashcard stats ────────────────────────────────────────────────
    fc_total = fc_known = 0
    if all_ci_ids:
        fc_res = (
            await db.execute(
                select(
                    func.count(FlashcardReview.id).label("total"),
                    func.sum(sa.cast(FlashcardReview.known, sa.Integer)).label("known"),
                )
                .where(
                    FlashcardReview.user_id == user.id,
                    FlashcardReview.content_item_id.in_(all_ci_ids),
                )
            )
        ).one()
        fc_total = fc_res.total or 0
        fc_known = int(fc_res.known or 0)

    # ── 9. Recent chat activity (last 10 sessions) ────────────────────────
    recent_res = (
        await db.execute(
            select(
                ChatSession.id,
                ChatSession.space_id,
                ChatSession.content_item_id,
                ChatSession.message_count,
                ChatSession.updated_at,
            )
            .where(
                ChatSession.axis_user_id == user.id,
                ChatSession.space_id.in_(space_ids),
                ChatSession.message_count > 0,
            )
            .order_by(ChatSession.updated_at.desc())
            .limit(10)
        )
    ).all()

    # Build space title lookup
    space_title_map = {str(r.id): r.title for r in spaces_res}

    # Resolve content titles for recent activity
    recent_ci_ids = [r.content_item_id for r in recent_res if r.content_item_id]
    ci_title_map: dict = {}
    if recent_ci_ids:
        ci_title_res = (
            await db.execute(
                select(ContentItem.id, ContentItem.title)
                .where(ContentItem.id.in_(recent_ci_ids))
            )
        ).all()
        ci_title_map = {str(r.id): r.title for r in ci_title_res}

    # ── 10. Assemble per-space breakdown ──────────────────────────────────
    space_rows_out = []
    total_messages = 0
    completed_spaces = 0

    for row in spaces_res:
        sid = str(row.id)
        total_ci = item_counts.get(sid, 0)
        s_data = studied_map.get(sid, {"studied": 0, "sessions": 0, "messages": 0})
        studied = s_data["studied"]
        msgs = s_data["messages"]
        total_messages += msgs
        pct = round((studied / total_ci * 100)) if total_ci > 0 else 0
        has_cert = sid in cert_map
        if has_cert or (total_ci > 0 and studied >= total_ci):
            completed_spaces += 1

        space_rows_out.append({
            "space_id": sid,
            "title": row.title,
            "total_items": total_ci,
            "studied_items": studied,
            "completion_pct": pct,
            "chat_messages": msgs,
            "certificate_earned": has_cert,
            "certificate_issued_at": cert_map.get(sid),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        })

    # Sort: completed last, then by pct desc
    space_rows_out.sort(key=lambda s: (s["certificate_earned"], s["completion_pct"]), reverse=True)

    quiz_accuracy = round(quiz_correct / quiz_total * 100) if quiz_total > 0 else 0

    return {
        "total_spaces": len(space_rows_out),
        "completed_spaces": completed_spaces,
        "certificates_earned": len(cert_map),
        "total_chat_messages": total_messages,
        "total_quiz_attempts": quiz_total,
        "quiz_accuracy_pct": quiz_accuracy,
        "total_flashcard_reviews": fc_total,
        "flashcard_known_pct": round(fc_known / fc_total * 100) if fc_total > 0 else 0,
        "spaces": space_rows_out,
        "recent_activity": [
            {
                "session_id": str(r.id),
                "space_id": str(r.space_id),
                "space_title": space_title_map.get(str(r.space_id), "Unknown"),
                "content_title": ci_title_map.get(str(r.content_item_id)) if r.content_item_id else None,
                "message_count": r.message_count,
                "last_active": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in recent_res
        ],
    }
