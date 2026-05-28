"""
Axis Frontend Admin API — endpoints for the axis.edzlms.com admin dashboard.

Separate from the Moodle-tenant admin (admin.py). All routes require
role=admin via the axis JWT auth system (get_current_user + require_role).

Routes:
  GET  /admin/status      — dashboard stat counts
  GET  /admin/features    — read platform feature flags
  PUT  /admin/features    — update platform feature flags
  GET  /admin/usage       — token/cost analytics (?period=7d|30d|90d)
  GET  /admin/audit       — paginated audit log (?limit=N&offset=N)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_dep, require_role
from app.core.database import get_db
from app.models.audit import AuditLog
from app.models.content import ContentItem
from app.models.space import LearningSpace
from app.models.user import AxisUser

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _period_start(period: str) -> datetime:
    days = {"7d": 7, "30d": 30, "90d": 90}.get(period, 30)
    return datetime.now(timezone.utc) - timedelta(days=days)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/status
# ─────────────────────────────────────────────────────────────────────────────

class AdminStatusResponse(BaseModel):
    total_users: int
    active_users: int
    total_spaces: int
    published_spaces: int
    total_content_items: int
    total_tokens_used: int
    total_cost_usd: float
    active_chat_sessions: int


@router.get(
    "/admin/status",
    response_model=AdminStatusResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_status(db: AsyncSession = Depends(get_db)):
    """Dashboard stats — user counts, space counts, content counts, token totals."""

    # Users
    total_users = (await db.execute(select(func.count()).select_from(AxisUser))).scalar() or 0
    active_users = (
        await db.execute(select(func.count()).select_from(AxisUser).where(AxisUser.is_active == True))
    ).scalar() or 0

    # Learning spaces
    total_spaces = (await db.execute(select(func.count()).select_from(LearningSpace))).scalar() or 0
    published_spaces = (
        await db.execute(
            select(func.count()).select_from(LearningSpace).where(LearningSpace.is_published == True)
        )
    ).scalar() or 0

    # Content items — use existing ContentItem if available, else 0
    try:
        total_content = (await db.execute(select(func.count()).select_from(ContentItem))).scalar() or 0
    except Exception:
        total_content = 0

    # Token usage — aggregate from audit_logs (all time)
    try:
        token_row = (
            await db.execute(
                select(
                    func.coalesce(func.sum(AuditLog.total_tokens), 0).label("tokens"),
                    func.coalesce(func.sum(AuditLog.estimated_cost_usd), 0.0).label("cost"),
                )
            )
        ).one()
        total_tokens = int(token_row.tokens)
        total_cost = float(token_row.cost)
    except Exception:
        total_tokens = 0
        total_cost = 0.0

    return AdminStatusResponse(
        total_users=total_users,
        active_users=active_users,
        total_spaces=total_spaces,
        published_spaces=published_spaces,
        total_content_items=total_content,
        total_tokens_used=total_tokens,
        total_cost_usd=round(total_cost, 4),
        active_chat_sessions=0,  # Future: count from chat_sessions table
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/features   PUT /admin/features
# ─────────────────────────────────────────────────────────────────────────────

class PlatformFeaturesResponse(BaseModel):
    summary: bool
    quiz: bool
    flashcards: bool
    glossary: bool
    faq: bool
    infographic: bool
    mindmap: bool
    objectives: bool
    blooms: bool
    chat: bool
    kb_chat: bool
    interactive_content: bool = True
    max_upload_size_mb: int = 100


class PlatformFeaturesUpdate(BaseModel):
    summary: Optional[bool] = None
    quiz: Optional[bool] = None
    flashcards: Optional[bool] = None
    glossary: Optional[bool] = None
    faq: Optional[bool] = None
    infographic: Optional[bool] = None
    mindmap: Optional[bool] = None
    objectives: Optional[bool] = None
    blooms: Optional[bool] = None
    chat: Optional[bool] = None
    kb_chat: Optional[bool] = None
    interactive_content: Optional[bool] = None
    max_upload_size_mb: Optional[int] = None


async def _get_or_create_settings(db: AsyncSession):
    """Return the single axis_platform_settings row, creating it if missing."""
    result = await db.execute(
        text("SELECT * FROM axis_platform_settings WHERE singleton_id = 1")
    )
    row = result.mappings().first()
    if row is None:
        await db.execute(
            text("INSERT INTO axis_platform_settings (singleton_id) VALUES (1) ON CONFLICT DO NOTHING")
        )
        await db.flush()
        result = await db.execute(
            text("SELECT * FROM axis_platform_settings WHERE singleton_id = 1")
        )
        row = result.mappings().first()
    return row


async def get_upload_limit_bytes(db: AsyncSession) -> int:
    """Return the admin-configured upload size limit in bytes.
    Falls back to 100 MB if the column doesn't exist yet (pre-migration).
    """
    try:
        result = await db.execute(
            text("SELECT max_upload_size_mb FROM axis_platform_settings WHERE singleton_id = 1")
        )
        row = result.mappings().first()
        mb = (row["max_upload_size_mb"] if row else None) or 100
    except Exception:
        mb = 100
    return mb * 1024 * 1024


async def get_current_ai_models(db: AsyncSession) -> tuple[str, str]:
    """
    Return (main_model, fast_model) from admin AI provider settings.
    Used by spaces.py and other modules that need to pick the right LLM.
    """
    row = await _get_or_create_settings(db)
    main_model = row.get("ai_model") or "gpt-4o"
    fast_model  = row.get("ai_model_fast") or "gpt-4o-mini"
    return main_model, fast_model

@router.get(
    "/admin/features",
    response_model=PlatformFeaturesResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_platform_features(db: AsyncSession = Depends(get_db)):
    """Return current platform-wide AI feature flags."""
    row = await _get_or_create_settings(db)
    return PlatformFeaturesResponse(
        summary=row["feature_summary"],
        quiz=row["feature_quiz"],
        flashcards=row["feature_flashcards"],
        glossary=row["feature_glossary"],
        faq=row["feature_faq"],
        infographic=row["feature_infographic"],
        mindmap=row["feature_mindmap"],
        objectives=row["feature_objectives"],
        blooms=row["feature_blooms"],
        chat=row["feature_chat"],
        kb_chat=row["feature_kb_chat"],
        interactive_content=row.get("feature_interactive_content", True) if row.get("feature_interactive_content") is not None else True,
        max_upload_size_mb=row.get("max_upload_size_mb", 100) or 100,
    )


@router.put(
    "/admin/features",
    response_model=PlatformFeaturesResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_platform_features(
    body: PlatformFeaturesUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update platform-wide AI feature flags. Only provided fields are updated."""
    # Build SET clause from non-None fields only
    raw = body.model_dump()
    if not any(v is not None for v in raw.values()):
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    set_parts: list[str] = []
    params: dict = {"updated_at": datetime.now(timezone.utc)}

    # Feature booleans use the feature_ prefix
    feature_keys = {k for k in raw if k != "max_upload_size_mb"}
    for k in feature_keys:
        if raw[k] is not None:
            set_parts.append(f"feature_{k} = :val_{k}")
            params[f"val_{k}"] = raw[k]

    # max_upload_size_mb is its own column (no prefix)
    if raw.get("max_upload_size_mb") is not None:
        mb = raw["max_upload_size_mb"]
        if not (1 <= mb <= 500):
            raise HTTPException(status_code=400, detail="max_upload_size_mb must be between 1 and 500.")
        set_parts.append("max_upload_size_mb = :max_upload_size_mb")
        params["max_upload_size_mb"] = mb

    if not set_parts:
        raise HTTPException(status_code=400, detail="No fields provided to update.")

    set_clauses = ", ".join(set_parts)

    await db.execute(
        text(
            f"UPDATE axis_platform_settings "
            f"SET {set_clauses}, updated_at = :updated_at "
            f"WHERE singleton_id = 1"
        ),
        params,
    )
    await db.commit()
    return await get_platform_features(db)


# ─────────────────────────────────────────────────────────────────────────────
# GET /features/public  — JWT-auth, for sidebar feature gating
# ─────────────────────────────────────────────────────────────────────────────

class PublicFeaturesResponse(BaseModel):
    """Minimal feature flags needed by the frontend for navigation / UI gating."""
    interactive_content: bool = True
    chat: bool = True
    kb_chat: bool = True


@router.get(
    "/features/public",
    response_model=PublicFeaturesResponse,
)
async def get_public_features(
    db: AsyncSession = Depends(get_db),
    _user: "AxisUser" = Depends(require_role("admin", "creator", "learner")),
):
    """Return UI-relevant feature flags to any authenticated user (for nav gating)."""
    try:
        row = await _get_or_create_settings(db)
        return PublicFeaturesResponse(
            interactive_content=row.get("feature_interactive_content", True) if row.get("feature_interactive_content") is not None else True,
            chat=bool(row.get("feature_chat", True)),
            kb_chat=bool(row.get("feature_kb_chat", True)),
        )
    except Exception:
        # Safe fallback — never block the UI on a missing column
        return PublicFeaturesResponse()


# ─────────────────────────────────────────────────────────────────────────────
# AI Provider & Model selection  GET/PUT /admin/ai-provider
# ─────────────────────────────────────────────────────────────────────────────

# Supported providers and their available models
AI_PROVIDER_MODELS: dict[str, list[dict]] = {
    "openai": [
        {"id": "gpt-4o",            "label": "GPT-4o (Recommended)",      "fast": False},
        {"id": "gpt-4o-mini",       "label": "GPT-4o Mini",               "fast": True },
        {"id": "gpt-4-turbo",       "label": "GPT-4 Turbo",               "fast": False},
        {"id": "gpt-3.5-turbo",     "label": "GPT-3.5 Turbo",             "fast": True },
    ],
    "anthropic": [
        {"id": "claude-opus-4-5",          "label": "Claude Opus 4.5 (Recommended)", "fast": False},
        {"id": "claude-sonnet-4-5",        "label": "Claude Sonnet 4.5",              "fast": False},
        {"id": "claude-haiku-4-5-20251001","label": "Claude Haiku 4.5 (Fast)",        "fast": True },
    ],
    "gemini": [
        {"id": "gemini/gemini-2.0-flash",      "label": "Gemini 2.0 Flash (Recommended)", "fast": True },
        {"id": "gemini/gemini-1.5-pro",        "label": "Gemini 1.5 Pro",                 "fast": False},
        {"id": "gemini/gemini-1.5-flash",      "label": "Gemini 1.5 Flash (Fast)",        "fast": True },
    ],
    "mistral": [
        {"id": "mistral/mistral-large-latest", "label": "Mistral Large (Recommended)",    "fast": False},
        {"id": "mistral/mistral-small-latest", "label": "Mistral Small (Fast)",           "fast": True },
    ],
}

PROVIDER_LABELS = {
    "openai":    "OpenAI",
    "anthropic": "Anthropic (Claude)",
    "gemini":    "Google Gemini",
    "mistral":   "Mistral AI",
}

PROVIDER_ENV_KEYS = {
    "openai":    "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini":    "GEMINI_API_KEY",
    "mistral":   "MISTRAL_API_KEY",
}


class AIProviderResponse(BaseModel):
    provider: str
    model: str
    model_fast: str
    available_providers: list[dict]


class AIProviderUpdate(BaseModel):
    provider: str
    model: str
    model_fast: str


@router.get(
    "/admin/ai-provider",
    response_model=AIProviderResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_ai_provider(db: AsyncSession = Depends(get_db)):
    """Return the current AI provider and model selections."""
    row = await _get_or_create_settings(db)
    provider = row.get("ai_provider") or "openai"
    model = row.get("ai_model") or "gpt-4o"
    model_fast = row.get("ai_model_fast") or "gpt-4o-mini"

    available = [
        {
            "id": pid,
            "label": PROVIDER_LABELS.get(pid, pid),
            "env_key": PROVIDER_ENV_KEYS.get(pid, ""),
            "models": models,
        }
        for pid, models in AI_PROVIDER_MODELS.items()
    ]

    return AIProviderResponse(
        provider=provider,
        model=model,
        model_fast=model_fast,
        available_providers=available,
    )


@router.put(
    "/admin/ai-provider",
    response_model=AIProviderResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def update_ai_provider(
    body: AIProviderUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update the AI provider and model selections."""
    if body.provider not in AI_PROVIDER_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{body.provider}'. Choose from: {list(AI_PROVIDER_MODELS.keys())}",
        )
    valid_models = {m["id"] for m in AI_PROVIDER_MODELS[body.provider]}
    if body.model not in valid_models:
        raise HTTPException(status_code=400, detail=f"Model '{body.model}' not valid for provider '{body.provider}'.")
    if body.model_fast not in valid_models:
        raise HTTPException(status_code=400, detail=f"Fast model '{body.model_fast}' not valid for provider '{body.provider}'.")

    await db.execute(
        text(
            "UPDATE axis_platform_settings "
            "SET ai_provider = :provider, ai_model = :model, ai_model_fast = :model_fast, "
            "    updated_at = :updated_at "
            "WHERE singleton_id = 1"
        ),
        {
            "provider": body.provider,
            "model": body.model,
            "model_fast": body.model_fast,
            "updated_at": datetime.now(timezone.utc),
        },
    )
    await db.commit()
    return await get_ai_provider(db)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/usage
# ─────────────────────────────────────────────────────────────────────────────

class DailyUsage(BaseModel):
    date: str           # "2026-05-01"
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    request_count: int


class UsageByType(BaseModel):
    task_type: str
    total_tokens: int
    estimated_cost_usd: float
    request_count: int


class AdminUsageResponse(BaseModel):
    period: str
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    total_cost_usd: float
    total_requests: int
    daily_breakdown: list[DailyUsage]
    by_task_type: list[UsageByType]


@router.get(
    "/admin/usage",
    response_model=AdminUsageResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_admin_usage(
    period: str = Query("30d", regex="^(7d|30d|90d)$"),
    db: AsyncSession = Depends(get_db),
):
    """Token and cost analytics for the selected period."""
    since = _period_start(period)

    # Totals
    try:
        totals_row = (
            await db.execute(
                select(
                    func.coalesce(func.sum(AuditLog.prompt_tokens), 0).label("prompt"),
                    func.coalesce(func.sum(AuditLog.completion_tokens), 0).label("completion"),
                    func.coalesce(func.sum(AuditLog.total_tokens), 0).label("total"),
                    func.coalesce(func.sum(AuditLog.estimated_cost_usd), 0.0).label("cost"),
                    func.count(AuditLog.id).label("requests"),
                ).where(AuditLog.created_at >= since)
            )
        ).one()
        prompt_t = int(totals_row.prompt)
        completion_t = int(totals_row.completion)
        total_t = int(totals_row.total)
        total_cost = round(float(totals_row.cost), 4)
        total_req = int(totals_row.requests)
    except Exception:
        prompt_t = completion_t = total_t = total_req = 0
        total_cost = 0.0

    # Daily breakdown — PostgreSQL date_trunc
    try:
        daily_rows = (
            await db.execute(
                select(
                    func.date_trunc("day", AuditLog.created_at).label("day"),
                    func.coalesce(func.sum(AuditLog.prompt_tokens), 0).label("prompt"),
                    func.coalesce(func.sum(AuditLog.completion_tokens), 0).label("completion"),
                    func.coalesce(func.sum(AuditLog.total_tokens), 0).label("total"),
                    func.coalesce(func.sum(AuditLog.estimated_cost_usd), 0.0).label("cost"),
                    func.count(AuditLog.id).label("requests"),
                )
                .where(AuditLog.created_at >= since)
                .group_by(text("1"))
                .order_by(text("1"))
            )
        ).all()
        daily = [
            DailyUsage(
                date=str(r.day)[:10],
                prompt_tokens=int(r.prompt),
                completion_tokens=int(r.completion),
                total_tokens=int(r.total),
                estimated_cost_usd=round(float(r.cost), 6),
                request_count=int(r.requests),
            )
            for r in daily_rows
        ]
    except Exception:
        daily = []

    # By task type
    try:
        type_rows = (
            await db.execute(
                select(
                    AuditLog.task_type,
                    func.coalesce(func.sum(AuditLog.total_tokens), 0).label("total"),
                    func.coalesce(func.sum(AuditLog.estimated_cost_usd), 0.0).label("cost"),
                    func.count(AuditLog.id).label("requests"),
                )
                .where(AuditLog.created_at >= since)
                .group_by(AuditLog.task_type)
                .order_by(text("total DESC"))
                .limit(20)
            )
        ).all()
        by_type = [
            UsageByType(
                task_type=r.task_type,
                total_tokens=int(r.total),
                estimated_cost_usd=round(float(r.cost), 6),
                request_count=int(r.requests),
            )
            for r in type_rows
        ]
    except Exception:
        by_type = []

    return AdminUsageResponse(
        period=period,
        total_tokens=total_t,
        prompt_tokens=prompt_t,
        completion_tokens=completion_t,
        total_cost_usd=total_cost,
        total_requests=total_req,
        daily_breakdown=daily,
        by_task_type=by_type,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/audit
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: str
    created_at: str
    task_type: str
    model: str
    provider: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: Optional[float]
    latency_ms: Optional[int]
    status: str
    error_message: Optional[str]
    content_item_id: Optional[str]
    job_id: Optional[str]


class AuditLogResponse(BaseModel):
    entries: list[AuditLogEntry]
    total: int
    limit: int
    offset: int


@router.get(
    "/admin/audit",
    response_model=AuditLogResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_audit_log(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    task_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="ISO date YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db),
):
    """Paginated audit log — most recent AI calls first, with optional filters."""
    from datetime import datetime as _dt
    # Build filter conditions
    conditions = []
    if task_type:
        conditions.append(AuditLog.task_type == task_type)
    if status:
        conditions.append(AuditLog.status == status)
    if date_from:
        try:
            conditions.append(AuditLog.created_at >= _dt.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            conditions.append(AuditLog.created_at < _dt.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            pass
    try:
        base_q = select(AuditLog)
        if conditions:
            from sqlalchemy import and_
            base_q = base_q.where(and_(*conditions))

        total = (
            await db.execute(select(func.count()).select_from(base_q.subquery()))
        ).scalar() or 0

        rows = (
            await db.execute(
                base_q
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()

        entries = [
            AuditLogEntry(
                id=str(r.id),
                created_at=r.created_at.isoformat() if r.created_at else "",
                task_type=r.task_type,
                model=r.model,
                provider=r.provider,
                prompt_tokens=r.prompt_tokens,
                completion_tokens=r.completion_tokens,
                total_tokens=r.total_tokens,
                estimated_cost_usd=r.estimated_cost_usd,
                latency_ms=r.latency_ms,
                status=str(r.status.value) if hasattr(r.status, 'value') else str(r.status),
                error_message=r.error_message,
                content_item_id=str(r.content_item_id) if r.content_item_id else None,
                job_id=str(r.job_id) if r.job_id else None,
            )
            for r in rows
        ]
    except Exception as e:
        entries = []
        total = 0

    return AuditLogResponse(
        entries=entries,
        total=total,
        limit=limit,
        offset=offset,
    )


# ── A-05: Admin content catalogue ─────────────────────────────────────────────

class ContentCatalogueItem(BaseModel):
    id: str
    title: Optional[str]
    content_type: str
    status: str
    space_id: Optional[str]
    space_title: Optional[str]
    creator_id: Optional[str]
    creator_name: Optional[str]
    language: str
    word_count: Optional[int]
    chunk_count: int
    file_size_bytes: Optional[int]
    source_url: Optional[str]
    created_at: str
    updated_at: str


class ContentCatalogueResponse(BaseModel):
    items: list[ContentCatalogueItem]
    total: int
    limit: int
    offset: int


@router.get(
    "/admin/content",
    response_model=ContentCatalogueResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def get_content_catalogue(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    content_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search by title or URL"),
    db: AsyncSession = Depends(get_db),
):
    """Admin view of all content items across all spaces."""
    from sqlalchemy import and_, or_
    conditions = [ContentItem.origin == "space"]
    if content_type:
        conditions.append(ContentItem.content_type == content_type)
    if status:
        conditions.append(ContentItem.status == status)
    if space_id:
        conditions.append(ContentItem.space_id == space_id)
    if search:
        like = f"%{search}%"
        conditions.append(or_(
            ContentItem.title.ilike(like),
            ContentItem.source_url.ilike(like),
        ))

    base_q = select(ContentItem).where(and_(*conditions))

    total = (
        await db.execute(select(func.count()).select_from(base_q.subquery()))
    ).scalar() or 0

    rows = (
        await db.execute(
            base_q.order_by(ContentItem.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()

    # Collect space IDs to resolve names
    space_ids = {str(r.space_id) for r in rows if r.space_id}
    space_map: dict[str, str] = {}
    if space_ids:
        space_rows = (
            await db.execute(
                select(LearningSpace.id, LearningSpace.title)
                .where(LearningSpace.id.in_([uuid.UUID(s) for s in space_ids]))
            )
        ).all()
        space_map = {str(s.id): s.title for s in space_rows}

    # Resolve creator names
    creator_ids = {str(r.creator_id) for r in rows if r.creator_id}
    creator_map: dict[str, str] = {}
    if creator_ids:
        from app.models.user import User
        creator_rows = (
            await db.execute(
                select(User.id, User.full_name, User.email)
                .where(User.id.in_([uuid.UUID(c) for c in creator_ids]))
            )
        ).all()
        creator_map = {str(u.id): (u.full_name or u.email) for u in creator_rows}

    items = [
        ContentCatalogueItem(
            id=str(r.id),
            title=r.title,
            content_type=str(r.content_type.value) if hasattr(r.content_type, "value") else str(r.content_type),
            status=str(r.status.value) if hasattr(r.status, "value") else str(r.status),
            space_id=str(r.space_id) if r.space_id else None,
            space_title=space_map.get(str(r.space_id)) if r.space_id else None,
            creator_id=str(r.creator_id) if r.creator_id else None,
            creator_name=creator_map.get(str(r.creator_id)) if r.creator_id else None,
            language=r.language,
            word_count=r.word_count,
            chunk_count=r.chunk_count,
            file_size_bytes=r.file_size_bytes,
            source_url=r.source_url,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in rows
    ]

    return ContentCatalogueResponse(items=items, total=total, limit=limit, offset=offset)


# ── Admin: delete a content item ─────────────────────────────────────────────

@router.delete(
    "/admin/content/{content_id}",
    status_code=204,
    dependencies=[Depends(require_role("admin"))],
)
async def admin_delete_content_item(
    content_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Admin force-delete any content item (bypasses creator ownership check)."""
    item = (
        await db.execute(select(ContentItem).where(ContentItem.id == uuid.UUID(content_id)))
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Content item not found")
    await db.delete(item)
    await db.commit()
    return


# ── Public: upload limit (readable by any authenticated user) ─────────────────

@router.get("/admin/upload-limit")
async def get_upload_limit_public(
    credentials: HTTPAuthorizationCredentials = Security(HTTPBearer()),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the current upload size limit. Any logged-in user can read this."""
    await get_current_user(credentials.credentials, db)  # just verify auth
    limit_bytes = await get_upload_limit_bytes(db)
    mb = limit_bytes // (1024 * 1024)
    return {"max_upload_size_mb": mb, "max_upload_size_bytes": limit_bytes}
