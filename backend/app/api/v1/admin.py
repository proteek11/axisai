"""
Admin API — tenant management and user token override management.

All endpoints require a master/admin-scoped API key.
Called by the Moodle edzaiaxisfront plugin on:
  - First install: POST /admin/tenants
  - Admin saves settings: PUT /admin/tenants/{id}
  - Health check: GET /admin/tenants/{id}/status
  - Per-user override: POST /admin/tenants/{id}/user-overrides
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant
from app.models.chat import ChatSession
from app.models.content import ContentItem
from app.models.kb import KnowledgeBaseItem
from app.models.tenant import Tenant, UserTokenOverride
from app.schemas.admin import (
    TenantCreateRequest,
    TenantUpdateRequest,
    TenantResponse,
    TenantStatusResponse,
    TenantSyncRateLimitsRequest,
    TenantSyncResponse,
    UserTokenOverrideRequest,
    UserTokenOverrideResponse,
)

router = APIRouter()
log = structlog.get_logger(__name__)


# ── Tenant CRUD ───────────────────────────────────────────────────────────────



# ── Tenant seed data ──────────────────────────────────────────────────────────

async def _seed_tenant_defaults(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    """
    Called once after a new tenant is created.
    Seeds:
      - 3 default proficiency levels (Awareness / Working / Expert)
      - 5 default org roles (New Joiner / Team Member / Team Lead / Manager / Director)
    These are fully editable/deletable by admin after creation.
    """
    from app.models.skills import ProficiencyLevel, OrgRole

    # Proficiency levels
    levels = [
        {"level_order": 1, "label": "Awareness",  "description": "Basic knowledge, can recognise concepts"},
        {"level_order": 2, "label": "Working",    "description": "Can apply the skill with guidance"},
        {"level_order": 3, "label": "Expert",     "description": "Can teach and lead others"},
    ]
    for lv in levels:
        db.add(ProficiencyLevel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            level_order=lv["level_order"],
            label=lv["label"],
            description=lv["description"],
        ))

    # Org roles (no team — general roles)
    roles = ["New Joiner", "Team Member", "Team Lead", "Manager", "Director"]
    for name in roles:
        db.add(OrgRole(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            team_id=None,
            name=name,
            is_archived=False,
        ))

    await db.commit()
    log.info("tenant_seeded", tenant_id=str(tenant_id))

@router.post("/tenants", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    req: TenantCreateRequest,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),  # requires valid API key
) -> TenantResponse:
    """
    Create a new tenant. Called by Moodle edzaiaxisfront on first plugin setup.
    The caller's API key must have admin scope.
    """
    # Check for duplicate moodle_url
    result = await db.execute(
        select(Tenant).where(Tenant.moodle_url == req.moodle_url)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with moodle_url '{req.moodle_url}' already exists.",
        )

    tenant = Tenant(
        id=uuid.uuid4(),
        name=req.name,
        moodle_url=req.moodle_url,
        is_active=True,
        # Feature flags
        feature_summary=req.features.feature_summary,
        feature_glossary=req.features.feature_glossary,
        feature_flashcards=req.features.feature_flashcards,
        feature_quiz=req.features.feature_quiz,
        feature_faq=req.features.feature_faq,
        feature_infographic=req.features.feature_infographic,
        feature_chatbot=req.features.feature_chatbot,
        feature_kb_chat=req.features.feature_kb_chat,
        # Rate limits
        chat_session_msg_limit=req.rate_limits.chat_session_msg_limit,
        chat_daily_msg_limit=req.rate_limits.chat_daily_msg_limit,
        chat_monthly_msg_limit=req.rate_limits.chat_monthly_msg_limit,
        token_monthly_limit=req.rate_limits.token_monthly_limit,
        config=req.config,
    )
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)

    # Seed default proficiency levels + org roles for the new tenant
    await _seed_tenant_defaults(tenant.id, db)

    log.info("tenant_created", tenant_id=str(tenant.id), name=tenant.name, url=tenant.moodle_url)
    return TenantResponse.model_validate(tenant)


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> TenantResponse:
    """Fetch full tenant config — used by Moodle to sync settings on page load."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return TenantResponse.model_validate(tenant)


async def update_tenant(
    tenant_id: uuid.UUID,
    req: TenantUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> TenantResponse:
    """
    Update tenant settings. Partial update — only provided fields change.
    Called every time Moodle admin saves the plugin settings page.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    if req.name is not None:
        tenant.name = req.name
    if req.is_active is not None:
        tenant.is_active = req.is_active
    if req.config is not None:
        tenant.config = req.config

    if req.features is not None:
        tenant.feature_summary = req.features.feature_summary
        tenant.feature_glossary = req.features.feature_glossary
        tenant.feature_flashcards = req.features.feature_flashcards
        tenant.feature_quiz = req.features.feature_quiz
        tenant.feature_faq = req.features.feature_faq
        tenant.feature_infographic = req.features.feature_infographic
        tenant.feature_chatbot = req.features.feature_chatbot
        tenant.feature_kb_chat = req.features.feature_kb_chat

    if req.rate_limits is not None:
        tenant.chat_session_msg_limit = req.rate_limits.chat_session_msg_limit
        tenant.chat_daily_msg_limit = req.rate_limits.chat_daily_msg_limit
        tenant.chat_monthly_msg_limit = req.rate_limits.chat_monthly_msg_limit
        tenant.token_monthly_limit = req.rate_limits.token_monthly_limit

    await db.commit()
    await db.refresh(tenant)

    log.info("tenant_updated", tenant_id=str(tenant.id))
    return TenantResponse.model_validate(tenant)


# Register for both PUT (REST-correct) and POST (Moodle curl compat — curl sends
# POST even when CURLOPT_CUSTOMREQUEST => 'PUT' is set, due to Moodle wrapper bug)
router.add_api_route(
    "/tenants/{tenant_id}",
    update_tenant,
    methods=["PUT", "POST"],
    response_model=TenantResponse,
    tags=["Admin"],
    summary="Update tenant settings (PUT or POST)",
)


@router.get("/tenants/{tenant_id}/status", response_model=TenantStatusResponse)
async def get_tenant_status(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> TenantStatusResponse:
    """
    Quick health/stats for a tenant.
    Moodle plugin displays this on the admin dashboard.
    """
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    # Content items count
    ci_count = await db.scalar(
        select(func.count()).where(ContentItem.tenant_id == tenant_id)
    )
    # KB items count
    kb_count = await db.scalar(
        select(func.count()).where(
            KnowledgeBaseItem.tenant_id == tenant_id,
            KnowledgeBaseItem.is_active == True,
        )
    )
    # Active chat sessions
    chat_count = await db.scalar(
        select(func.count()).where(
            ChatSession.tenant_id == tenant_id,
            ChatSession.is_active == True,
        )
    )

    # Build enabled features list
    features_enabled = []
    if tenant.feature_summary: features_enabled.append("summary")
    if tenant.feature_glossary: features_enabled.append("glossary")
    if tenant.feature_flashcards: features_enabled.append("flashcards")
    if tenant.feature_quiz: features_enabled.append("quiz")
    if tenant.feature_faq: features_enabled.append("faq")
    if tenant.feature_infographic: features_enabled.append("infographic")
    if tenant.feature_chatbot: features_enabled.append("chatbot")
    if tenant.feature_kb_chat: features_enabled.append("kb_chat")

    return TenantStatusResponse(
        tenant_id=tenant.id,
        name=tenant.name,
        is_active=tenant.is_active,
        content_items_count=ci_count or 0,
        kb_items_count=kb_count or 0,
        active_chat_sessions=chat_count or 0,
        features_enabled=features_enabled,
    )


# ── Self-service rate limit sync (no tenant UUID required) ───────────────────

@router.post(
    "/tenants/me/settings",
    response_model=TenantSyncResponse,
    summary="Sync rate limit settings from Moodle to this tenant",
    description=(
        "Update the rate limits of the authenticated tenant without needing its UUID. "
        "The tenant is resolved from the Bearer API key. "
        "Called by the Moodle plugin 'Sync to axis-ai' button."
    ),
)
async def sync_tenant_settings(
    req: TenantSyncRateLimitsRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> TenantSyncResponse:
    """Update rate limits for the tenant identified by the API key."""
    result = await db.execute(select(Tenant).where(Tenant.id == tenant.id))
    db_tenant = result.scalar_one_or_none()
    if not db_tenant:
        raise HTTPException(status_code=404, detail="Tenant not found.")

    db_tenant.chat_session_msg_limit = req.chat_session_msg_limit
    db_tenant.chat_daily_msg_limit = req.chat_daily_msg_limit
    db_tenant.chat_monthly_msg_limit = req.chat_monthly_msg_limit
    db_tenant.token_monthly_limit = req.token_monthly_limit

    await db.commit()
    await db.refresh(db_tenant)

    log.info(
        "tenant_rate_limits_synced",
        tenant_id=str(db_tenant.id),
        chat_session_msg_limit=req.chat_session_msg_limit,
        chat_daily_msg_limit=req.chat_daily_msg_limit,
        chat_monthly_msg_limit=req.chat_monthly_msg_limit,
        token_monthly_limit=req.token_monthly_limit,
    )
    return TenantSyncResponse(
        success=True,
        tenant_id=str(db_tenant.id),
        message=(
            f"Rate limits synced: session={req.chat_session_msg_limit}, "
            f"daily={req.chat_daily_msg_limit}, "
            f"monthly={req.chat_monthly_msg_limit}, "
            f"tokens={req.token_monthly_limit}"
        ),
    )


# ── User Token Overrides ──────────────────────────────────────────────────────
# IMPORTANT: "me" routes MUST be defined before "{tenant_id}" param routes.
# FastAPI matches top-down; if {tenant_id} came first, "me" would be parsed
# as a uuid.UUID, fail validation, and return 422.

@router.post(
    "/tenants/me/user-overrides",
    response_model=UserTokenOverrideResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert a per-user override — tenant resolved from API key",
)
async def upsert_user_override_me(
    req: UserTokenOverrideRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> UserTokenOverrideResponse:
    """Create or update a per-user rate limit override. Tenant identified by API key."""
    result = await db.execute(
        select(UserTokenOverride).where(
            UserTokenOverride.tenant_id == tenant.id,
            UserTokenOverride.moodle_user_id == req.moodle_user_id,
        )
    )
    override = result.scalar_one_or_none()

    if override:
        override.chat_session_msg_limit = req.chat_session_msg_limit
        override.chat_daily_msg_limit = req.chat_daily_msg_limit
        override.chat_monthly_msg_limit = req.chat_monthly_msg_limit
        override.token_monthly_limit = req.token_monthly_limit
        override.note = req.note
        override.set_by_moodle_user_id = req.set_by_moodle_user_id
    else:
        override = UserTokenOverride(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            moodle_user_id=req.moodle_user_id,
            chat_session_msg_limit=req.chat_session_msg_limit,
            chat_daily_msg_limit=req.chat_daily_msg_limit,
            chat_monthly_msg_limit=req.chat_monthly_msg_limit,
            token_monthly_limit=req.token_monthly_limit,
            note=req.note,
            set_by_moodle_user_id=req.set_by_moodle_user_id,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    log.info(
        "user_override_upserted",
        tenant_id=str(tenant.id),
        moodle_user_id=req.moodle_user_id,
    )
    return UserTokenOverrideResponse.model_validate(override)


@router.delete(
    "/tenants/me/user-overrides/{moodle_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a per-user override — tenant resolved from API key",
)
async def delete_user_override_me(
    moodle_user_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """Remove a per-user override. Tenant identified by API key."""
    result = await db.execute(
        select(UserTokenOverride).where(
            UserTokenOverride.tenant_id == tenant.id,
            UserTokenOverride.moodle_user_id == moodle_user_id,
        )
    )
    override = result.scalar_one_or_none()
    if override:
        await db.delete(override)
        await db.commit()
        log.info(
            "user_override_deleted",
            tenant_id=str(tenant.id),
            moodle_user_id=moodle_user_id,
        )


@router.post(
    "/tenants/me/user-overrides/{moodle_user_id}/delete",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="POST alias for DELETE user override — Moodle curl compat",
)
async def delete_user_override_me_post(
    moodle_user_id: int,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """POST alias because Moodle's curl wrapper sends POST even when DELETE is intended."""
    return await delete_user_override_me(moodle_user_id, db, tenant)


# ── User overrides via explicit tenant UUID (kept for direct API use) ─────────

@router.post(
    "/tenants/{tenant_id}/user-overrides",
    response_model=UserTokenOverrideResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_user_override(
    tenant_id: uuid.UUID,
    req: UserTokenOverrideRequest,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> UserTokenOverrideResponse:
    """
    Create or update a per-user rate limit override using explicit tenant UUID.
    Prefer the /me/ variant when calling from Moodle.
    """
    result = await db.execute(
        select(UserTokenOverride).where(
            UserTokenOverride.tenant_id == tenant_id,
            UserTokenOverride.moodle_user_id == req.moodle_user_id,
        )
    )
    override = result.scalar_one_or_none()

    if override:
        override.chat_session_msg_limit = req.chat_session_msg_limit
        override.chat_daily_msg_limit = req.chat_daily_msg_limit
        override.chat_monthly_msg_limit = req.chat_monthly_msg_limit
        override.token_monthly_limit = req.token_monthly_limit
        override.note = req.note
        override.set_by_moodle_user_id = req.set_by_moodle_user_id
    else:
        override = UserTokenOverride(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            moodle_user_id=req.moodle_user_id,
            chat_session_msg_limit=req.chat_session_msg_limit,
            chat_daily_msg_limit=req.chat_daily_msg_limit,
            chat_monthly_msg_limit=req.chat_monthly_msg_limit,
            token_monthly_limit=req.token_monthly_limit,
            note=req.note,
            set_by_moodle_user_id=req.set_by_moodle_user_id,
        )
        db.add(override)

    await db.commit()
    await db.refresh(override)
    log.info(
        "user_override_upserted",
        tenant_id=str(tenant_id),
        moodle_user_id=req.moodle_user_id,
    )
    return UserTokenOverrideResponse.model_validate(override)


@router.get(
    "/tenants/{tenant_id}/user-overrides",
    response_model=list[UserTokenOverrideResponse],
)
async def list_user_overrides(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> list[UserTokenOverrideResponse]:
    """List all per-user overrides for a tenant — displayed in admin settings."""
    result = await db.execute(
        select(UserTokenOverride).where(UserTokenOverride.tenant_id == tenant_id)
    )
    overrides = result.scalars().all()
    return [UserTokenOverrideResponse.model_validate(o) for o in overrides]


@router.delete(
    "/tenants/{tenant_id}/user-overrides/{moodle_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_user_override(
    tenant_id: uuid.UUID,
    moodle_user_id: int,
    db: AsyncSession = Depends(get_db),
    _tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """Remove a per-user override — user reverts to tenant baseline limits."""
    result = await db.execute(
        select(UserTokenOverride).where(
            UserTokenOverride.tenant_id == tenant_id,
            UserTokenOverride.moodle_user_id == moodle_user_id,
        )
    )
    override = result.scalar_one_or_none()
    if override:
        await db.delete(override)
        await db.commit()
        log.info(
            "user_override_deleted",
            tenant_id=str(tenant_id),
            moodle_user_id=moodle_user_id,
        )


# ── Qdrant diagnostic endpoint ─────────────────────────────────────────────────

@router.get(
    "/qdrant/debug",
    summary="Check Qdrant vector counts for this tenant",
    description=(
        "Returns how many chunks are indexed in Qdrant for this tenant. "
        "Pass content_item_id to check a specific content item. "
        "Used to diagnose RAG returning empty results."
    ),
)
async def qdrant_debug(
    content_item_id: str | None = None,
    tenant: Tenant = Depends(get_current_tenant),
) -> dict:
    """Check Qdrant chunk counts — diagnostic endpoint for empty RAG results."""
    from app.core.qdrant import get_qdrant
    from app.config import settings
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    qdrant = get_qdrant()

    # Count all chunks for this tenant
    tenant_result = await qdrant.count(
        collection_name=settings.qdrant_collection_content_chunks,
        count_filter=Filter(must=[
            FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant.id)))
        ]),
        exact=True,
    )

    response = {
        "tenant_id": str(tenant.id),
        "total_chunks_in_qdrant": tenant_result.count,
    }

    # If a specific content_item_id is provided, also count just for that item
    if content_item_id:
        item_result = await qdrant.count(
            collection_name=settings.qdrant_collection_content_chunks,
            count_filter=Filter(must=[
                FieldCondition(key="tenant_id", match=MatchValue(value=str(tenant.id))),
                FieldCondition(key="content_item_id", match=MatchValue(value=content_item_id)),
            ]),
            exact=True,
        )
        response["content_item_id"] = content_item_id
        response["chunks_for_content_item"] = item_result.count

    return response
