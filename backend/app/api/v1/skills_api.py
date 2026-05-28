"""
Skills API — skill categories, skills, content skill tags, user skill progress.

# Skill Categories (admin only)
GET    /api/v1/skills/categories                          → list with skill count
POST   /api/v1/skills/categories                          → create
PUT    /api/v1/skills/categories/{id}                     → update name
DELETE /api/v1/skills/categories/{id}                     → delete (guarded)

# Skills (admin create/edit, any authenticated can list)
GET    /api/v1/skills                                     → list all for tenant
POST   /api/v1/skills                                     → create  [admin]
PUT    /api/v1/skills/{id}                                → update  [admin]
DELETE /api/v1/skills/{id}                                → archive [admin]

# Content Skill Tags (creator / admin)
GET    /api/v1/skills/content/{content_item_id}/tags      → list tags for content item
POST   /api/v1/skills/content/{content_item_id}/tags      → add / confirm manual tag
DELETE /api/v1/skills/content/{content_item_id}/tags/{skill_id} → remove tag

# User Skill Progress
GET    /api/v1/skills/me/progress                         → own portfolio
GET    /api/v1/skills/users/{user_id}/progress            → any user's portfolio [admin]
"""
import uuid
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.skills import (
    ContentSkillTag,
    ProficiencyLevel,
    Skill,
    SkillCategory,
    UserSkillProgress,
)
from app.models.user import AxisUser

router = APIRouter(tags=["Skills"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SkillCategoryCreate(BaseModel):
    name: str


class SkillCategoryUpdate(BaseModel):
    name: str


class SkillCreate(BaseModel):
    name: str
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None


class SkillUpdate(BaseModel):
    name: Optional[str] = None
    category_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_archived: Optional[bool] = None


class ContentSkillTagCreate(BaseModel):
    skill_id: uuid.UUID
    level_id: Optional[uuid.UUID] = None
    source: str  # 'manual' | 'confirmed_ai'


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_admin(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin only")


def _require_creator_or_admin(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin only")


async def _get_skill(
    skill_id: uuid.UUID, tenant_id: uuid.UUID, db: AsyncSession
) -> Skill:
    result = await db.execute(
        select(Skill).where(Skill.id == skill_id, Skill.tenant_id == tenant_id)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/skills/categories")
async def list_skill_categories(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all skill categories for the tenant with skill count."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    result = await db.execute(
        select(SkillCategory)
        .where(SkillCategory.tenant_id == user.tenant_id)
        .order_by(SkillCategory.name)
    )
    categories = result.scalars().all()

    # Skill counts per category
    counts_result = await db.execute(
        select(Skill.category_id, func.count(Skill.id).label("cnt"))
        .where(Skill.tenant_id == user.tenant_id, Skill.is_archived == False)
        .group_by(Skill.category_id)
    )
    counts_map: dict[uuid.UUID, int] = {row.category_id: row.cnt for row in counts_result if row.category_id}

    return [
        {
            "id": str(cat.id),
            "name": cat.name,
            "skill_count": counts_map.get(cat.id, 0),
            "created_at": cat.created_at.isoformat(),
        }
        for cat in categories
    ]


@router.post("/skills/categories", status_code=201)
async def create_skill_category(
    body: SkillCategoryCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new skill category."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    dup = await db.execute(
        select(SkillCategory).where(
            SkillCategory.tenant_id == user.tenant_id,
            SkillCategory.name == body.name,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A category with this name already exists")

    cat = SkillCategory(tenant_id=user.tenant_id, name=body.name)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)

    log.info("skill_category_created", id=str(cat.id), name=cat.name, admin=str(user.id))
    return {
        "id": str(cat.id),
        "name": cat.name,
        "skill_count": 0,
        "created_at": cat.created_at.isoformat(),
    }


@router.put("/skills/categories/{category_id}")
async def update_skill_category(
    category_id: uuid.UUID,
    body: SkillCategoryUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a skill category name."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    result = await db.execute(
        select(SkillCategory).where(
            SkillCategory.id == category_id,
            SkillCategory.tenant_id == user.tenant_id,
        )
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    cat.name = body.name
    await db.commit()
    await db.refresh(cat)

    return {"id": str(cat.id), "name": cat.name, "created_at": cat.created_at.isoformat()}


@router.delete("/skills/categories/{category_id}", status_code=204)
async def delete_skill_category(
    category_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a skill category.

    Guarded: rejects if any skills (active or archived) exist in this category.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    result = await db.execute(
        select(SkillCategory).where(
            SkillCategory.id == category_id,
            SkillCategory.tenant_id == user.tenant_id,
        )
    )
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")

    skill_ref = await db.execute(
        select(Skill.id).where(Skill.category_id == category_id).limit(1)
    )
    if skill_ref.scalar_one_or_none():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete: this category still contains skills. Archive or reassign them first.",
        )

    await db.delete(cat)
    await db.commit()
    log.info("skill_category_deleted", id=str(category_id), admin=str(user.id))


# ═══════════════════════════════════════════════════════════════════════════════
# SKILLS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/skills")
async def list_skills(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all skills for the tenant (any authenticated user)."""
    user = await get_current_user(credentials.credentials, db)

    result = await db.execute(
        select(Skill, SkillCategory.name.label("category_name"))
        .outerjoin(SkillCategory, Skill.category_id == SkillCategory.id)
        .where(Skill.tenant_id == user.tenant_id)
        .order_by(Skill.name)
    )
    rows = result.all()

    # Content tag counts per skill
    counts_result = await db.execute(
        select(ContentSkillTag.skill_id, func.count(ContentSkillTag.id).label("cnt"))
        .join(Skill, ContentSkillTag.skill_id == Skill.id)
        .where(Skill.tenant_id == user.tenant_id)
        .group_by(ContentSkillTag.skill_id)
    )
    counts_map: dict[uuid.UUID, int] = {row.skill_id: row.cnt for row in counts_result}

    return [
        {
            "id": str(skill.id),
            "name": skill.name,
            "description": skill.description,
            "category_id": str(skill.category_id) if skill.category_id else None,
            "category_name": category_name,
            "is_archived": skill.is_archived,
            "content_tag_count": counts_map.get(skill.id, 0),
            "created_at": skill.created_at.isoformat(),
        }
        for skill, category_name in rows
    ]


@router.post("/skills", status_code=201)
async def create_skill(
    body: SkillCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new skill. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    dup = await db.execute(
        select(Skill).where(Skill.tenant_id == user.tenant_id, Skill.name == body.name)
    )
    if dup.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A skill with this name already exists")

    if body.category_id:
        cat_check = await db.execute(
            select(SkillCategory).where(
                SkillCategory.id == body.category_id,
                SkillCategory.tenant_id == user.tenant_id,
            )
        )
        if not cat_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Category not found")

    skill = Skill(
        tenant_id=user.tenant_id,
        name=body.name,
        category_id=body.category_id,
        description=body.description,
    )
    db.add(skill)
    await db.commit()
    await db.refresh(skill)

    log.info("skill_created", id=str(skill.id), name=skill.name, admin=str(user.id))
    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "category_id": str(skill.category_id) if skill.category_id else None,
        "is_archived": skill.is_archived,
        "created_at": skill.created_at.isoformat(),
    }


@router.put("/skills/{skill_id}")
async def update_skill(
    skill_id: uuid.UUID,
    body: SkillUpdate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update a skill. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    skill = await _get_skill(skill_id, user.tenant_id, db)

    if body.name is not None:
        skill.name = body.name
    if body.description is not None:
        skill.description = body.description
    if body.category_id is not None:
        cat_check = await db.execute(
            select(SkillCategory).where(
                SkillCategory.id == body.category_id,
                SkillCategory.tenant_id == user.tenant_id,
            )
        )
        if not cat_check.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Category not found")
        skill.category_id = body.category_id
    if body.is_archived is not None:
        skill.is_archived = body.is_archived

    await db.commit()
    await db.refresh(skill)

    return {
        "id": str(skill.id),
        "name": skill.name,
        "description": skill.description,
        "category_id": str(skill.category_id) if skill.category_id else None,
        "is_archived": skill.is_archived,
        "created_at": skill.created_at.isoformat(),
    }


@router.delete("/skills/{skill_id}", status_code=200)
async def archive_skill(
    skill_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Archive a skill (sets is_archived=True). Admin only."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    skill = await _get_skill(skill_id, user.tenant_id, db)
    skill.is_archived = True
    await db.commit()

    log.info("skill_archived", id=str(skill_id), admin=str(user.id))
    return {"id": str(skill_id), "is_archived": True}


# ═══════════════════════════════════════════════════════════════════════════════
# CONTENT SKILL TAGS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/skills/content/{content_item_id}/tags")
async def list_content_skill_tags(
    content_item_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all skill tags for a content item."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    result = await db.execute(
        select(ContentSkillTag, Skill, ProficiencyLevel)
        .join(Skill, ContentSkillTag.skill_id == Skill.id)
        .outerjoin(ProficiencyLevel, ContentSkillTag.level_id == ProficiencyLevel.id)
        .where(
            ContentSkillTag.content_item_id == content_item_id,
            Skill.tenant_id == user.tenant_id,
        )
        .order_by(Skill.name)
    )
    rows = result.all()

    return [
        {
            "id": str(tag.id),
            "skill_id": str(tag.skill_id),
            "skill_name": skill.name,
            "level_id": str(tag.level_id) if tag.level_id else None,
            "level_label": level.label if level else None,
            "source": tag.source,
            "confidence": tag.confidence,
            "tagged_by": str(tag.tagged_by) if tag.tagged_by else None,
            "created_at": tag.created_at.isoformat(),
        }
        for tag, skill, level in rows
    ]


@router.post("/skills/content/{content_item_id}/tags", status_code=201)
async def add_content_skill_tag(
    content_item_id: uuid.UUID,
    body: ContentSkillTagCreate,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Add or confirm a manual skill tag on a content item.

    If a tag already exists for (content_item_id, skill_id), updates level_id and source.
    Otherwise creates a new record.
    """
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    skill = await _get_skill(body.skill_id, user.tenant_id, db)

    level: Optional[ProficiencyLevel] = None
    if body.level_id:
        level_result = await db.execute(
            select(ProficiencyLevel).where(
                ProficiencyLevel.id == body.level_id,
                ProficiencyLevel.tenant_id == user.tenant_id,
            )
        )
        level = level_result.scalar_one_or_none()
        if not level:
            raise HTTPException(status_code=404, detail="Proficiency level not found")

    # Validate source value
    valid_sources = {"manual", "confirmed_ai", "ai"}
    if body.source not in valid_sources:
        raise HTTPException(
            status_code=422,
            detail=f"source must be one of: {', '.join(sorted(valid_sources))}",
        )

    # Check for existing tag
    existing = await db.execute(
        select(ContentSkillTag).where(
            ContentSkillTag.content_item_id == content_item_id,
            ContentSkillTag.skill_id == body.skill_id,
        )
    )
    tag = existing.scalar_one_or_none()

    if tag:
        tag.level_id = body.level_id
        tag.source = body.source
        tag.tagged_by = user.id
        tag.confidence = 1.0 if body.source in ("manual", "confirmed_ai") else tag.confidence
        await db.commit()
        await db.refresh(tag)
        created = False
    else:
        tag = ContentSkillTag(
            content_item_id=content_item_id,
            skill_id=body.skill_id,
            level_id=body.level_id,
            source=body.source,
            confidence=1.0 if body.source in ("manual", "confirmed_ai") else None,
            tagged_by=user.id,
        )
        db.add(tag)
        await db.commit()
        await db.refresh(tag)
        created = True

    log.info(
        "content_skill_tag_upserted",
        content=str(content_item_id),
        skill=str(body.skill_id),
        created=created,
        user=str(user.id),
    )
    return {
        "id": str(tag.id),
        "skill_id": str(tag.skill_id),
        "skill_name": skill.name,
        "level_id": str(tag.level_id) if tag.level_id else None,
        "level_label": level.label if level else None,
        "source": tag.source,
        "created": created,
        "created_at": tag.created_at.isoformat(),
    }


@router.delete("/skills/content/{content_item_id}/tags/{skill_id}", status_code=204)
async def remove_content_skill_tag(
    content_item_id: uuid.UUID,
    skill_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a skill tag from a content item."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    result = await db.execute(
        select(ContentSkillTag).where(
            ContentSkillTag.content_item_id == content_item_id,
            ContentSkillTag.skill_id == skill_id,
        )
    )
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Skill tag not found")

    await db.delete(tag)
    await db.commit()
    log.info(
        "content_skill_tag_removed",
        content=str(content_item_id),
        skill=str(skill_id),
        user=str(user.id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# USER SKILL PROGRESS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/skills/me/progress")
async def get_my_skill_progress(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return the authenticated learner's own skill portfolio."""
    user = await get_current_user(credentials.credentials, db)
    return await _build_skill_portfolio(user.id, db)


@router.get("/skills/users/{target_user_id}/progress")
async def get_user_skill_progress(
    target_user_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Return any user's skill portfolio. Admin only."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    # Verify target user exists in same tenant
    target_result = await db.execute(
        select(AxisUser).where(
            AxisUser.id == target_user_id,
            AxisUser.tenant_id == user.tenant_id,
        )
    )
    if not target_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    return await _build_skill_portfolio(target_user_id, db)


async def _build_skill_portfolio(
    target_user_id: uuid.UUID, db: AsyncSession
) -> list[dict[str, Any]]:
    """Shared helper: fetch UserSkillProgress rows for a user with enriched names."""
    result = await db.execute(
        select(UserSkillProgress, Skill, ProficiencyLevel, SkillCategory)
        .join(Skill, UserSkillProgress.skill_id == Skill.id)
        .join(ProficiencyLevel, UserSkillProgress.current_level_id == ProficiencyLevel.id)
        .outerjoin(SkillCategory, Skill.category_id == SkillCategory.id)
        .where(UserSkillProgress.user_id == target_user_id)
        .order_by(SkillCategory.name.nullslast(), Skill.name)
    )
    rows = result.all()

    return [
        {
            "id": str(progress.id),
            "skill_id": str(progress.skill_id),
            "skill_name": skill.name,
            "skill_description": skill.description,
            "category_id": str(skill.category_id) if skill.category_id else None,
            "category_name": category.name if category else None,
            "current_level_id": str(progress.current_level_id),
            "current_level_label": level.label,
            "current_level_order": level.level_order,
            "source_content_id": str(progress.source_content_id) if progress.source_content_id else None,
            "earned_at": progress.earned_at.isoformat(),
            "updated_at": progress.updated_at.isoformat(),
        }
        for progress, skill, level, category in rows
    ]
