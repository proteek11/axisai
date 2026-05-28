"""
Skills Service — award, query, and AI-tag skills for learners.

Functions:
  award_skills_for_completion  — called on content completion; upserts UserSkillProgress
  get_user_skills_portfolio    — full skills dashboard payload for a learner
  ai_tag_content_skills        — LiteLLM auto-tag a content item with skills
  get_org_skill_gap_heatmap    — admin heatmap: teams × skills, % meeting target
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skills import (
    ContentSkillTag,
    OrgRole,
    OrgRoleSkillTarget,
    ProficiencyLevel,
    Skill,
    SkillCategory,
    UserOrgRole,
    UserSkillProgress,
)
from app.models.content import ContentItem
from app.models.team import Team, TeamMember
from app.models.user import AxisUser

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# award_skills_for_completion
# ---------------------------------------------------------------------------

async def award_skills_for_completion(
    user_id: uuid.UUID,
    content_item_id: uuid.UUID,
    db: AsyncSession,
) -> list[dict]:
    """
    Called when a learner completes a content item.

    1. Fetch all ContentSkillTag rows for content_item_id.
    2. For each tag, check if user has UserSkillProgress for that skill.
    3. If not, create it with current_level_id = tag.level_id, falling back
       to the lowest proficiency level for the tenant if tag.level_id is None.
    4. If exists and tag.level_id's level_order > current level's level_order,
       upgrade the row.
    5. Return list of {skill_id, skill_name, old_level, new_level, upgraded: bool}.
    """
    results: list[dict] = []

    # --- fetch all skill tags for this content item, join Skill + optional level ---
    tags_result = await db.execute(
        select(ContentSkillTag, Skill, ProficiencyLevel)
        .join(Skill, Skill.id == ContentSkillTag.skill_id)
        .outerjoin(ProficiencyLevel, ProficiencyLevel.id == ContentSkillTag.level_id)
        .where(ContentSkillTag.content_item_id == content_item_id)
        .where(Skill.is_archived == False)
    )
    tag_rows = tags_result.all()

    if not tag_rows:
        return results

    # Collect the tenant_id from the content item (needed for lowest-level fallback)
    content_result = await db.execute(
        select(ContentItem).where(ContentItem.id == content_item_id)
    )
    content_item = content_result.scalar_one_or_none()
    tenant_id: uuid.UUID | None = content_item.tenant_id if content_item else None

    # Cache lowest proficiency level per tenant to avoid repeated queries
    _lowest_level_cache: dict[uuid.UUID, ProficiencyLevel | None] = {}

    async def _get_lowest_level(tid: uuid.UUID) -> ProficiencyLevel | None:
        if tid in _lowest_level_cache:
            return _lowest_level_cache[tid]
        row = await db.execute(
            select(ProficiencyLevel)
            .where(ProficiencyLevel.tenant_id == tid)
            .order_by(ProficiencyLevel.level_order.asc())
            .limit(1)
        )
        level = row.scalar_one_or_none()
        _lowest_level_cache[tid] = level
        return level

    for tag, skill, tag_level in tag_rows:
        # Resolve the target level for this tag
        if tag_level is not None:
            target_level = tag_level
        elif tenant_id is not None:
            target_level = await _get_lowest_level(tenant_id)
        else:
            target_level = None

        if target_level is None:
            log.warning(
                "skills_award_no_level",
                skill_id=str(skill.id),
                content_item_id=str(content_item_id),
            )
            continue

        # Fetch existing progress row
        prog_result = await db.execute(
            select(UserSkillProgress, ProficiencyLevel)
            .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
            .where(UserSkillProgress.user_id == user_id)
            .where(UserSkillProgress.skill_id == skill.id)
        )
        prog_row = prog_result.first()

        if prog_row is None:
            # Create new progress row
            progress = UserSkillProgress(
                id=uuid.uuid4(),
                user_id=user_id,
                skill_id=skill.id,
                current_level_id=target_level.id,
                source_content_id=content_item_id,
                earned_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(progress)
            await db.flush()

            results.append({
                "skill_id": str(skill.id),
                "skill_name": skill.name,
                "old_level": None,
                "new_level": target_level.label,
                "upgraded": True,
            })
            log.info(
                "skill_awarded_new",
                user_id=str(user_id),
                skill=skill.name,
                level=target_level.label,
            )

        else:
            existing_progress, current_level = prog_row
            if target_level.level_order > current_level.level_order:
                # Upgrade
                existing_progress.current_level_id = target_level.id
                existing_progress.source_content_id = content_item_id
                existing_progress.updated_at = datetime.now(timezone.utc)
                await db.flush()

                results.append({
                    "skill_id": str(skill.id),
                    "skill_name": skill.name,
                    "old_level": current_level.label,
                    "new_level": target_level.label,
                    "upgraded": True,
                })
                log.info(
                    "skill_upgraded",
                    user_id=str(user_id),
                    skill=skill.name,
                    old=current_level.label,
                    new=target_level.label,
                )
            else:
                # Already at equal or higher level — no change
                results.append({
                    "skill_id": str(skill.id),
                    "skill_name": skill.name,
                    "old_level": current_level.label,
                    "new_level": current_level.label,
                    "upgraded": False,
                })

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        log.error("skills_award_commit_failed", error=str(exc))
        return []

    return results


# ---------------------------------------------------------------------------
# get_user_skills_portfolio
# ---------------------------------------------------------------------------

async def get_user_skills_portfolio(
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Returns the learner's full skills portfolio.

    {
      skills: [{skill_id, skill_name, category_name, current_level_label,
                current_level_order, target_level_label, target_level_order,
                gap: int, source_content_title}],
      categories: [{category_name, skills_count, avg_attainment_pct}],
      overall_attainment_pct: float,
    }
    """
    # --- fetch user's active org role ---
    user_result = await db.execute(
        select(AxisUser).where(AxisUser.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    active_role_id: uuid.UUID | None = user.active_org_role_id if user else None

    # --- fetch skill targets for user's role (skill_id → target ProficiencyLevel) ---
    role_targets: dict[uuid.UUID, tuple[str, int]] = {}  # skill_id → (label, order)
    if active_role_id is not None:
        targets_result = await db.execute(
            select(OrgRoleSkillTarget, ProficiencyLevel)
            .join(ProficiencyLevel, ProficiencyLevel.id == OrgRoleSkillTarget.target_level_id)
            .where(OrgRoleSkillTarget.org_role_id == active_role_id)
        )
        for target, plevel in targets_result.all():
            role_targets[target.skill_id] = (plevel.label, plevel.level_order)

    # --- fetch all user skill progress rows ---
    progress_result = await db.execute(
        select(UserSkillProgress, Skill, SkillCategory, ProficiencyLevel, ContentItem)
        .join(Skill, Skill.id == UserSkillProgress.skill_id)
        .outerjoin(SkillCategory, SkillCategory.id == Skill.category_id)
        .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
        .outerjoin(ContentItem, ContentItem.id == UserSkillProgress.source_content_id)
        .where(UserSkillProgress.user_id == user_id)
        .where(Skill.tenant_id == tenant_id)
        .where(Skill.is_archived == False)
        .order_by(SkillCategory.name.asc().nullslast(), Skill.name.asc())
    )
    progress_rows = progress_result.all()

    skills_list: list[dict] = []
    # category_name → {skills_count, total_attainment_pct_sum}
    category_stats: dict[str, dict[str, Any]] = {}
    total_attainment_sum = 0.0
    total_skills = 0

    for prog, skill, category, current_level, source_content in progress_rows:
        category_name = category.name if category else "Uncategorised"
        target_label, target_order = role_targets.get(skill.id, (None, None))

        # Gap = target_order - current_order (negative or 0 means met/exceeded)
        gap = (target_order - current_level.level_order) if target_order is not None else 0

        # Attainment % for this skill relative to target
        if target_order is not None and target_order > 0:
            attainment_pct = min(100.0, (current_level.level_order / target_order) * 100.0)
        else:
            # No target set — treat current level as 100% attainment for aggregation
            attainment_pct = 100.0

        skills_list.append({
            "skill_id": str(skill.id),
            "skill_name": skill.name,
            "category_name": category_name,
            "current_level_label": current_level.label,
            "current_level_order": current_level.level_order,
            "target_level_label": target_label,
            "target_level_order": target_order,
            "gap": max(0, gap),
            "source_content_title": source_content.title if source_content else None,
        })

        # Accumulate category stats
        if category_name not in category_stats:
            category_stats[category_name] = {"skills_count": 0, "attainment_sum": 0.0}
        category_stats[category_name]["skills_count"] += 1
        category_stats[category_name]["attainment_sum"] += attainment_pct

        total_attainment_sum += attainment_pct
        total_skills += 1

    categories_list = [
        {
            "category_name": cat_name,
            "skills_count": stats["skills_count"],
            "avg_attainment_pct": round(
                stats["attainment_sum"] / stats["skills_count"], 1
            ) if stats["skills_count"] > 0 else 0.0,
        }
        for cat_name, stats in sorted(category_stats.items())
    ]

    overall_attainment_pct = round(
        total_attainment_sum / total_skills, 1
    ) if total_skills > 0 else 0.0

    return {
        "skills": skills_list,
        "categories": categories_list,
        "overall_attainment_pct": overall_attainment_pct,
    }


# ---------------------------------------------------------------------------
# ai_tag_content_skills
# ---------------------------------------------------------------------------

async def ai_tag_content_skills(
    content_item_id: uuid.UUID,
    tenant_id: uuid.UUID,
    extracted_text: str,
    db: AsyncSession,
    session_factory,
    redis=None,
) -> list[dict]:
    """
    Auto-tag a content item with skills using LiteLLM (gpt-4o-mini).

    1. Fetch all active skills for the tenant.
    2. If none exist, return [].
    3. Build prompt and call AIClient.complete().
    4. Parse JSON response.
    5. Upsert ContentSkillTag rows with source='ai'.
    6. Return [{skill_id, skill_name, confidence}].
    """
    # --- fetch active skills ---
    skills_result = await db.execute(
        select(Skill)
        .where(Skill.tenant_id == tenant_id)
        .where(Skill.is_archived == False)
        .order_by(Skill.name.asc())
    )
    all_skills = skills_result.scalars().all()

    if not all_skills:
        log.info("ai_tag_skills_no_skills", tenant_id=str(tenant_id))
        return []

    # Build skill list for the prompt (id + name so model can return ids directly)
    skill_lookup: dict[str, Skill] = {str(s.id): s for s in all_skills}
    skill_list_text = "\n".join(
        f"- {s.id}: {s.name}" + (f" ({s.description})" if s.description else "")
        for s in all_skills
    )

    # Truncate content text to ~4000 chars to stay within token budget
    content_preview = extracted_text[:4000].strip() if extracted_text else ""

    prompt_messages = [
        {
            "role": "system",
            "content": (
                "You are a learning content analyst. "
                "Given a piece of educational content and a skill library, "
                "identify which skills the content teaches or develops. "
                "Be conservative — only tag skills the content genuinely covers. "
                "Return ONLY a JSON array, no prose, no markdown fences."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Content:\n{content_preview}\n\n"
                f"Skill library (id: name):\n{skill_list_text}\n\n"
                "Return a JSON array of objects for each matching skill:\n"
                '[{"skill_id": "<uuid>", "confidence": <0.0-1.0>}]\n'
                "Only include skills the content genuinely teaches. "
                "Omit skills that are tangential or not covered."
            ),
        },
    ]

    from app.services.ai.client import AIClient

    ai_client = AIClient(
        session_factory=session_factory,
        redis=redis,
        tenant_id=str(tenant_id),
        content_item_id=str(content_item_id),
    )

    try:
        response = await ai_client.complete(
            messages=prompt_messages,
            model="gpt-4o-mini",
            task_type="skill_tagging",
            temperature=0.1,
            max_tokens=1000,
        )
        raw_text = response.choices[0].message.content or ""
    except Exception as exc:
        log.error("ai_tag_skills_llm_failed", error=str(exc), content_item_id=str(content_item_id))
        return []

    # --- parse JSON response ---
    tagged: list[dict] = []
    try:
        # Strip markdown fences if model added them despite instructions
        clean = re.sub(r"```(?:json)?", "", raw_text).strip()
        # Extract the first JSON array
        match = re.search(r"\[.*\]", clean, re.DOTALL)
        if not match:
            raise ValueError("No JSON array found in response")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, list):
            raise ValueError("Parsed JSON is not a list")
    except Exception as exc:
        log.error(
            "ai_tag_skills_parse_failed",
            error=str(exc),
            raw=raw_text[:200],
            content_item_id=str(content_item_id),
        )
        return []

    # --- upsert ContentSkillTag rows ---
    now = datetime.now(timezone.utc)
    upserted: list[dict] = []

    for item in parsed:
        if not isinstance(item, dict):
            continue
        skill_id_str = str(item.get("skill_id", "")).strip()
        confidence = float(item.get("confidence", 0.5))

        if skill_id_str not in skill_lookup:
            log.warning(
                "ai_tag_skills_unknown_skill",
                skill_id=skill_id_str,
                content_item_id=str(content_item_id),
            )
            continue

        skill = skill_lookup[skill_id_str]
        confidence = max(0.0, min(1.0, confidence))

        # Upsert: insert or update confidence/source on conflict
        stmt = (
            pg_insert(ContentSkillTag)
            .values(
                id=uuid.uuid4(),
                content_item_id=content_item_id,
                skill_id=skill.id,
                level_id=None,
                source="ai",
                confidence=confidence,
                tagged_by=None,
                created_at=now,
            )
            .on_conflict_do_update(
                constraint="uq_content_skill_tag",
                set_={
                    "source": "ai",
                    "confidence": confidence,
                    "created_at": now,
                },
            )
        )
        await db.execute(stmt)

        upserted.append({
            "skill_id": skill_id_str,
            "skill_name": skill.name,
            "confidence": confidence,
        })

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        log.error("ai_tag_skills_commit_failed", error=str(exc))
        return []

    log.info(
        "ai_tag_skills_complete",
        content_item_id=str(content_item_id),
        tagged_count=len(upserted),
    )
    return upserted


# ---------------------------------------------------------------------------
# get_org_skill_gap_heatmap
# ---------------------------------------------------------------------------

async def get_org_skill_gap_heatmap(
    tenant_id: uuid.UUID,
    db: AsyncSession,
) -> dict:
    """
    Returns heatmap data for the admin Skill Gap Analysis report.

    {
      teams: [team_name],
      skills: [skill_name],
      matrix: [[pct_meeting_target, ...], ...]   # indexed [team_idx][skill_idx]
    }

    For each team × skill cell:
      numerator   = users in team whose current_level_order >= target_level_order
      denominator = users in team who have an active org role with a target for that skill
    """
    # --- fetch all active (non-archived) skills for the tenant ---
    skills_result = await db.execute(
        select(Skill)
        .where(Skill.tenant_id == tenant_id)
        .where(Skill.is_archived == False)
        .order_by(Skill.name.asc())
    )
    skills: list[Skill] = skills_result.scalars().all()

    if not skills:
        return {"teams": [], "skills": [], "matrix": []}

    # --- fetch all teams for the tenant ---
    teams_result = await db.execute(
        select(Team)
        .where(Team.tenant_id == tenant_id)
        .order_by(Team.name.asc())
    )
    teams: list[Team] = teams_result.scalars().all()

    if not teams:
        return {"teams": [], "skills": [s.name for s in skills], "matrix": []}

    skill_ids = [s.id for s in skills]
    skill_index: dict[uuid.UUID, int] = {s.id: i for i, s in enumerate(skills)}
    team_index: dict[uuid.UUID, int] = {t.id: i for i, t in enumerate(teams)}
    n_teams = len(teams)
    n_skills = len(skills)

    # matrix[team_idx][skill_idx] = [met_count, total_count]
    counts: list[list[list[int]]] = [[[0, 0] for _ in range(n_skills)] for _ in range(n_teams)]

    # --- one query: all team members with active org role, skill target, and progress ---
    # Join path:
    #   TeamMember → AxisUser (active_org_role_id) → OrgRoleSkillTarget →
    #   ProficiencyLevel (target) → UserSkillProgress → ProficiencyLevel (current)
    #
    # We only include rows where:
    #   - user is in a team belonging to this tenant
    #   - user has active_org_role_id set
    #   - that role has a skill target for one of our skills
    #   - the skill is not archived

    target_pl = ProficiencyLevel.__table__.alias("target_pl")
    current_pl = ProficiencyLevel.__table__.alias("current_pl")

    from sqlalchemy import and_, column
    from sqlalchemy.orm import aliased

    TargetLevel = aliased(ProficiencyLevel, name="target_level")
    CurrentLevel = aliased(ProficiencyLevel, name="current_level")

    rows_result = await db.execute(
        select(
            TeamMember.team_id,
            OrgRoleSkillTarget.skill_id,
            TargetLevel.level_order.label("target_order"),
            CurrentLevel.level_order.label("current_order"),
        )
        .join(AxisUser, AxisUser.id == TeamMember.user_id)
        .join(OrgRole, OrgRole.id == AxisUser.active_org_role_id)
        .join(OrgRoleSkillTarget, OrgRoleSkillTarget.org_role_id == OrgRole.id)
        .join(TargetLevel, TargetLevel.id == OrgRoleSkillTarget.target_level_id)
        .join(
            UserSkillProgress,
            (UserSkillProgress.user_id == TeamMember.user_id)
            & (UserSkillProgress.skill_id == OrgRoleSkillTarget.skill_id),
        )
        .join(CurrentLevel, CurrentLevel.id == UserSkillProgress.current_level_id)
        .join(Skill, Skill.id == OrgRoleSkillTarget.skill_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.tenant_id == tenant_id)
        .where(Skill.is_archived == False)
        .where(Skill.id.in_(skill_ids))
    )
    data_rows = rows_result.all()

    # Also need denominator: users in team with a target for skill (regardless of progress)
    denom_result = await db.execute(
        select(
            TeamMember.team_id,
            OrgRoleSkillTarget.skill_id,
            func.count(TeamMember.user_id).label("user_count"),
        )
        .join(AxisUser, AxisUser.id == TeamMember.user_id)
        .join(OrgRole, OrgRole.id == AxisUser.active_org_role_id)
        .join(OrgRoleSkillTarget, OrgRoleSkillTarget.org_role_id == OrgRole.id)
        .join(Skill, Skill.id == OrgRoleSkillTarget.skill_id)
        .join(Team, Team.id == TeamMember.team_id)
        .where(Team.tenant_id == tenant_id)
        .where(Skill.is_archived == False)
        .where(Skill.id.in_(skill_ids))
        .group_by(TeamMember.team_id, OrgRoleSkillTarget.skill_id)
    )
    denom_rows = denom_result.all()

    # denominator matrix[team_idx][skill_idx] = total users with that target
    denom: list[list[int]] = [[0] * n_skills for _ in range(n_teams)]
    for team_id, skill_id, user_count in denom_rows:
        t_idx = team_index.get(team_id)
        s_idx = skill_index.get(skill_id)
        if t_idx is not None and s_idx is not None:
            denom[t_idx][s_idx] = user_count

    # numerator: count users meeting target
    numer: list[list[int]] = [[0] * n_skills for _ in range(n_teams)]
    for team_id, skill_id, target_order, current_order in data_rows:
        t_idx = team_index.get(team_id)
        s_idx = skill_index.get(skill_id)
        if t_idx is not None and s_idx is not None:
            if current_order >= target_order:
                numer[t_idx][s_idx] += 1

    # Build matrix: pct_meeting_target (0–100), None if no users have target
    matrix: list[list[float | None]] = []
    for t_idx in range(n_teams):
        row: list[float | None] = []
        for s_idx in range(n_skills):
            total = denom[t_idx][s_idx]
            if total == 0:
                row.append(None)
            else:
                row.append(round((numer[t_idx][s_idx] / total) * 100.0, 1))
        matrix.append(row)

    return {
        "teams": [t.name for t in teams],
        "skills": [s.name for s in skills],
        "matrix": matrix,
    }
