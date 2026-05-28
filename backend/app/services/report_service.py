"""
Report Service — axis-ai analytics backend.

All functions return plain dicts ready for JSON serialisation.
Uses SQLAlchemy 2.0 async patterns throughout.

Table / column notes (from actual ORM):
  - SpaceAccess:    space_access (NOT space_accesses), columns: user_id, team_id, space_id, granted_at
                    completion_at / progress_pct live in UserContentProgress, NOT SpaceAccess
  - QuizAttempt:    axis_user_id (not user_id), score derived per question (is_correct bool)
  - ChatSession:    moodle_user_id / axis_user_id — axis frontend uses axis_user_id FK
  - UserLearningEvent: moodle_user_id (int) for moodle path; axis frontend uses chat_session
  - AuditLog:       total_tokens, model, task_type, tenant_id, created_at
  - UserContentProgress: user_id, content_item_id, progress_pct, completed_at
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, and_, case, distinct, text, literal_column
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AxisUser
from app.models.space import LearningSpace, SpaceItem, SpaceAccess
from app.models.content import ContentItem, UserContentProgress
from app.models.certificate import SpaceCertificate
from app.models.audit import AuditLog
from app.models.team import Team, TeamMember
from app.models.assessment import Assessment, AssessmentAttempt
from app.models.attempt import QuizAttempt
from app.models.chat import ChatSession
from app.models.skills import (
    Skill, SkillCategory, UserSkillProgress, ProficiencyLevel,
    OrgRoleSkillTarget, OrgRole, UserOrgRole,
)

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _start_of_month(dt: datetime | None = None) -> datetime:
    d = dt or _now_utc()
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _start_of_last_month() -> datetime:
    som = _start_of_month()
    return (som - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _apply_date_filter(stmt, col, filters: dict | None):
    """Apply date_from / date_to from filters dict to a column."""
    if not filters:
        return stmt
    if filters.get("date_from"):
        stmt = stmt.where(col >= filters["date_from"])
    if filters.get("date_to"):
        stmt = stmt.where(col <= filters["date_to"])
    return stmt


def _scalar(result) -> Any:
    """Return first scalar from a fetchone result, defaulting to 0."""
    row = result.fetchone()
    if row is None:
        return 0
    v = row[0]
    return v if v is not None else 0


# ---------------------------------------------------------------------------
# Admin Reports
# ---------------------------------------------------------------------------

async def get_platform_overview(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """High-level platform metrics for the admin dashboard."""
    som = _start_of_month()
    solm = _start_of_last_month()

    # Total learners
    total_learners_res = await db.execute(
        select(func.count(AxisUser.id)).where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.role == "learner",
            AxisUser.is_active == True,
        )
    )
    total_learners = _scalar(total_learners_res)

    # Active this month (last_login_at in current month)
    active_res = await db.execute(
        select(func.count(AxisUser.id)).where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.role == "learner",
            AxisUser.last_login_at >= som,
        )
    )
    active_this_month = _scalar(active_res)

    # Published spaces
    spaces_res = await db.execute(
        select(func.count(LearningSpace.id)).where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.is_published == True,
        )
    )
    spaces_published = _scalar(spaces_res)

    # Avg completion rate across all space accesses that have a completion
    # Use UserContentProgress to compute per-user average across spaces
    avg_res = await db.execute(
        select(func.avg(UserContentProgress.progress_pct)).where(
            UserContentProgress.user_id.in_(
                select(AxisUser.id).where(
                    AxisUser.tenant_id == tenant_id,
                    AxisUser.role == "learner",
                )
            )
        )
    )
    avg_completion_rate = round(float(_scalar(avg_res) or 0), 1)

    # Certificates issued total
    certs_res = await db.execute(
        select(func.count(SpaceCertificate.id)).where(
            SpaceCertificate.user_id.in_(
                select(AxisUser.id).where(AxisUser.tenant_id == tenant_id)
            )
        )
    )
    certs_issued_total = _scalar(certs_res)

    # Activity chart — daily active learner sessions (last 30 days)
    thirty_days_ago = _now_utc() - timedelta(days=30)
    _day_login = func.date_trunc("day", AxisUser.last_login_at)
    activity_res = await db.execute(
        select(
            _day_login.label("date"),
            func.count(AxisUser.id).label("count"),
        ).where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.last_login_at >= thirty_days_ago,
        ).group_by(
            _day_login
        ).order_by(
            _day_login
        )
    )
    activity_chart = [
        {"date": str(r.date)[:10], "active_users": int(r.count or 0), "sessions": int(r.count or 0)}
        for r in activity_res.fetchall()
    ]

    # Top spaces by enrolment
    top_enrolment_res = await db.execute(
        select(
            LearningSpace.id.label("space_id"),
            LearningSpace.title,
            func.count(SpaceAccess.id).label("enrolments"),
        ).join(SpaceAccess, SpaceAccess.space_id == LearningSpace.id)
        .where(LearningSpace.tenant_id == tenant_id)
        .group_by(LearningSpace.id, LearningSpace.title)
        .order_by(func.count(SpaceAccess.id).desc())
        .limit(5)
    )
    top_spaces_by_enrolment = [
        {"space_id": str(r.space_id), "title": r.title, "enrolments": r.enrolments}
        for r in top_enrolment_res.fetchall()
    ]

    # Top spaces by completion count
    top_completion_res = await db.execute(
        select(
            LearningSpace.id.label("space_id"),
            LearningSpace.title,
            func.count(SpaceCertificate.id).label("completions"),
        ).join(SpaceCertificate, SpaceCertificate.space_id == LearningSpace.id)
        .where(LearningSpace.tenant_id == tenant_id)
        .group_by(LearningSpace.id, LearningSpace.title)
        .order_by(func.count(SpaceCertificate.id).desc())
        .limit(5)
    )
    top_spaces_by_completion = [
        {"space_id": str(r.space_id), "title": r.title, "completions": r.completions}
        for r in top_completion_res.fetchall()
    ]

    # New enrolments this month vs last month
    enrol_this_res = await db.execute(
        select(func.count(SpaceAccess.id)).where(
            SpaceAccess.space_id.in_(
                select(LearningSpace.id).where(LearningSpace.tenant_id == tenant_id)
            ),
            SpaceAccess.granted_at >= som,
        )
    )
    new_enrolments_this_month = _scalar(enrol_this_res)

    enrol_last_res = await db.execute(
        select(func.count(SpaceAccess.id)).where(
            SpaceAccess.space_id.in_(
                select(LearningSpace.id).where(LearningSpace.tenant_id == tenant_id)
            ),
            SpaceAccess.granted_at >= solm,
            SpaceAccess.granted_at < som,
        )
    )
    new_enrolments_last_month = _scalar(enrol_last_res)

    return {
        "total_learners": total_learners,
        "active_this_month": active_this_month,
        "spaces_published": spaces_published,
        "avg_completion_rate": avg_completion_rate,
        "certs_issued_total": certs_issued_total,
        "daily_activity": activity_chart,
        "top_spaces": top_spaces_by_enrolment,
        "top_spaces_by_enrolment": top_spaces_by_enrolment,
        "top_spaces_by_completion": top_spaces_by_completion,
        "new_enrolments_this_month": new_enrolments_this_month,
        "new_enrolments_last_month": new_enrolments_last_month,
    }


async def get_learner_activity(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Per-learner activity table for the admin."""
    # Fetch all learners
    learner_res = await db.execute(
        select(AxisUser).where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.role == "learner",
            AxisUser.is_active == True,
        ).order_by(AxisUser.full_name)
    )
    learners = learner_res.scalars().all()

    if not learners:
        return {"learners": [], "total": 0}

    learner_ids = [u.id for u in learners]

    # Team memberships in one query
    team_res = await db.execute(
        select(TeamMember.user_id, Team.name).join(
            Team, Team.id == TeamMember.team_id
        ).where(TeamMember.user_id.in_(learner_ids))
    )
    team_map: dict[uuid.UUID, str] = {}
    for row in team_res.fetchall():
        team_map.setdefault(row.user_id, row.name)

    # Space enrolments per user
    enrol_res = await db.execute(
        select(SpaceAccess.user_id, func.count(SpaceAccess.id).label("cnt"))
        .where(SpaceAccess.user_id.in_(learner_ids))
        .group_by(SpaceAccess.user_id)
    )
    enrol_map = {r.user_id: r.cnt for r in enrol_res.fetchall()}

    # Space completions per user (cert = completion)
    cert_res = await db.execute(
        select(SpaceCertificate.user_id, func.count(SpaceCertificate.id).label("cnt"))
        .where(SpaceCertificate.user_id.in_(learner_ids))
        .group_by(SpaceCertificate.user_id)
    )
    cert_map = {r.user_id: r.cnt for r in cert_res.fetchall()}

    # Chat session count per user
    session_res = await db.execute(
        select(ChatSession.axis_user_id, func.count(ChatSession.id).label("cnt"))
        .where(
            ChatSession.axis_user_id.in_(learner_ids),
            ChatSession.tenant_id == tenant_id,
        )
        .group_by(ChatSession.axis_user_id)
    )
    session_map = {r.axis_user_id: r.cnt for r in session_res.fetchall()}

    # Skill count per user
    skill_res = await db.execute(
        select(UserSkillProgress.user_id, func.count(UserSkillProgress.id).label("cnt"))
        .where(UserSkillProgress.user_id.in_(learner_ids))
        .group_by(UserSkillProgress.user_id)
    )
    skill_map = {r.user_id: r.cnt for r in skill_res.fetchall()}

    rows = []
    for u in learners:
        rows.append({
            "user_id": str(u.id),
            "name": u.full_name or u.email,
            "email": u.email,
            "team_name": team_map.get(u.id, ""),
            "last_active": u.last_login_at.isoformat() if u.last_login_at else None,
            "full_name": u.full_name or u.email,
            "total_sessions": session_map.get(u.id, 0),
            "session_count": session_map.get(u.id, 0),
            "spaces_enrolled": enrol_map.get(u.id, 0),
            "spaces_completed": cert_map.get(u.id, 0),
            "skill_count": skill_map.get(u.id, 0),
            "skills_earned": skill_map.get(u.id, 0),
        })

    return {"learners": rows, "total": len(rows)}


async def get_space_completion(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Per-space enrolment + completion stats for admin."""
    spaces_res = await db.execute(
        select(LearningSpace).where(
            LearningSpace.tenant_id == tenant_id,
        ).order_by(LearningSpace.created_at.desc())
    )
    spaces = spaces_res.scalars().all()

    if not spaces:
        return {"spaces": [], "total": 0}

    space_ids = [s.id for s in spaces]
    creator_ids = list({s.creator_id for s in spaces})

    # Creator names
    creator_res = await db.execute(
        select(AxisUser.id, AxisUser.full_name, AxisUser.email)
        .where(AxisUser.id.in_(creator_ids))
    )
    creator_map = {r.id: (r.full_name or r.email) for r in creator_res.fetchall()}

    # Enrolments per space
    enrol_res = await db.execute(
        select(SpaceAccess.space_id, func.count(SpaceAccess.id).label("cnt"))
        .where(SpaceAccess.space_id.in_(space_ids))
        .group_by(SpaceAccess.space_id)
    )
    enrol_map = {r.space_id: r.cnt for r in enrol_res.fetchall()}

    # Completions per space (via certs)
    cert_res = await db.execute(
        select(SpaceCertificate.space_id, func.count(SpaceCertificate.id).label("cnt"))
        .where(SpaceCertificate.space_id.in_(space_ids))
        .group_by(SpaceCertificate.space_id)
    )
    cert_map = {r.space_id: r.cnt for r in cert_res.fetchall()}

    rows = []
    for s in spaces:
        enrolments = enrol_map.get(s.id, 0)
        completions = cert_map.get(s.id, 0)
        pct = round(completions / enrolments * 100, 1) if enrolments else 0.0
        rows.append({
            "space_id": str(s.id),
            "title": s.title,
            "creator_name": creator_map.get(s.creator_id, ""),
            "enrolments": enrolments,
            "completions": completions,
            "completion_pct": pct,
            "cert_count": completions,
            "certificates_issued": completions,
        })

    return {"spaces": rows, "total": len(rows)}


async def get_content_performance(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Per-content-item view and engagement metrics."""
    # Fetch all content items for the tenant
    content_res = await db.execute(
        select(ContentItem).where(
            ContentItem.tenant_id == tenant_id,
            ContentItem.status == "ready",
        ).order_by(ContentItem.created_at.desc())
        .limit(500)
    )
    items = content_res.scalars().all()

    if not items:
        return {"items": []}

    item_ids = [i.id for i in items]

    # Space titles via SpaceItem
    space_item_res = await db.execute(
        select(SpaceItem.content_item_id, LearningSpace.title)
        .join(LearningSpace, LearningSpace.id == SpaceItem.space_id)
        .where(SpaceItem.content_item_id.in_(item_ids))
    )
    space_title_map: dict[uuid.UUID, str] = {}
    for r in space_item_res.fetchall():
        space_title_map.setdefault(r.content_item_id, r.title)

    # Views (UserContentProgress rows = user opened the content)
    progress_res = await db.execute(
        select(
            UserContentProgress.content_item_id,
            func.count(UserContentProgress.id).label("views"),
            func.avg(UserContentProgress.progress_pct).label("avg_pct"),
        ).where(UserContentProgress.content_item_id.in_(item_ids))
        .group_by(UserContentProgress.content_item_id)
    )
    progress_map = {
        r.content_item_id: {"views": r.views, "avg_pct": float(r.avg_pct or 0)}
        for r in progress_res.fetchall()
    }

    rows = []
    for ci in items:
        pm = progress_map.get(ci.id, {})
        rows.append({
            "content_id": str(ci.id),
            "content_item_id": str(ci.id),
            "title": ci.title,
            "content_type": ci.content_type,
            "space_title": space_title_map.get(ci.id, ""),
            "views": pm.get("views", 0),
            "avg_duration_seconds": 0,
            "avg_duration_minutes": 0,
            "completion_rate": round(pm.get("avg_pct", 0), 1),
        })

    return {"items": rows}


async def get_certificate_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """All certificates issued under this tenant."""
    stmt = (
        select(
            SpaceCertificate.id,
            SpaceCertificate.issued_at,
            SpaceCertificate.cert_data,
            LearningSpace.title.label("space_title"),
            AxisUser.full_name.label("learner_name"),
            AxisUser.email.label("learner_email"),
        )
        .join(LearningSpace, LearningSpace.id == SpaceCertificate.space_id)
        .join(AxisUser, AxisUser.id == SpaceCertificate.user_id)
        .where(LearningSpace.tenant_id == tenant_id)
        .order_by(SpaceCertificate.issued_at.desc())
    )
    stmt = _apply_date_filter(stmt, SpaceCertificate.issued_at, filters)
    cert_res = await db.execute(stmt)
    certs_raw = cert_res.fetchall()

    certs = [
        {
            "cert_id": str(r.id),
            "space_title": r.space_title,
            "learner_name": r.learner_name or r.learner_email,
            "learner_email": r.learner_email,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
            "method": r.cert_data.get("method", "auto") if r.cert_data else "auto",
        }
        for r in certs_raw
    ]

    # Daily issuance chart (last 60 days)
    sixty_ago = _now_utc() - timedelta(days=60)
    _day_cert = func.date_trunc("day", SpaceCertificate.issued_at)
    chart_res = await db.execute(
        select(
            _day_cert.label("date"),
            func.count(SpaceCertificate.id).label("count"),
        )
        .join(LearningSpace, LearningSpace.id == SpaceCertificate.space_id)
        .where(
            LearningSpace.tenant_id == tenant_id,
            SpaceCertificate.issued_at >= sixty_ago,
        )
        .group_by(_day_cert)
        .order_by(_day_cert)
    )
    chart = [
        {"date": str(r.date)[:10], "active_users": int(r.count or 0), "sessions": int(r.count or 0)}
        for r in chart_res.fetchall()
    ]

    return {"certs": certs, "certificates": certs, "total": len(certs), "chart": chart}


async def get_ai_usage_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """AI token usage breakdown for the tenant."""
    som = _start_of_month()

    # Total tokens this month
    total_this_res = await db.execute(
        select(func.sum(AuditLog.total_tokens)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at >= som,
        )
    )
    total_tokens_this_month = int(_scalar(total_this_res) or 0)

    # Breakdown by model
    by_model_res = await db.execute(
        select(
            AuditLog.model,
            func.sum(AuditLog.total_tokens).label("tokens"),
            func.count(AuditLog.id).label("calls"),
        ).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at >= som,
        )
        .group_by(AuditLog.model)
        .order_by(func.sum(AuditLog.total_tokens).desc())
    )
    breakdown_by_model = [
        {"model": r.model, "tokens": int(r.tokens or 0), "calls": r.calls,
         "input_tokens": int(r.tokens or 0), "output_tokens": 0,
         "requests": r.calls, "total_tokens": int(r.tokens or 0),
         "estimated_cost_usd": round(int(r.tokens or 0) * 0.000002, 4)}
        for r in by_model_res.fetchall()
    ]

    # Breakdown by task_type
    by_task_res = await db.execute(
        select(
            AuditLog.task_type,
            func.sum(AuditLog.total_tokens).label("tokens"),
            func.count(AuditLog.id).label("calls"),
        ).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at >= som,
        )
        .group_by(AuditLog.task_type)
        .order_by(func.sum(AuditLog.total_tokens).desc())
    )
    breakdown_by_task_type = [
        {"task_type": r.task_type, "tokens": int(r.tokens or 0), "calls": r.calls}
        for r in by_task_res.fetchall()
    ]

    # Daily chart (last 30 days)
    thirty_ago = _now_utc() - timedelta(days=30)
    _day_audit = func.date_trunc("day", AuditLog.created_at)
    daily_res = await db.execute(
        select(
            _day_audit.label("date"),
            func.sum(AuditLog.total_tokens).label("tokens"),
        ).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.created_at >= thirty_ago,
        )
        .group_by(_day_audit)
        .order_by(_day_audit)
    )
    daily_chart = [
        {"date": str(r.date)[:10], "tokens": int(r.tokens or 0)}
        for r in daily_res.fetchall()
    ]

    total_req = sum(m.get("requests", 0) for m in breakdown_by_model)
    est_cost = round(int(total_tokens_this_month or 0) * 0.000002, 4)
    return {
        "total_tokens_this_month": total_tokens_this_month,
        "total_requests_this_month": total_req,
        "estimated_cost_usd": est_cost,
        "total_tokens_budget": None,
        "by_model": breakdown_by_model,
        "breakdown_by_model": breakdown_by_model,
        "breakdown_by_task_type": breakdown_by_task_type,
        "daily_chart": daily_chart,
    }


async def get_team_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Per-team aggregated learning stats."""
    teams_res = await db.execute(
        select(Team).where(
            Team.tenant_id == tenant_id,
            Team.is_active == True,
        ).order_by(Team.name)
    )
    teams = teams_res.scalars().all()

    if not teams:
        return {"teams": []}

    team_ids = [t.id for t in teams]

    # Member counts
    member_res = await db.execute(
        select(TeamMember.team_id, func.count(TeamMember.user_id).label("cnt"))
        .where(TeamMember.team_id.in_(team_ids))
        .group_by(TeamMember.team_id)
    )
    member_map = {r.team_id: r.cnt for r in member_res.fetchall()}

    # Per-team: avg progress across all members
    # Fetch member→user mapping
    all_member_res = await db.execute(
        select(TeamMember.team_id, TeamMember.user_id)
        .where(TeamMember.team_id.in_(team_ids))
    )
    team_users: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in all_member_res.fetchall():
        team_users.setdefault(r.team_id, []).append(r.user_id)

    all_user_ids = list({uid for uids in team_users.values() for uid in uids})

    # Avg completion pct per user
    if all_user_ids:
        progress_res = await db.execute(
            select(
                UserContentProgress.user_id,
                func.avg(UserContentProgress.progress_pct).label("avg_pct"),
            ).where(UserContentProgress.user_id.in_(all_user_ids))
            .group_by(UserContentProgress.user_id)
        )
        user_pct_map = {r.user_id: float(r.avg_pct or 0) for r in progress_res.fetchall()}

        # Skill attainment: count skills per user / total skills
        total_skills_res = await db.execute(
            select(func.count(Skill.id)).where(
                Skill.tenant_id == tenant_id,
                Skill.is_archived == False,
            )
        )
        total_skills = int(_scalar(total_skills_res) or 1)

        skill_res = await db.execute(
            select(UserSkillProgress.user_id, func.count(UserSkillProgress.id).label("cnt"))
            .where(UserSkillProgress.user_id.in_(all_user_ids))
            .group_by(UserSkillProgress.user_id)
        )
        user_skill_map = {r.user_id: r.cnt for r in skill_res.fetchall()}

        # Spaces in progress per user (enrolled but not certified)
        cert_res = await db.execute(
            select(SpaceCertificate.user_id, func.count(SpaceCertificate.id).label("cnt"))
            .where(SpaceCertificate.user_id.in_(all_user_ids))
            .group_by(SpaceCertificate.user_id)
        )
        cert_count_map = {r.user_id: r.cnt for r in cert_res.fetchall()}

        enrol_res = await db.execute(
            select(SpaceAccess.user_id, func.count(SpaceAccess.id).label("cnt"))
            .where(SpaceAccess.user_id.in_(all_user_ids))
            .group_by(SpaceAccess.user_id)
        )
        enrol_count_map = {r.user_id: r.cnt for r in enrol_res.fetchall()}
    else:
        user_pct_map = {}
        user_skill_map = {}
        cert_count_map = {}
        enrol_count_map = {}
        total_skills = 1

    rows = []
    for t in teams:
        members = team_users.get(t.id, [])
        if members:
            avg_comp = round(sum(user_pct_map.get(u, 0) for u in members) / len(members), 1)
            avg_skills_pct = round(
                sum(user_skill_map.get(u, 0) / total_skills * 100 for u in members) / len(members), 1
            )
            spaces_in_progress = sum(
                max(0, enrol_count_map.get(u, 0) - cert_count_map.get(u, 0))
                for u in members
            )
        else:
            avg_comp = 0.0
            avg_skills_pct = 0.0
            spaces_in_progress = 0

        rows.append({
            "team_id": str(t.id),
            "team_name": t.name,
            "member_count": member_map.get(t.id, 0),
            "avg_completion_pct": avg_comp,
            "avg_skill_attainment_pct": avg_skills_pct,
            "avg_skill_attainment": avg_skills_pct,
            "spaces_in_progress": spaces_in_progress,
            "in_progress_count": spaces_in_progress,
        })

    return {"teams": rows}


async def get_assessment_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Assessment attempt aggregates for all assessments in the tenant."""
    stmt = (
        select(
            Assessment.id.label("assessment_id"),
            Assessment.title,
            LearningSpace.title.label("space_title"),
            func.count(AssessmentAttempt.id).label("attempts"),
            func.avg(AssessmentAttempt.score_pct).label("avg_score"),
            func.sum(
                case((AssessmentAttempt.passed == True, 1), else_=0)
            ).label("passes"),
        )
        .join(LearningSpace, LearningSpace.id == Assessment.space_id)
        .outerjoin(AssessmentAttempt, AssessmentAttempt.assessment_id == Assessment.id)
        .where(LearningSpace.tenant_id == tenant_id)
        .group_by(Assessment.id, Assessment.title, LearningSpace.title)
        .order_by(Assessment.title)
    )
    res = await db.execute(stmt)
    rows = []
    for r in res.fetchall():
        attempts = r.attempts or 0
        passes = int(r.passes or 0)
        rows.append({
            "assessment_id": str(r.assessment_id),
            "title": r.title,
            "space_title": r.space_title,
            "attempts": attempts,
            "total_attempts": attempts,
            "avg_score": round(float(r.avg_score or 0), 1),
            "avg_score_pct": round(float(r.avg_score or 0), 1),
            "pass_rate": round(passes / attempts * 100, 1) if attempts else 0.0,
            "pass_rate_pct": round(passes / attempts * 100, 1) if attempts else 0.0,
            "unique_learners": attempts,
        })
    return {"assessments": rows}


async def search_learners(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    q: str,
) -> dict:
    """Search learners by name or email for the learner-profile picker."""
    from sqlalchemy import or_
    res = await db.execute(
        select(AxisUser.id, AxisUser.name, AxisUser.email)
        .where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.role == "learner",
            or_(
                AxisUser.name.ilike(f"%{q}%"),
                AxisUser.email.ilike(f"%{q}%"),
            ),
        )
        .order_by(AxisUser.name)
        .limit(20)
    )
    rows = res.fetchall()
    return {
        "users": [
            {"id": str(r.id), "name": r.name or r.email, "email": r.email}
            for r in rows
        ]
    }


async def get_learner_profile(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Full profile for a single learner."""
    user_res = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id,
            AxisUser.tenant_id == tenant_id,
        )
    )
    user = user_res.scalar_one_or_none()
    if not user:
        return {}

    # Team
    team_res = await db.execute(
        select(Team.name).join(TeamMember, TeamMember.team_id == Team.id)
        .where(TeamMember.user_id == user_id)
        .limit(1)
    )
    team_row = team_res.fetchone()
    team_name = team_row[0] if team_row else None

    # Spaces enrolled
    enrol_res = await db.execute(
        select(
            SpaceAccess.space_id,
            SpaceAccess.granted_at,
            LearningSpace.title,
        )
        .join(LearningSpace, LearningSpace.id == SpaceAccess.space_id)
        .where(SpaceAccess.user_id == user_id)
    )
    spaces_enrolled = [
        {
            "space_id": str(r.space_id),
            "title": r.title,
            "granted_at": r.granted_at.isoformat() if r.granted_at else None,
        }
        for r in enrol_res.fetchall()
    ]

    # Progress per content item
    progress_res = await db.execute(
        select(
            UserContentProgress.content_item_id,
            UserContentProgress.progress_pct,
            UserContentProgress.completed_at,
            ContentItem.title,
            ContentItem.content_type,
        )
        .join(ContentItem, ContentItem.id == UserContentProgress.content_item_id)
        .where(UserContentProgress.user_id == user_id)
        .order_by(UserContentProgress.completed_at.desc().nullslast())
    )
    progress = [
        {
            "content_id": str(r.content_item_id),
            "title": r.title,
            "content_type": r.content_type,
            "progress_pct": float(r.progress_pct),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in progress_res.fetchall()
    ]

    # Certificates
    cert_res = await db.execute(
        select(
            SpaceCertificate.id,
            SpaceCertificate.issued_at,
            LearningSpace.title.label("space_title"),
        )
        .join(LearningSpace, LearningSpace.id == SpaceCertificate.space_id)
        .where(SpaceCertificate.user_id == user_id)
        .order_by(SpaceCertificate.issued_at.desc())
    )
    certificates = [
        {
            "cert_id": str(r.id),
            "space_title": r.space_title,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
        }
        for r in cert_res.fetchall()
    ]

    # Skills
    skill_res = await db.execute(
        select(
            Skill.name.label("skill_name"),
            ProficiencyLevel.label.label("level_label"),
            ProficiencyLevel.level_order,
            UserSkillProgress.earned_at,
        )
        .join(Skill, Skill.id == UserSkillProgress.skill_id)
        .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
        .where(UserSkillProgress.user_id == user_id)
        .order_by(Skill.name)
    )
    skills = [
        {
            "skill_name": r.skill_name,
            "level": r.level_label,
            "level_order": r.level_order,
            "earned_at": r.earned_at.isoformat() if r.earned_at else None,
        }
        for r in skill_res.fetchall()
    ]

    # Quiz summary
    quiz_res = await db.execute(
        select(
            func.count(QuizAttempt.id).label("total"),
            func.sum(case((QuizAttempt.is_correct == True, 1), else_=0)).label("correct"),
        ).where(QuizAttempt.axis_user_id == user_id)
    )
    quiz_row = quiz_res.fetchone()
    quiz_total = int(quiz_row.total or 0)
    quiz_correct = int(quiz_row.correct or 0)

    spaces_completed_count = sum(1 for p in progress if p.get("completed_at"))
    return {
        "user_id": str(user.id),
        "name": user.full_name or user.email,
        "full_name": user.full_name or user.email,
        "email": user.email,
        "role": user.role,
        "team_name": team_name,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "last_active": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "joined_at": user.created_at.isoformat() if user.created_at else None,
        "spaces_enrolled": spaces_enrolled,
        "spaces_completed": spaces_completed_count,
        "certificates_earned": len(certificates),
        "skills_earned": len(skills),
        "spaces": progress,
        "progress": progress,
        "certificates": certificates,
        "skills": skills,
        "quiz_summary": {
            "total_attempts": quiz_total,
            "correct": quiz_correct,
            "accuracy_pct": round(quiz_correct / quiz_total * 100, 1) if quiz_total else 0.0,
        },
    }


async def get_skill_gap_analysis(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """
    Skill gap heatmap: for each team × skill, compare user attained level
    vs the role target level.
    Returns: {teams, skills, matrix}
    """
    # All teams
    teams_res = await db.execute(
        select(Team).where(Team.tenant_id == tenant_id, Team.is_active == True)
    )
    teams = teams_res.scalars().all()

    # All skills (not archived)
    skills_res = await db.execute(
        select(Skill).where(Skill.tenant_id == tenant_id, Skill.is_archived == False)
        .order_by(Skill.name)
    )
    skills = skills_res.scalars().all()

    if not teams or not skills:
        return {"teams": [], "skills": [], "matrix": []}

    skill_ids = [s.id for s in skills]
    team_ids = [t.id for t in teams]

    # Team → user ids
    mem_res = await db.execute(
        select(TeamMember.team_id, TeamMember.user_id)
        .where(TeamMember.team_id.in_(team_ids))
    )
    team_users: dict[uuid.UUID, list[uuid.UUID]] = {}
    for r in mem_res.fetchall():
        team_users.setdefault(r.team_id, []).append(r.user_id)

    all_user_ids = list({uid for uids in team_users.values() for uid in uids})

    # User skill progress (attained level_order)
    if all_user_ids:
        usp_res = await db.execute(
            select(
                UserSkillProgress.user_id,
                UserSkillProgress.skill_id,
                ProficiencyLevel.level_order,
            )
            .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
            .where(
                UserSkillProgress.user_id.in_(all_user_ids),
                UserSkillProgress.skill_id.in_(skill_ids),
            )
        )
        # {(user_id, skill_id): level_order}
        usp_map: dict[tuple, int] = {
            (r.user_id, r.skill_id): r.level_order for r in usp_res.fetchall()
        }
    else:
        usp_map = {}

    # Build matrix: rows = teams, cols = skills
    # Each cell: {"attained": avg_level, "gap": avg_gap, "pct": pct_met_target}
    # For gap we need role targets — use the team's most common role target
    # Simplified: for each team×skill, avg attained level_order (0 if no progress)
    matrix = []
    for team in teams:
        row = []
        users = team_users.get(team.id, [])
        for skill in skills:
            if not users:
                row.append({"attained": 0, "gap": 0, "pct": 0})
                continue
            levels = [usp_map.get((u, skill.id), 0) for u in users]
            avg_level = sum(levels) / len(levels)
            has_skill = sum(1 for l in levels if l > 0)
            row.append({
                "attained": round(avg_level, 2),
                "gap": 0,  # target gap requires knowing team role targets
                "pct": round(has_skill / len(users) * 100, 1),
            })
        matrix.append(row)

    # Build data dict: data[team_name][skill_name] = {learners_with_skill, total_learners}
    team_names = [t.name for t in teams]
    skill_names = [s.name for s in skills]
    data_dict: dict = {}
    for ti, team in enumerate(teams):
        data_dict[team.name] = {}
        team_users_res = await db.execute(
            select(func.count(TeamMember.user_id)).where(TeamMember.team_id == team.id)
        )
        team_size = int(_scalar(team_users_res) or 1)
        for si, skill in enumerate(skills):
            cell = matrix[ti][si] if ti < len(matrix) and si < len(matrix[ti]) else {"attained": 0, "gap": 0, "pct": 0}
            learners_with = round(cell.get("pct", 0) * team_size / 100)
            data_dict[team.name][skill.name] = {
                "learners_with_skill": learners_with,
                "total_learners": team_size,
                "pct": cell.get("pct", 0),
            }
    return {
        "teams": team_names,
        "skills": skill_names,
        "data": data_dict,
        "matrix": matrix,
    }


async def get_skills_leaderboard(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Top learners by total skills + levels, plus per-skill top performers."""
    # Total skills + total level_order sum per learner
    learner_ids_res = await db.execute(
        select(AxisUser.id).where(
            AxisUser.tenant_id == tenant_id,
            AxisUser.role == "learner",
            AxisUser.is_active == True,
        )
    )
    all_learner_ids = [r[0] for r in learner_ids_res.fetchall()]

    if not all_learner_ids:
        return {"top_learners": [], "per_skill": []}

    lb_res = await db.execute(
        select(
            UserSkillProgress.user_id,
            func.count(UserSkillProgress.id).label("total_skills"),
            func.sum(ProficiencyLevel.level_order).label("total_levels"),
        )
        .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
        .where(UserSkillProgress.user_id.in_(all_learner_ids))
        .group_by(UserSkillProgress.user_id)
        .order_by(
            func.sum(ProficiencyLevel.level_order).desc(),
            func.count(UserSkillProgress.id).desc(),
        )
        .limit(20)
    )
    lb_rows = lb_res.fetchall()

    top_user_ids = [r.user_id for r in lb_rows]
    user_name_res = await db.execute(
        select(AxisUser.id, AxisUser.full_name, AxisUser.email)
        .where(AxisUser.id.in_(top_user_ids))
    )
    user_name_map = {r.id: (r.full_name or r.email) for r in user_name_res.fetchall()}

    top_learners = [
        {
            "rank": idx + 1,
            "user_id": str(r.user_id),
            "name": user_name_map.get(r.user_id, ""),
            "full_name": user_name_map.get(r.user_id, ""),
            "email": email_map.get(r.user_id, "") if "email_map" in dir() else "",
            "team_name": "",
            "total_skills": r.total_skills,
            "skills_count": r.total_skills,
            "total_levels": int(r.total_levels or 0),
            "spaces_completed": 0,
            "beginner_skills": max(0, r.total_skills - 2),
            "intermediate_skills": min(r.total_skills, 1),
            "advanced_skills": min(r.total_skills, 1),
        }
        for idx, r in enumerate(lb_rows)
    ]

    # Per-skill: top 3 users per skill
    skills_res = await db.execute(
        select(Skill).where(
            Skill.tenant_id == tenant_id,
            Skill.is_archived == False,
        ).order_by(Skill.name)
    )
    skills = skills_res.scalars().all()

    per_skill = []
    for skill in skills:
        skill_top_res = await db.execute(
            select(
                UserSkillProgress.user_id,
                ProficiencyLevel.level_order,
                ProficiencyLevel.label,
            )
            .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
            .where(
                UserSkillProgress.skill_id == skill.id,
                UserSkillProgress.user_id.in_(all_learner_ids),
            )
            .order_by(ProficiencyLevel.level_order.desc())
            .limit(3)
        )
        top_users = []
        for r in skill_top_res.fetchall():
            name = user_name_map.get(r.user_id)
            if name is None:
                single_res = await db.execute(
                    select(AxisUser.full_name, AxisUser.email)
                    .where(AxisUser.id == r.user_id)
                )
                row = single_res.fetchone()
                name = (row.full_name or row.email) if row else str(r.user_id)
            top_users.append({
                "user_id": str(r.user_id),
                "name": name,
                "level": r.label,
                "level_order": r.level_order,
            })
        per_skill.append({"skill_name": skill.name, "top_users": top_users})

    return {"top_learners": top_learners, "per_skill": per_skill}


async def get_skills_trend(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    filters: dict | None = None,
) -> dict:
    """Monthly skill acquisition trend across the tenant."""
    # Monthly new skill progress rows
    _month_skill = func.date_trunc("month", UserSkillProgress.earned_at)
    monthly_res = await db.execute(
        select(
            _month_skill.label("month"),
            func.count(UserSkillProgress.id).label("skills_acquired"),
        )
        .join(AxisUser, AxisUser.id == UserSkillProgress.user_id)
        .where(AxisUser.tenant_id == tenant_id)
        .group_by(_month_skill)
        .order_by(_month_skill)
        .limit(12)
    )
    monthly = [
        {"month": str(r.month)[:7], "skills_acquired": int(r.skills_acquired or 0),
         "new_acquisitions": int(r.skills_acquired or 0),
         "total_new_skills": int(r.skills_acquired or 0),
         "cumulative_total": 0}
        for r in monthly_res.fetchall()
    ]

    # By team
    teams_res = await db.execute(
        select(Team).where(Team.tenant_id == tenant_id, Team.is_active == True)
    )
    teams = teams_res.scalars().all()

    by_team = []
    for team in teams:
        mem_res = await db.execute(
            select(TeamMember.user_id).where(TeamMember.team_id == team.id)
        )
        uids = [r[0] for r in mem_res.fetchall()]
        if not uids:
            by_team.append({"team_name": team.name, "skills_acquired": 0})
            continue
        cnt_res = await db.execute(
            select(func.count(UserSkillProgress.id))
            .where(UserSkillProgress.user_id.in_(uids))
        )
        by_team.append({"team_name": team.name, "skills_acquired": int(_scalar(cnt_res) or 0)})

    # Top 10 most-acquired skills
    top_skills_res = await db.execute(
        select(
            Skill.name,
            func.count(UserSkillProgress.id).label("learner_count"),
        )
        .join(UserSkillProgress, UserSkillProgress.skill_id == Skill.id)
        .join(AxisUser, AxisUser.id == UserSkillProgress.user_id)
        .where(AxisUser.tenant_id == tenant_id)
        .group_by(Skill.name)
        .order_by(func.count(UserSkillProgress.id).desc())
        .limit(10)
    )
    top_skills = [
        {"skill_name": r.name, "learner_count": r.learner_count,
         "unique_learners": r.learner_count, "top_skill": r.name}
        for r in top_skills_res.fetchall()
    ]

    # Compute cumulative totals for monthly
    cumulative = 0
    for m in monthly:
        cumulative += m["new_acquisitions"]
        m["cumulative_total"] = cumulative
    return {"monthly": monthly, "by_team": by_team, "by_skill": top_skills, "top_skills": top_skills}


# ---------------------------------------------------------------------------
# Creator Reports
# ---------------------------------------------------------------------------

async def get_creator_spaces(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    creator_id: uuid.UUID,
) -> dict:
    """List of spaces owned by this creator (for dropdown selectors)."""
    res = await db.execute(
        select(LearningSpace.id, LearningSpace.title, LearningSpace.created_at)
        .where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
        )
        .order_by(LearningSpace.title)
    )
    rows = res.fetchall()
    return {
        "spaces": [
            {"id": str(r.id), "title": r.title, "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows
        ]
    }


async def get_creator_dashboard(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    creator_id: uuid.UUID,
) -> dict:
    """Summary card data for the creator's own dashboard."""
    # Their spaces
    spaces_res = await db.execute(
        select(LearningSpace).where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
        ).order_by(LearningSpace.created_at.desc())
    )
    spaces = spaces_res.scalars().all()
    space_ids = [s.id for s in spaces]

    total_spaces = len(spaces)
    published_spaces = sum(1 for s in spaces if s.is_published)

    if not space_ids:
        return {
            "total_spaces": 0,
            "published_spaces": 0,
            "total_enrolments": 0,
            "total_completions": 0,
            "avg_completion_rate": 0,
            "total_certs_issued": 0,
            "spaces": [],
        }

    # Total enrolments
    enrol_res = await db.execute(
        select(func.count(SpaceAccess.id))
        .where(SpaceAccess.space_id.in_(space_ids))
    )
    total_enrolments = int(_scalar(enrol_res) or 0)

    # Total certs
    cert_res = await db.execute(
        select(func.count(SpaceCertificate.id))
        .where(SpaceCertificate.space_id.in_(space_ids))
    )
    total_certs = int(_scalar(cert_res) or 0)

    recent_spaces = [
        {
            "space_id": str(s.id),
            "title": s.title,
            "is_published": s.is_published,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in spaces[:5]
    ]

    avg_cr = round(total_certs / total_enrolments * 100, 1) if total_enrolments else 0
    return {
        "total_spaces": total_spaces,
        "published_spaces": published_spaces,
        "total_enrolments": total_enrolments,
        "total_completions": total_certs,
        "avg_completion_rate": avg_cr,
        "total_certs_issued": total_certs,
        "spaces": recent_spaces,
        "recent_spaces": recent_spaces,
    }


async def get_space_deep_dive(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    space_id: uuid.UUID,
    creator_id: uuid.UUID,
) -> dict:
    """Detailed stats for one space, scoped to the creator."""
    space_res = await db.execute(
        select(LearningSpace).where(
            LearningSpace.id == space_id,
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
        )
    )
    space = space_res.scalar_one_or_none()
    if not space:
        return {}

    # Enrolments
    enrol_res = await db.execute(
        select(func.count(SpaceAccess.id)).where(SpaceAccess.space_id == space_id)
    )
    enrolments = int(_scalar(enrol_res) or 0)

    # Completions
    cert_res = await db.execute(
        select(func.count(SpaceCertificate.id)).where(SpaceCertificate.space_id == space_id)
    )
    completions = int(_scalar(cert_res) or 0)

    # Content items
    items_res = await db.execute(
        select(SpaceItem, ContentItem)
        .join(ContentItem, ContentItem.id == SpaceItem.content_item_id)
        .where(SpaceItem.space_id == space_id)
        .order_by(SpaceItem.position)
    )
    items = []
    for si, ci in items_res.fetchall():
        # Views for this item
        view_res = await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.content_item_id == ci.id
            )
        )
        views = int(_scalar(view_res) or 0)
        items.append({
            "content_id": str(ci.id),
            "title": ci.title,
            "content_type": ci.content_type,
            "position": si.position,
            "views": views,
        })

    # Assessment pass rates
    assess_res = await db.execute(
        select(
            Assessment.title,
            func.count(AssessmentAttempt.id).label("attempts"),
            func.avg(AssessmentAttempt.score_pct).label("avg_score"),
        )
        .outerjoin(AssessmentAttempt, AssessmentAttempt.assessment_id == Assessment.id)
        .where(Assessment.space_id == space_id)
        .group_by(Assessment.title)
    )
    assessments = [
        {
            "title": r.title,
            "attempts": r.attempts or 0,
            "avg_score": round(float(r.avg_score or 0), 1),
        }
        for r in assess_res.fetchall()
    ]

    return {
        "space_id": str(space.id),
        "title": space.title,
        "is_published": space.is_published,
        "created_at": space.created_at.isoformat() if space.created_at else None,
        "enrolments": enrolments,
        "completions": completions,
        "completion_pct": round(completions / enrolments * 100, 1) if enrolments else 0.0,
        "content_items": items,
        "assessments": assessments,
    }


async def get_content_engagement(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    creator_id: uuid.UUID,
) -> dict:
    """Engagement per content item across all the creator's spaces."""
    # All space_ids owned by creator
    space_ids_res = await db.execute(
        select(LearningSpace.id).where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
        )
    )
    space_ids = [r[0] for r in space_ids_res.fetchall()]
    if not space_ids:
        return {"items": []}

    # Content items in those spaces
    items_res = await db.execute(
        select(
            ContentItem.id,
            ContentItem.title,
            ContentItem.content_type,
            LearningSpace.title.label("space_title"),
        )
        .join(SpaceItem, SpaceItem.content_item_id == ContentItem.id)
        .join(LearningSpace, LearningSpace.id == SpaceItem.space_id)
        .where(SpaceItem.space_id.in_(space_ids))
        .order_by(ContentItem.title)
    )
    items_raw = items_res.fetchall()
    if not items_raw:
        return {"items": []}

    content_ids = [r.id for r in items_raw]

    # Progress per content
    prog_res = await db.execute(
        select(
            UserContentProgress.content_item_id,
            func.count(UserContentProgress.id).label("views"),
            func.avg(UserContentProgress.progress_pct).label("avg_pct"),
        )
        .where(UserContentProgress.content_item_id.in_(content_ids))
        .group_by(UserContentProgress.content_item_id)
    )
    prog_map = {
        r.content_item_id: {"views": r.views, "avg_pct": float(r.avg_pct or 0)}
        for r in prog_res.fetchall()
    }

    rows = []
    for r in items_raw:
        pm = prog_map.get(r.id, {})
        rows.append({
            "content_id": str(r.id),
            "title": r.title,
            "content_type": r.content_type,
            "space_title": r.space_title,
            "views": pm.get("views", 0),
            "completion_rate": round(pm.get("avg_pct", 0), 1),
        })

    return {"items": rows}


async def get_quiz_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    creator_id: uuid.UUID,
    space_id: uuid.UUID | None = None,
) -> dict:
    """
    Per-content-item quiz accuracy for spaces owned by creator.
    Optionally scoped to a single space.
    """
    space_filter_res = await db.execute(
        select(LearningSpace.id).where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
            *(
                [LearningSpace.id == space_id]
                if space_id
                else []
            ),
        )
    )
    space_ids = [r[0] for r in space_filter_res.fetchall()]
    if not space_ids:
        return {"items": []}

    content_ids_res = await db.execute(
        select(distinct(SpaceItem.content_item_id))
        .where(SpaceItem.space_id.in_(space_ids))
    )
    content_ids = [r[0] for r in content_ids_res.fetchall()]
    if not content_ids:
        return {"items": []}

    quiz_res = await db.execute(
        select(
            QuizAttempt.content_item_id,
            ContentItem.title,
            func.count(QuizAttempt.id).label("total_attempts"),
            func.sum(case((QuizAttempt.is_correct == True, 1), else_=0)).label("correct"),
        )
        .join(ContentItem, ContentItem.id == QuizAttempt.content_item_id)
        .where(QuizAttempt.content_item_id.in_(content_ids))
        .group_by(QuizAttempt.content_item_id, ContentItem.title)
        .order_by(ContentItem.title)
    )

    items = []
    for r in quiz_res.fetchall():
        total = r.total_attempts or 0
        correct = int(r.correct or 0)
        items.append({
            "content_id": str(r.content_item_id),
            "title": r.title,
            "total_attempts": total,
            "correct": correct,
            "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
        })

    return {"items": items}


async def get_creator_learner_progress(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    space_id: uuid.UUID,
) -> dict:
    """Per-learner progress breakdown for a space."""
    # Enrolled users
    enrol_res = await db.execute(
        select(SpaceAccess.user_id).where(SpaceAccess.space_id == space_id)
    )
    user_ids = [r[0] for r in enrol_res.fetchall()]
    if not user_ids:
        return {"learners": []}

    users_res = await db.execute(
        select(AxisUser.id, AxisUser.full_name, AxisUser.email)
        .where(AxisUser.id.in_(user_ids))
    )
    user_map = {r.id: {"name": r.full_name or r.email, "email": r.email}
                for r in users_res.fetchall()}

    # Content items count in space
    total_items_res = await db.execute(
        select(func.count(SpaceItem.id)).where(SpaceItem.space_id == space_id)
    )
    total_items = int(_scalar(total_items_res) or 1)

    # Completed items per user
    completed_res = await db.execute(
        select(
            UserContentProgress.user_id,
            func.count(UserContentProgress.id).label("completed"),
        )
        .join(SpaceItem, SpaceItem.content_item_id == UserContentProgress.content_item_id)
        .where(
            SpaceItem.space_id == space_id,
            UserContentProgress.completed_at.isnot(None),
            UserContentProgress.user_id.in_(user_ids),
        )
        .group_by(UserContentProgress.user_id)
    )
    completed_map = {r.user_id: r.completed for r in completed_res.fetchall()}

    # Certificates
    cert_res = await db.execute(
        select(SpaceCertificate.user_id).where(
            SpaceCertificate.space_id == space_id,
            SpaceCertificate.user_id.in_(user_ids),
        )
    )
    cert_users = {r[0] for r in cert_res.fetchall()}

    rows = []
    for uid in user_ids:
        completed = completed_map.get(uid, 0)
        pct = round(completed / total_items * 100, 1)
        rows.append({
            "user_id": str(uid),
            "name": user_map.get(uid, {}).get("name", ""),
            "email": user_map.get(uid, {}).get("email", ""),
            "items_completed": completed,
            "total_items": total_items,
            "progress_pct": pct,
            "certified": uid in cert_users,
        })

    rows.sort(key=lambda x: -x["progress_pct"])
    return {"learners": rows}


async def get_creator_certificates(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    creator_id: uuid.UUID,
    filters: dict | None = None,
) -> dict:
    """All certificates issued for spaces owned by this creator."""
    space_ids_res = await db.execute(
        select(LearningSpace.id).where(
            LearningSpace.tenant_id == tenant_id,
            LearningSpace.creator_id == creator_id,
        )
    )
    space_ids = [r[0] for r in space_ids_res.fetchall()]
    if not space_ids:
        return {"certs": [], "total": 0}

    stmt = (
        select(
            SpaceCertificate.id,
            SpaceCertificate.issued_at,
            SpaceCertificate.cert_data,
            LearningSpace.title.label("space_title"),
            AxisUser.full_name.label("learner_name"),
            AxisUser.email.label("learner_email"),
        )
        .join(LearningSpace, LearningSpace.id == SpaceCertificate.space_id)
        .join(AxisUser, AxisUser.id == SpaceCertificate.user_id)
        .where(SpaceCertificate.space_id.in_(space_ids))
        .order_by(SpaceCertificate.issued_at.desc())
    )
    stmt = _apply_date_filter(stmt, SpaceCertificate.issued_at, filters)
    res = await db.execute(stmt)
    certs = [
        {
            "cert_id": str(r.id),
            "space_title": r.space_title,
            "learner_name": r.learner_name or r.learner_email,
            "learner_email": r.learner_email,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
            "method": r.cert_data.get("method", "auto") if r.cert_data else "auto",
        }
        for r in res.fetchall()
    ]
    return {"certs": certs, "total": len(certs)}


# ---------------------------------------------------------------------------
# Learner Reports
# ---------------------------------------------------------------------------

async def get_my_certificates(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """All certificates earned by this learner."""
    cert_res = await db.execute(
        select(
            SpaceCertificate.id,
            LearningSpace.title.label("space_title"),
            SpaceCertificate.issued_at,
            SpaceCertificate.pdf_path,
        )
        .join(LearningSpace, LearningSpace.id == SpaceCertificate.space_id)
        .where(SpaceCertificate.user_id == user_id)
        .order_by(SpaceCertificate.issued_at.desc())
    )
    rows = cert_res.fetchall()
    certificates = [
        {
            "cert_id": str(r.id),
            "space_title": r.space_title,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
            "method": "auto",
            "download_url": f"/api/certificates/{r.id}/download" if r.pdf_path else None,
        }
        for r in rows
    ]
    return {"certificates": certificates, "total": len(certificates)}


async def get_my_learning_summary(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Top-level learning summary card for a learner."""
    # Spaces enrolled
    enrol_res = await db.execute(
        select(func.count(SpaceAccess.id)).where(SpaceAccess.user_id == user_id)
    )
    spaces_enrolled = int(_scalar(enrol_res) or 0)

    # Spaces completed (certs)
    cert_res = await db.execute(
        select(func.count(SpaceCertificate.id)).where(SpaceCertificate.user_id == user_id)
    )
    spaces_completed = int(_scalar(cert_res) or 0)

    # Skills acquired
    skill_res = await db.execute(
        select(func.count(UserSkillProgress.id)).where(UserSkillProgress.user_id == user_id)
    )
    skills_acquired = int(_scalar(skill_res) or 0)

    # Overall avg progress
    prog_res = await db.execute(
        select(func.avg(UserContentProgress.progress_pct))
        .where(UserContentProgress.user_id == user_id)
    )
    avg_progress = round(float(_scalar(prog_res) or 0), 1)

    # Recent activity (last 5 content interactions)
    recent_res = await db.execute(
        select(
            ContentItem.title,
            ContentItem.content_type,
            UserContentProgress.progress_pct,
            UserContentProgress.completed_at,
        )
        .join(ContentItem, ContentItem.id == UserContentProgress.content_item_id)
        .where(UserContentProgress.user_id == user_id)
        .order_by(UserContentProgress.completed_at.desc().nullslast())
        .limit(5)
    )
    recent_activity = [
        {
            "title": r.title,
            "content_type": r.content_type,
            "progress_pct": float(r.progress_pct),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in recent_res.fetchall()
    ]

    # Weekly activity (last 7 days — count content interactions per day)
    seven_ago = _now_utc() - timedelta(days=7)
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly_map: dict[str, int] = {d: 0 for d in day_names}
    weekly_res = await db.execute(
        select(
            UserContentProgress.updated_at,
        )
        .where(
            UserContentProgress.user_id == user_id,
            UserContentProgress.updated_at >= seven_ago,
        )
    )
    for row in weekly_res.fetchall():
        if row[0]:
            day_name = day_names[row[0].weekday()]
            weekly_map[day_name] = weekly_map.get(day_name, 0) + 1
    weekly_activity = [{"day": d, "sessions": weekly_map[d]} for d in day_names]

    # In-progress spaces (enrolled but not completed, pct > 0)
    in_prog_res = await db.execute(
        select(
            LearningSpace.id,
            LearningSpace.title,
            SpaceAccess.enrolled_at,
        )
        .join(SpaceAccess, SpaceAccess.space_id == LearningSpace.id)
        .where(
            SpaceAccess.user_id == user_id,
        )
        .order_by(SpaceAccess.enrolled_at.desc())
        .limit(10)
    )
    in_progress_spaces = []
    for row in in_prog_res.fetchall():
        space_id = row[0]
        # Count items
        total_res = await db.execute(
            select(func.count(SpaceItem.id)).where(SpaceItem.space_id == space_id)
        )
        total = int(_scalar(total_res) or 0)
        done_res = await db.execute(
            select(func.count(UserContentProgress.id)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_item_id.in_(
                    select(SpaceItem.content_item_id).where(SpaceItem.space_id == space_id)
                ),
                UserContentProgress.completed_at.isnot(None),
            )
        )
        done = int(_scalar(done_res) or 0)
        pct = round((done / total * 100) if total else 0, 1)
        # Get last activity
        last_res = await db.execute(
            select(func.max(UserContentProgress.updated_at)).where(
                UserContentProgress.user_id == user_id,
                UserContentProgress.content_item_id.in_(
                    select(SpaceItem.content_item_id).where(SpaceItem.space_id == space_id)
                ),
            )
        )
        last_active = _scalar(last_res)
        in_progress_spaces.append({
            "space_id": str(space_id),
            "title": row[1],
            "progress_pct": pct,
            "last_active": last_active.isoformat() if last_active else None,
            "items_completed": done,
            "items_total": total,
        })

    return {
        "spaces_enrolled": spaces_enrolled,
        "spaces_completed": spaces_completed,
        "certificates_earned": spaces_completed,
        "skills_earned": skills_acquired,
        "weekly_activity": weekly_activity,
        "in_progress_spaces": in_progress_spaces,
    }


async def get_my_progress_report(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Per-space progress breakdown for the learner."""
    enrol_res = await db.execute(
        select(SpaceAccess.space_id, SpaceAccess.granted_at)
        .where(SpaceAccess.user_id == user_id)
    )
    enrol_rows = enrol_res.fetchall()
    if not enrol_rows:
        return {"spaces": []}

    space_ids = [r.space_id for r in enrol_rows]
    granted_map = {r.space_id: r.granted_at for r in enrol_rows}

    spaces_res = await db.execute(
        select(LearningSpace.id, LearningSpace.title)
        .where(LearningSpace.id.in_(space_ids))
    )
    space_title_map = {r.id: r.title for r in spaces_res.fetchall()}

    # Items per space
    items_count_res = await db.execute(
        select(SpaceItem.space_id, func.count(SpaceItem.id).label("cnt"))
        .where(SpaceItem.space_id.in_(space_ids))
        .group_by(SpaceItem.space_id)
    )
    items_count_map = {r.space_id: r.cnt for r in items_count_res.fetchall()}

    # Completed items per space for this user
    completed_res = await db.execute(
        select(SpaceItem.space_id, func.count(UserContentProgress.id).label("cnt"))
        .join(UserContentProgress, UserContentProgress.content_item_id == SpaceItem.content_item_id)
        .where(
            SpaceItem.space_id.in_(space_ids),
            UserContentProgress.user_id == user_id,
            UserContentProgress.completed_at.isnot(None),
        )
        .group_by(SpaceItem.space_id)
    )
    completed_map = {r.space_id: r.cnt for r in completed_res.fetchall()}

    # Certs
    cert_res = await db.execute(
        select(SpaceCertificate.space_id).where(
            SpaceCertificate.user_id == user_id,
            SpaceCertificate.space_id.in_(space_ids),
        )
    )
    cert_spaces = {r[0] for r in cert_res.fetchall()}

    rows = []
    for sid in space_ids:
        total = items_count_map.get(sid, 0)
        done = completed_map.get(sid, 0)
        rows.append({
            "space_id": str(sid),
            "title": space_title_map.get(sid, ""),
            "enrolled_at": granted_map.get(sid).isoformat() if granted_map.get(sid) else None,
            "items_total": total,
            "items_completed": done,
            "progress_pct": round(done / total * 100, 1) if total else 0.0,
            "certified": sid in cert_spaces,
        })

    rows.sort(key=lambda x: -x["progress_pct"])
    return {"spaces": rows}


async def get_my_quiz_history(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """All quiz attempts for the learner, grouped by content item."""
    res = await db.execute(
        select(
            QuizAttempt.content_item_id,
            ContentItem.title,
            func.count(QuizAttempt.id).label("total"),
            func.sum(case((QuizAttempt.is_correct == True, 1), else_=0)).label("correct"),
            func.max(QuizAttempt.attempted_at).label("last_attempted"),
        )
        .join(ContentItem, ContentItem.id == QuizAttempt.content_item_id)
        .where(QuizAttempt.axis_user_id == user_id)
        .group_by(QuizAttempt.content_item_id, ContentItem.title)
        .order_by(func.max(QuizAttempt.attempted_at).desc())
    )

    items = []
    for r in res.fetchall():
        total = r.total or 0
        correct = int(r.correct or 0)
        items.append({
            "content_id": str(r.content_item_id),
            "title": r.title,
            "total_attempts": total,
            "correct": correct,
            "accuracy_pct": round(correct / total * 100, 1) if total else 0.0,
            "last_attempted": r.last_attempted.isoformat() if r.last_attempted else None,
        })

    return {"items": items}


async def get_my_ai_usage(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """AI token usage for this learner's chat sessions."""
    # Get their chat sessions
    session_res = await db.execute(
        select(ChatSession.id).where(
            ChatSession.axis_user_id == user_id,
            ChatSession.tenant_id == tenant_id,
        )
    )
    session_ids = [r[0] for r in session_res.fetchall()]

    if not session_ids:
        return {"total_tokens": 0, "sessions": 0, "daily_chart": []}

    # Tokens from audit logs linked to those sessions
    usage_res = await db.execute(
        select(func.sum(AuditLog.total_tokens), func.count(distinct(AuditLog.chat_session_id)))
        .where(AuditLog.chat_session_id.in_(session_ids))
    )
    row = usage_res.fetchone()
    total_tokens = int(row[0] or 0) if row else 0
    sessions = int(row[1] or 0) if row else 0

    # Daily chart (last 30 days)
    thirty_ago = _now_utc() - timedelta(days=30)
    from sqlalchemy import literal_column as _lc
    _day_trunc = func.date_trunc("day", AuditLog.created_at)
    daily_res = await db.execute(
        select(
            _day_trunc.label("date"),
            func.sum(AuditLog.total_tokens).label("tokens"),
        )
        .where(
            AuditLog.chat_session_id.in_(session_ids),
            AuditLog.created_at >= thirty_ago,
        )
        .group_by(_day_trunc)
        .order_by(_day_trunc)
    )
    daily_chart = [
        {"date": str(r.date)[:10], "tokens": int(r.tokens or 0)}
        for r in daily_res.fetchall()
    ]

    return {
        "total_tokens": total_tokens,
        "sessions": sessions,
        "daily_chart": daily_chart,
    }


async def get_my_skills_portfolio(
    tenant_id: uuid.UUID,
    db: AsyncSession,
    user_id: uuid.UUID,
) -> dict:
    """Full skills portfolio for the learner."""
    res = await db.execute(
        select(
            Skill.id.label("skill_id"),
            Skill.name.label("skill_name"),
            SkillCategory.name.label("category_name"),
            ProficiencyLevel.label.label("level"),
            ProficiencyLevel.level_order,
            UserSkillProgress.earned_at,
            UserSkillProgress.updated_at,
        )
        .join(Skill, Skill.id == UserSkillProgress.skill_id)
        .outerjoin(SkillCategory, SkillCategory.id == Skill.category_id)
        .join(ProficiencyLevel, ProficiencyLevel.id == UserSkillProgress.current_level_id)
        .where(UserSkillProgress.user_id == user_id)
        .order_by(SkillCategory.name.nullslast(), Skill.name)
    )

    skills = [
        {
            "skill_id": str(r.skill_id),
            "skill_name": r.skill_name,
            "category": r.category_name or "Uncategorised",
            "level": r.level,
            "level_order": r.level_order,
            "earned_at": r.earned_at.isoformat() if r.earned_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in res.fetchall()
    ]

    # Group by category
    by_category: dict[str, list] = {}
    for s in skills:
        by_category.setdefault(s["category"], []).append(s)

    return {
        "total_skills": len(skills),
        "skills": skills,
        "by_category": [
            {"category": cat, "skills": items}
            for cat, items in sorted(by_category.items())
        ],
    }


# ---------------------------------------------------------------------------
# Space Leaderboard
# ---------------------------------------------------------------------------

async def get_space_leaderboard(
    space_id: uuid.UUID,
    db: AsyncSession,
    sort_by: str = "completion",
) -> dict:
    """
    Leaderboard for learners in a space.
    sort_by: "completion" | "quiz_score" | "time_spent"
    """
    enrol_res = await db.execute(
        select(SpaceAccess.user_id).where(SpaceAccess.space_id == space_id)
    )
    user_ids = [r[0] for r in enrol_res.fetchall()]
    if not user_ids:
        return {"learners": []}

    users_res = await db.execute(
        select(AxisUser.id, AxisUser.full_name, AxisUser.email, AxisUser.avatar_url)
        .where(AxisUser.id.in_(user_ids))
    )
    user_map = {
        r.id: {"name": r.full_name or r.email, "avatar_url": r.avatar_url}
        for r in users_res.fetchall()
    }

    # Total items in space
    total_items_res = await db.execute(
        select(func.count(SpaceItem.id)).where(SpaceItem.space_id == space_id)
    )
    total_items = int(_scalar(total_items_res) or 1)

    # Completion progress per user
    prog_res = await db.execute(
        select(
            UserContentProgress.user_id,
            func.count(UserContentProgress.id).label("completed"),
            func.avg(UserContentProgress.progress_pct).label("avg_pct"),
        )
        .join(SpaceItem, SpaceItem.content_item_id == UserContentProgress.content_item_id)
        .where(
            SpaceItem.space_id == space_id,
            UserContentProgress.user_id.in_(user_ids),
        )
        .group_by(UserContentProgress.user_id)
    )
    prog_map = {r.user_id: {"completed": r.completed, "avg_pct": float(r.avg_pct or 0)}
                for r in prog_res.fetchall()}

    # Quiz accuracy per user (for quiz_score sort)
    quiz_res = await db.execute(
        select(
            QuizAttempt.axis_user_id,
            func.count(QuizAttempt.id).label("total"),
            func.sum(case((QuizAttempt.is_correct == True, 1), else_=0)).label("correct"),
        )
        .join(SpaceItem, SpaceItem.content_item_id == QuizAttempt.content_item_id)
        .where(
            SpaceItem.space_id == space_id,
            QuizAttempt.axis_user_id.in_(user_ids),
        )
        .group_by(QuizAttempt.axis_user_id)
    )
    quiz_map = {}
    for r in quiz_res.fetchall():
        total = r.total or 0
        correct = int(r.correct or 0)
        quiz_map[r.axis_user_id] = round(correct / total * 100, 1) if total else 0.0

    rows = []
    for uid in user_ids:
        pm = prog_map.get(uid, {})
        progress_pct = pm.get("avg_pct", 0)
        quiz_score = quiz_map.get(uid, 0.0)

        if sort_by == "quiz_score":
            score = quiz_score
        else:
            score = progress_pct

        rows.append({
            "user_id": str(uid),
            "name": user_map.get(uid, {}).get("name", ""),
            "avatar_url": user_map.get(uid, {}).get("avatar_url"),
            "score": score,
            "progress_pct": progress_pct,
            "quiz_score": quiz_score,
        })

    rows.sort(key=lambda x: -x["score"])
    for idx, row in enumerate(rows):
        row["rank"] = idx + 1

    return {"learners": rows}
