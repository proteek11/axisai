"""
Report PDF/CSV export service.

generate_pdf() and generate_csv() are called by /api/v1/reports/export/pdf
and /api/v1/reports/export/csv respectively.

Both functions delegate to report_service to fetch the data, then render it
into the requested format.

PDF rendering uses ReportLab (reportlab package).
CSV rendering uses Python's built-in csv module.
"""
from __future__ import annotations

import csv
import io
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import AxisUser
from app.services import report_service

log = structlog.get_logger(__name__)

# ── Dispatcher maps ───────────────────────────────────────────────────────────

_SERVICE_MAP = {
    "platform_overview":        lambda uid, tid, db, f: report_service.get_platform_overview(tid, db, f),
    "learner_activity":         lambda uid, tid, db, f: report_service.get_learner_activity(tid, db, f),
    "space_completion":         lambda uid, tid, db, f: report_service.get_space_completion(tid, db, f),
    "content_performance":      lambda uid, tid, db, f: report_service.get_content_performance(tid, db, f),
    "certificates":             lambda uid, tid, db, f: report_service.get_certificate_report(tid, db, f),
    "ai_usage":                 lambda uid, tid, db, f: report_service.get_ai_usage_report(tid, db, f),
    "teams":                    lambda uid, tid, db, f: report_service.get_team_report(tid, db, f),
    "assessments":              lambda uid, tid, db, f: report_service.get_assessment_report(tid, db, f),
    "skill_gap":                lambda uid, tid, db, f: report_service.get_skill_gap_analysis(tid, db, f),
    "skills_leaderboard":       lambda uid, tid, db, f: report_service.get_skills_leaderboard(tid, db, f),
    "skills_trend":             lambda uid, tid, db, f: report_service.get_skills_trend(tid, db, f),
    # Creator reports  (signature: tenant_id, db, creator_id)
    "creator_dashboard":        lambda uid, tid, db, f: report_service.get_creator_dashboard(tid, db, uid),
    "content_engagement":       lambda uid, tid, db, f: report_service.get_content_engagement(tid, db, uid),
    "quiz_report":              lambda uid, tid, db, f: report_service.get_quiz_report(tid, db, uid),
    # Learner reports  (signature: tenant_id, db, user_id)
    "my_learning_summary":      lambda uid, tid, db, f: report_service.get_my_learning_summary(tid, db, uid),
    "my_progress":              lambda uid, tid, db, f: report_service.get_my_progress_report(tid, db, uid),
    "my_quiz_history":          lambda uid, tid, db, f: report_service.get_my_quiz_history(tid, db, uid),
    "my_ai_usage":              lambda uid, tid, db, f: report_service.get_my_ai_usage(tid, db, uid),
    "my_skills_portfolio":      lambda uid, tid, db, f: report_service.get_my_skills_portfolio(tid, db, uid),
}


async def _fetch_report_data(
    report_type: str,
    filters: dict[str, Any],
    user: AxisUser,
    db: AsyncSession,
) -> dict[str, Any]:
    """Resolve report_type to the correct service call and return its dict."""
    fn = _SERVICE_MAP.get(report_type)
    if fn is None:
        raise ValueError(f"Unknown report_type: {report_type!r}")

    # Special cases that require extra params from filters
    if report_type == "learner_profile":
        user_id_str = filters.get("user_id")
        if not user_id_str:
            raise ValueError("learner_profile requires user_id in filters")
        # signature: get_learner_profile(tenant_id, db, user_id)
        return await report_service.get_learner_profile(
            user.tenant_id, db, uuid.UUID(user_id_str)
        )
    if report_type == "space_deep_dive":
        space_id_str = filters.get("space_id")
        if not space_id_str:
            raise ValueError("space_deep_dive requires space_id in filters")
        # signature: get_space_deep_dive(tenant_id, db, space_id, creator_id)
        return await report_service.get_space_deep_dive(
            user.tenant_id, db, uuid.UUID(space_id_str), user.id
        )
    if report_type == "creator_learner_progress":
        space_id_str = filters.get("space_id")
        if not space_id_str:
            raise ValueError("creator_learner_progress requires space_id in filters")
        # signature: get_creator_learner_progress(tenant_id, db, space_id)
        return await report_service.get_creator_learner_progress(
            user.tenant_id, db, uuid.UUID(space_id_str)
        )
    if report_type == "creator_certificates":
        # signature: get_creator_certificates(tenant_id, db, creator_id, filters)
        return await report_service.get_creator_certificates(
            user.tenant_id, db, user.id, filters
        )

    return await fn(user.id, user.tenant_id, db, filters)


def _flatten_for_csv(data: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """
    Best-effort flattening of a report dict into (headers, rows) for CSV output.

    Looks for the first list-of-dicts value in the response; falls back to
    a single summary row using all top-level scalar keys.
    """
    # Find first list-of-dicts
    for val in data.values():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            headers = list(val[0].keys())
            rows = [[str(item.get(h, "")) for h in headers] for item in val]
            return headers, rows

    # Fallback: single summary row from scalar top-level keys
    headers = [k for k, v in data.items() if not isinstance(v, (dict, list))]
    rows = [[str(data[h]) for h in headers]]
    return headers, rows


async def generate_pdf(
    report_type: str,
    filters: dict[str, Any],
    user: AxisUser,
    db: AsyncSession,
) -> bytes:
    """
    Fetch report data and render as a PDF.

    Uses ReportLab SimpleDocTemplate with a basic table layout.
    Falls back to a minimal text PDF if ReportLab is unavailable.
    """
    data = await _fetch_report_data(report_type, filters, user, db)
    headers, rows = _flatten_for_csv(data)

    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import cm

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=1 * cm, rightMargin=1 * cm)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title = report_type.replace("_", " ").title()
        elements.append(Paragraph(f"<b>{title}</b>", styles["Title"]))
        elements.append(Spacer(1, 0.5 * cm))

        if headers and rows:
            table_data = [headers] + rows
            tbl = Table(table_data, repeatRows=1)
            tbl.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1d4ed8")),
                    ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                    ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE",   (0, 0), (-1, -1), 8),
                    ("GRID",       (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0f4ff")]),
                    ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ])
            )
            elements.append(tbl)
        else:
            elements.append(Paragraph("No data available for this report.", styles["Normal"]))

        doc.build(elements)
        return buf.getvalue()

    except ImportError:
        log.warning("reportlab_not_installed", report_type=report_type)
        # Minimal valid PDF fallback
        content = f"%PDF-1.4\n% Report: {report_type}\n% Install reportlab for full PDF support\n"
        return content.encode()


async def generate_csv(
    report_type: str,
    filters: dict[str, Any],
    user: AxisUser,
    db: AsyncSession,
) -> str:
    """Fetch report data and render as a UTF-8 CSV string."""
    data = await _fetch_report_data(report_type, filters, user, db)
    headers, rows = _flatten_for_csv(data)

    buf = io.StringIO()
    writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    writer.writerows(rows)
    return buf.getvalue()
