"""
Reports API — thin routing layer over report_service and report_pdf.

Admin endpoints:
  GET /api/v1/reports/admin/overview
  GET /api/v1/reports/admin/learner-activity
  GET /api/v1/reports/admin/space-completion
  GET /api/v1/reports/admin/content-performance
  GET /api/v1/reports/admin/certificates
  GET /api/v1/reports/admin/ai-usage
  GET /api/v1/reports/admin/teams
  GET /api/v1/reports/admin/assessments
  GET /api/v1/reports/admin/learner-profile      ?user_id=
  GET /api/v1/reports/admin/skill-gap
  GET /api/v1/reports/admin/skills-leaderboard
  GET /api/v1/reports/admin/skills-trend

Creator endpoints:
  GET /api/v1/reports/creator/dashboard
  GET /api/v1/reports/creator/space-deep-dive    ?space_id=
  GET /api/v1/reports/creator/content-engagement
  GET /api/v1/reports/creator/quiz-report
  GET /api/v1/reports/creator/learner-progress   ?space_id=
  GET /api/v1/reports/creator/certificates

Learner endpoints:
  GET /api/v1/reports/learner/summary
  GET /api/v1/reports/learner/progress
  GET /api/v1/reports/learner/quiz-history
  GET /api/v1/reports/learner/ai-usage
  GET /api/v1/reports/learner/skills

Export:
  POST /api/v1/reports/export/pdf
  POST /api/v1/reports/export/csv

Leaderboard:
  GET /api/v1/reports/spaces/{space_id}/leaderboard   ?sort_by=
"""
import uuid
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user
from app.core.database import get_db
from app.models.user import AxisUser
from app.services import report_service, report_pdf

router = APIRouter(prefix="/reports", tags=["Reports"])
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class ExportRequest(BaseModel):
    report_type: str
    filters: Optional[dict[str, Any]] = None


# ── Role guards ───────────────────────────────────────────────────────────────

def _require_admin(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin only")


def _require_creator_or_admin(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin", "creator"):
        raise HTTPException(status_code=403, detail="Creator or admin only")


# ── Shared filter helper ──────────────────────────────────────────────────────

def _build_filters(
    date_from: Optional[str],
    date_to: Optional[str],
    team_id: Optional[str],
    space_id: Optional[str],
    user_search: Optional[str],
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    if team_id:
        filters["team_id"] = team_id
    if space_id:
        filters["space_id"] = space_id
    if user_search:
        filters["user_search"] = user_search
    return filters


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN REPORTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/admin/overview")
async def admin_overview(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Platform overview report — active users, completions, certificates, AI usage."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_platform_overview(user.tenant_id, db, filters)


@router.get("/admin/learner-activity")
async def admin_learner_activity(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner activity report — logins, content views, time-on-platform per user."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_learner_activity(user.tenant_id, db, filters)


@router.get("/admin/space-completion")
async def admin_space_completion(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Space completion rates across all spaces for the tenant."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_space_completion(user.tenant_id, db, filters)


@router.get("/admin/content-performance")
async def admin_content_performance(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Content performance — views, completions, avg scores per content item."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_content_performance(user.tenant_id, db, filters)


@router.get("/admin/certificates")
async def admin_certificate_report(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Certificate issuance report — issued counts, revocations, by space."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_certificate_report(user.tenant_id, db, filters)


@router.get("/admin/ai-usage")
async def admin_ai_usage(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """AI usage report — token consumption, chat sessions, costs per user/space."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_ai_usage_report(user.tenant_id, db, filters)


@router.get("/admin/teams")
async def admin_team_report(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Team report — completion rates, activity, certificates per team."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_team_report(user.tenant_id, db, filters)


@router.get("/admin/assessments")
async def admin_assessment_report(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Assessment report — attempt counts, pass rates, avg scores per quiz."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_assessment_report(user.tenant_id, db, filters)



@router.get("/admin/learners/search")
async def admin_learners_search(
    q: str = Query("", description="Name or email search query"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Search learners by name or email — for the learner-profile picker."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    return await report_service.search_learners(user.tenant_id, db, q)


@router.get("/admin/learner-profile")
async def admin_learner_profile(
    user_id: str = Query(..., description="UUID of the learner to profile"),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deep profile for a single learner — activity, completions, certs, skills."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)

    try:
        target_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a valid UUID")

    filters: dict[str, Any] = {}
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    return await report_service.get_learner_profile(
        user.tenant_id, db, target_user_id
    )


@router.get("/admin/skill-gap")
async def admin_skill_gap(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Skill gap analysis — target vs attained proficiency levels per role."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_skill_gap_analysis(user.tenant_id, db, filters)


@router.get("/admin/skills-leaderboard")
async def admin_skills_leaderboard(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Skills leaderboard — top learners ranked by total skill points."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_skills_leaderboard(user.tenant_id, db, filters)


@router.get("/admin/skills-trend")
async def admin_skills_trend(
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    team_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    user_search: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Skills trend — skill progress gained over time (weekly/monthly buckets)."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    filters = _build_filters(date_from, date_to, team_id, space_id, user_search)
    return await report_service.get_skills_trend(user.tenant_id, db, filters)


# ═══════════════════════════════════════════════════════════════════════════════
# CREATOR REPORTS
# ═══════════════════════════════════════════════════════════════════════════════


@router.get("/admin/learner-profile/{user_id}")
async def admin_learner_profile_path(
    user_id: str,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deep profile for a single learner (path param variant)."""
    user = await get_current_user(credentials.credentials, db)
    _require_admin(user)
    try:
        target_user_id = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="user_id must be a valid UUID")
    return await report_service.get_learner_profile(user.tenant_id, db, target_user_id)



@router.get("/creator/spaces")
async def creator_spaces_list(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """List spaces owned by this creator — for dropdown selectors."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)
    return await report_service.get_creator_spaces(user.tenant_id, db, user.id)


@router.get("/creator/dashboard")
async def creator_dashboard(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Creator dashboard — summary of all spaces the creator owns."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)
    return await report_service.get_creator_dashboard(user.tenant_id, db, user.id)


@router.get("/creator/space-deep-dive")
async def creator_space_deep_dive(
    space_id: str = Query(..., description="UUID of the space to analyse"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deep dive into a single space — enrolment, completion funnel, content breakdown."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    try:
        space_uuid = uuid.UUID(space_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="space_id must be a valid UUID")

    return await report_service.get_space_deep_dive(
        user.tenant_id, db, space_uuid, user.id
    )



@router.get("/creator/space-deep-dive/{space_id}")
async def creator_space_deep_dive_path(
    space_id: str,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deep dive into a single space (path param variant)."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)
    try:
        space_uuid = uuid.UUID(space_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="space_id must be a valid UUID")
    return await report_service.get_space_deep_dive(user.tenant_id, db, space_uuid, user.id)


@router.get("/creator/content-engagement")
async def creator_content_engagement(
    space_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Content engagement metrics for the creator's spaces."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    space_uuid: Optional[uuid.UUID] = None
    if space_id:
        try:
            space_uuid = uuid.UUID(space_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="space_id must be a valid UUID")

    return await report_service.get_content_engagement(
        user.tenant_id, db, user.id
    )


@router.get("/creator/quiz-report")
async def creator_quiz_report(
    space_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Quiz attempt data for the creator's spaces — pass rates and question-level breakdown."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    space_uuid: Optional[uuid.UUID] = None
    if space_id:
        try:
            space_uuid = uuid.UUID(space_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="space_id must be a valid UUID")

    return await report_service.get_quiz_report(
        user.tenant_id, db, user.id, space_id=space_uuid
    )


@router.get("/creator/learner-progress")
async def creator_learner_progress(
    space_id: str = Query(..., description="UUID of the space"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per-learner progress for a space the creator owns."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    try:
        space_uuid = uuid.UUID(space_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="space_id must be a valid UUID")

    return await report_service.get_creator_learner_progress(
        user.tenant_id, db, space_uuid
    )



@router.get("/creator/learner-progress/{space_id}")
async def creator_learner_progress_path(
    space_id: str,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Per-learner progress for a space (path param variant)."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)
    try:
        space_uuid = uuid.UUID(space_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="space_id must be a valid UUID")
    return await report_service.get_creator_learner_progress(user.tenant_id, db, space_uuid)


@router.get("/creator/certificates")
async def creator_certificates(
    space_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Certificates issued for the creator's spaces."""
    user = await get_current_user(credentials.credentials, db)
    _require_creator_or_admin(user)

    space_uuid: Optional[uuid.UUID] = None
    if space_id:
        try:
            space_uuid = uuid.UUID(space_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="space_id must be a valid UUID")

    return await report_service.get_creator_certificates(
        user.tenant_id, db, user.id
    )


# ═══════════════════════════════════════════════════════════════════════════════
# LEARNER REPORTS (any authenticated user — scoped to own data)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/learner/summary")
async def learner_summary(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's own learning summary — enrolled spaces, completion rate, streak."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_learning_summary(user.tenant_id, db, user.id)


@router.get("/learner/progress")
async def learner_progress(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's progress across all enrolled spaces with per-item status."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_progress_report(user.tenant_id, db, user.id)


@router.get("/learner/quiz-history")
async def learner_quiz_history(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's quiz attempt history — scores, pass/fail, dates."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_quiz_history(user.tenant_id, db, user.id)


@router.get("/learner/ai-usage")
async def learner_ai_usage(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's own AI chat usage — sessions, messages, token consumption."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_ai_usage(user.tenant_id, db, user.id)


@router.get("/learner/skills")
async def learner_skills(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's skill portfolio — attained proficiency levels with role gap view."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_skills_portfolio(user.tenant_id, db, user.id)
@router.get("/learner/certificates")
async def learner_certificates(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Learner's earned certificates."""
    user = await get_current_user(credentials.credentials, db)
    return await report_service.get_my_certificates(user.tenant_id, db, user.id)





# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT (PDF / CSV)
# ═══════════════════════════════════════════════════════════════════════════════

@router.post("/export/pdf")
async def export_pdf(
    body: ExportRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Generate and return a report as a PDF file.

    Body: { "report_type": "...", "filters": { ... } }

    Admin-only report types require admin role; creator types require creator/admin.
    """
    user = await get_current_user(credentials.credentials, db)

    _ADMIN_TYPES = {
        "platform_overview", "learner_activity", "space_completion",
        "content_performance", "certificates", "ai_usage", "teams",
        "assessments", "learner_profile", "skill_gap",
        "skills_leaderboard", "skills_trend",
    }
    _CREATOR_TYPES = {
        "creator_dashboard", "space_deep_dive", "content_engagement",
        "quiz_report", "creator_learner_progress", "creator_certificates",
    }

    if body.report_type in _ADMIN_TYPES:
        _require_admin(user)
    elif body.report_type in _CREATOR_TYPES:
        _require_creator_or_admin(user)
    # Learner types are accessible to all authenticated users

    try:
        pdf_bytes = await report_pdf.generate_pdf(
            report_type=body.report_type,
            filters=body.filters or {},
            user=user,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = f"report_{body.report_type}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/csv")
async def export_csv(
    body: ExportRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Generate and return a report as a CSV file.

    Body: { "report_type": "...", "filters": { ... } }
    """
    user = await get_current_user(credentials.credentials, db)

    _ADMIN_TYPES = {
        "platform_overview", "learner_activity", "space_completion",
        "content_performance", "certificates", "ai_usage", "teams",
        "assessments", "learner_profile", "skill_gap",
        "skills_leaderboard", "skills_trend",
    }
    _CREATOR_TYPES = {
        "creator_dashboard", "space_deep_dive", "content_engagement",
        "quiz_report", "creator_learner_progress", "creator_certificates",
    }

    if body.report_type in _ADMIN_TYPES:
        _require_admin(user)
    elif body.report_type in _CREATOR_TYPES:
        _require_creator_or_admin(user)

    try:
        csv_text = await report_pdf.generate_csv(
            report_type=body.report_type,
            filters=body.filters or {},
            user=user,
            db=db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = f"report_{body.report_type}.csv"
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# SPACE LEADERBOARD (any authenticated user with space access)
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/spaces/{space_id}/leaderboard")
async def space_leaderboard(
    space_id: uuid.UUID,
    sort_by: Optional[str] = Query(None, description="Sort field: 'progress' | 'score' | 'completed_at'"),
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Leaderboard for a specific space.

    Any authenticated user may call this endpoint; the service checks
    that the caller has access to the space before returning data.
    """
    user = await get_current_user(credentials.credentials, db)

    return await report_service.get_space_leaderboard(
        user_id=user.id,
        tenant_id=user.tenant_id,
        space_id=space_id,
        sort_by=sort_by or "progress",
        db=db,
    )
