"""
Certificate API — PF-02.

Endpoints:
  GET  /api/v1/spaces/{space_id}/completion       → check completion status
  POST /api/v1/spaces/{space_id}/certificate      → issue (or re-issue) certificate
  GET  /api/v1/spaces/{space_id}/certificate      → download certificate PDF
  GET  /api/v1/my/certificates                    → list all certificates for logged-in learner
"""
import uuid
from typing import Any, Optional
from pydantic import BaseModel as _BM

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.certificate import SpaceCertificate
from app.models.space import LearningSpace, SpaceAccess
from app.models.user import AxisUser
from app.services.certificate_service import (
    check_space_completion,
    get_certificate_pdf_bytes,
    issue_certificate,
)

log = structlog.get_logger(__name__)
router = APIRouter(tags=["certificates"])
security = HTTPBearer()


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> AxisUser:
    """Validate JWT and return AxisUser."""
    from app.core.jwt import decode_access_token
    payload = decode_access_token(creds.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token missing subject")
    r = await db.execute(select(AxisUser).where(AxisUser.id == uuid.UUID(user_id)))
    user = r.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def _assert_space_access(
    space_id: uuid.UUID,
    user: AxisUser,
    db: AsyncSession,
) -> LearningSpace:
    """Ensure the learner has access to the space (or is the creator)."""
    r = await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))
    space = r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")

    # Creator always has access
    if space.creator_id == user.id:
        return space

    # Check SpaceAccess (direct user grant or team grant)
    from app.models.team import TeamMember
    team_ids_r = await db.execute(
        select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    )
    team_ids = [row.team_id for row in team_ids_r]

    access_r = await db.execute(
        select(SpaceAccess).where(
            SpaceAccess.space_id == space_id,
            (SpaceAccess.user_id == user.id) |
            (SpaceAccess.team_id.in_(team_ids) if team_ids else SpaceAccess.team_id.is_(None)),
        )
    )
    if not access_r.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="You do not have access to this space")

    return space


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/spaces/{space_id}/completion")
async def get_space_completion(
    space_id: uuid.UUID,
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return completion status for the logged-in learner in a space.

    Response:
    {
      "completed": bool,
      "total_items": int,
      "completed_items": int,
      "progress_pct": float,
      "certificate_issued": bool,
      "certificate_id": str | null
    }
    """
    await _assert_space_access(space_id, user, db)
    return await check_space_completion(space_id, user.id, db)


@router.post("/spaces/{space_id}/certificate")
async def issue_space_certificate(
    space_id: uuid.UUID,
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Issue (or re-issue) a completion certificate for the logged-in learner.

    Returns 400 if the space is not yet fully completed.
    Returns 200 with certificate metadata on success.
    """
    await _assert_space_access(space_id, user, db)

    try:
        cert = await issue_certificate(space_id=space_id, user=user, db=db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "certificate_id": str(cert.id),
        "issued_at": cert.issued_at.isoformat(),
        "learner_name": cert.cert_data.get("learner_name"),
        "space_title": cert.cert_data.get("space_title"),
    }


@router.get("/spaces/{space_id}/certificate")
async def download_space_certificate(
    space_id: uuid.UUID,
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    Download the PDF certificate for the logged-in learner.

    Returns 404 if no certificate has been issued yet.
    Auto-issues if space is complete and no cert exists.
    """
    await _assert_space_access(space_id, user, db)

    # Check if cert exists; auto-issue if space is completed
    r = await db.execute(
        select(SpaceCertificate).where(
            SpaceCertificate.user_id == user.id,
            SpaceCertificate.space_id == space_id,
        )
    )
    cert = r.scalar_one_or_none()

    if not cert:
        # Try to auto-issue
        try:
            cert = await issue_certificate(space_id=space_id, user=user, db=db)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail="No certificate available. Complete all space items first.",
            )

    pdf_bytes = get_certificate_pdf_bytes(cert)
    safe_title = (cert.cert_data.get("space_title") or "certificate").replace(" ", "_")[:40]
    filename = f"certificate_{safe_title}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/my/certificates")
async def list_my_certificates(
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    List all certificates issued to the logged-in learner.
    """
    r = await db.execute(
        select(SpaceCertificate).where(SpaceCertificate.user_id == user.id)
        .order_by(SpaceCertificate.issued_at.desc())
    )
    certs = r.scalars().all()

    return [
        {
            "certificate_id": str(c.id),
            "space_id": str(c.space_id),
            "space_title": c.cert_data.get("space_title"),
            "issued_at": c.issued_at.isoformat(),
            "download_url": f"/api/v1/spaces/{c.space_id}/certificate",
        }
        for c in certs
    ]


# ── Admin / Creator: management endpoints ─────────────────────────────────────

@router.get("/admin/certificates")
async def admin_list_certificates(
    space_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Admin: list all issued certificates platform-wide.
    Creator: list certificates issued for a specific space they own.

    Query params:
      space_id  — optional, filter by space
      limit     — default 100
      offset    — default 0
    """
    if user.role not in ("admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator role required")

    from app.models.space import LearningSpace
    from app.models.user import AxisUser as UserModel

    stmt = (
        select(SpaceCertificate)
        .order_by(SpaceCertificate.issued_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if space_id:
        stmt = stmt.where(SpaceCertificate.space_id == uuid.UUID(space_id))

        # Creator can only see certs for their own spaces
        if user.role == "creator":
            space_r = await db.execute(
                select(LearningSpace.creator_id).where(
                    LearningSpace.id == uuid.UUID(space_id)
                )
            )
            creator_id = space_r.scalar_one_or_none()
            if creator_id != user.id:
                raise HTTPException(status_code=403, detail="You don't own this space")

    elif user.role == "creator":
        # Creator without space_id filter — only their spaces
        space_ids_r = await db.execute(
            select(LearningSpace.id).where(LearningSpace.creator_id == user.id)
        )
        owned_ids = [row.id for row in space_ids_r]
        if not owned_ids:
            return {"certificates": [], "total": 0}
        stmt = stmt.where(SpaceCertificate.space_id.in_(owned_ids))

    # Count total (same filter, no pagination)
    count_stmt = select(SpaceCertificate.id)
    if space_id:
        count_stmt = count_stmt.where(SpaceCertificate.space_id == uuid.UUID(space_id))
    elif user.role == "creator":
        space_ids_r2 = await db.execute(
            select(LearningSpace.id).where(LearningSpace.creator_id == user.id)
        )
        owned_ids2 = [row.id for row in space_ids_r2]
        count_stmt = count_stmt.where(SpaceCertificate.space_id.in_(owned_ids2))

    count_r = await db.execute(count_stmt)
    total = len(count_r.scalars().all())

    r = await db.execute(stmt)
    certs = r.scalars().all()

    return {
        "total": total,
        "certificates": [
            {
                "certificate_id": str(c.id),
                "space_id": str(c.space_id),
                "space_title": c.cert_data.get("space_title", "Unknown"),
                "learner_name": c.cert_data.get("learner_name", "Unknown"),
                "learner_email": c.cert_data.get("learner_email", ""),
                "issued_at": c.issued_at.isoformat(),
                "user_id": str(c.user_id),
            }
            for c in certs
        ],
    }


@router.delete("/admin/certificates/{certificate_id}", status_code=204)
async def admin_revoke_certificate(
    certificate_id: uuid.UUID,
    user: AxisUser = Depends(_get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Admin only: revoke (delete) a certificate."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    r = await db.execute(
        select(SpaceCertificate).where(SpaceCertificate.id == certificate_id)
    )
    cert = r.scalar_one_or_none()
    if not cert:
        raise HTTPException(status_code=404, detail="Certificate not found")

    # Remove PDF file from disk
    from pathlib import Path
    if cert.pdf_path and Path(cert.pdf_path).exists():
        Path(cert.pdf_path).unlink(missing_ok=True)

    await db.delete(cert)
    await db.commit()
    log.info("certificate_revoked", cert_id=str(certificate_id), admin_id=str(user.id))




# ── Admin / Creator: manually issue a certificate for a specific learner ────

class ManualIssueRequest(_BM):
    space_id: str
    user_id: str


@router.post("/admin/certificates/issue", status_code=201)
async def admin_issue_certificate(
    body: ManualIssueRequest,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Admin or creator manually issues a certificate for a specific learner.

    Bypasses the completion check — useful for participation awards,
    manual trigger type cert configs, or admin exceptions.

    Returns 404 if the space or user is not found.
    """
    user = await _get_current_user(creds, db)
    if user.role not in ("admin", "super_admin", "creator"):
        raise HTTPException(status_code=403, detail="Admin or creator access required")

    # Verify space exists and (for creator) they own it
    space_id_uuid = uuid.UUID(body.space_id)
    space_r = await db.execute(
        select(LearningSpace).where(LearningSpace.id == space_id_uuid)
    )
    space = space_r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")

    if user.role == "creator" and space.creator_id != user.id:
        raise HTTPException(status_code=403, detail="You don't own this space")

    # Resolve the learner
    user_id_uuid = uuid.UUID(body.user_id)
    learner_r = await db.execute(
        select(AxisUser).where(
            AxisUser.id == user_id_uuid,
            AxisUser.tenant_id == user.tenant_id,
        )
    )
    learner = learner_r.scalar_one_or_none()
    if not learner:
        raise HTTPException(status_code=404, detail="User not found in this tenant")

    from app.services.certificate_service import force_issue_certificate
    cert = await force_issue_certificate(
        space_id=space_id_uuid,
        user=learner,
        db=db,
    )

    return {
        "certificate_id": str(cert.id),
        "issued_at": cert.issued_at.isoformat(),
        "learner_name": cert.cert_data.get("learner_name"),
        "learner_email": cert.cert_data.get("learner_email"),
        "space_title": cert.cert_data.get("space_title"),
        "issued_manually": True,
    }

# ═══════════════════════════════════════════════════════════════════════════════
# CERTIFICATE TEMPLATES  (admin only)
# ═══════════════════════════════════════════════════════════════════════════════

from app.models.certificate_template import CertificateTemplate, SpaceCertificateConfig
from app.core.jwt import decode_access_token as _djwt
from fastapi import File, Form, UploadFile
import aiofiles, os as _os

def _get_logo_dir() -> str:
    from app.config import settings as _settings
    d = _settings.cert_logos_dir
    _os.makedirs(d, exist_ok=True)
    return d


def _admin_check(user: AxisUser) -> None:
    if user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")


class TemplateCreate(_BM):
    name: str
    type_tag: str = "completion"
    layout_style: str = "classic"
    title_text: str = "Certificate of Completion"
    body_text: Optional[str] = None
    signature_name: Optional[str] = None
    signature_title: Optional[str] = None


class TemplateOut(_BM):
    id: str
    name: str
    type_tag: str
    layout_style: str
    title_text: str
    body_text: Optional[str]
    logo_path: Optional[str]
    signature_name: Optional[str]
    signature_title: Optional[str]
    signature_path: Optional[str]
    is_active: bool
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/admin/certificate-templates")
async def list_templates(
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    user = await _get_current_user(creds, db)
    _admin_check(user)
    r = await db.execute(
        select(CertificateTemplate)
        .where(CertificateTemplate.tenant_id == user.tenant_id)
        .order_by(CertificateTemplate.created_at)
    )
    templates = r.scalars().all()
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "type_tag": t.type_tag,
            "layout_style": t.layout_style,
            "title_text": t.title_text,
            "body_text": t.body_text,
            "logo_path": t.logo_path,
            "signature_name": t.signature_name,
            "signature_title": t.signature_title,
            "signature_path": t.signature_path,
            "is_active": t.is_active,
            "created_at": t.created_at.isoformat(),
        }
        for t in templates
    ]


@router.post("/admin/certificate-templates", status_code=201)
async def create_template(
    body: TemplateCreate,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_current_user(creds, db)
    _admin_check(user)
    tmpl = CertificateTemplate(
        tenant_id=user.tenant_id,
        name=body.name,
        type_tag=body.type_tag,
        layout_style=body.layout_style,
        title_text=body.title_text,
        body_text=body.body_text,
        signature_name=body.signature_name,
        signature_title=body.signature_title,
    )
    db.add(tmpl)
    await db.commit()
    await db.refresh(tmpl)
    return {"id": str(tmpl.id), "name": tmpl.name, "created_at": tmpl.created_at.isoformat()}


@router.put("/admin/certificate-templates/{template_id}")
async def update_template(
    template_id: uuid.UUID,
    body: TemplateCreate,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_current_user(creds, db)
    _admin_check(user)
    r = await db.execute(
        select(CertificateTemplate).where(
            CertificateTemplate.id == template_id,
            CertificateTemplate.tenant_id == user.tenant_id,
        )
    )
    tmpl = r.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")
    tmpl.name = body.name
    tmpl.type_tag = body.type_tag
    tmpl.layout_style = body.layout_style
    tmpl.title_text = body.title_text
    tmpl.body_text = body.body_text
    tmpl.signature_name = body.signature_name
    tmpl.signature_title = body.signature_title
    await db.commit()
    return {"id": str(tmpl.id), "updated": True}


@router.post("/admin/certificate-templates/{template_id}/logo")
async def upload_template_logo(
    template_id: uuid.UUID,
    file: UploadFile = File(...),
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_current_user(creds, db)
    _admin_check(user)
    r = await db.execute(
        select(CertificateTemplate).where(
            CertificateTemplate.id == template_id,
            CertificateTemplate.tenant_id == user.tenant_id,
        )
    )
    tmpl = r.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    _logo_dir = _get_logo_dir()
    ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower()
    filename = f"{template_id}_logo.{ext}"
    dest = _os.path.join(_logo_dir, filename)
    async with aiofiles.open(dest, "wb") as f:
        content = await file.read()
        await f.write(content)

    tmpl.logo_path = f"/cert-logos/{filename}"
    await db.commit()
    return {"logo_path": tmpl.logo_path}


@router.delete("/admin/certificate-templates/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _get_current_user(creds, db)
    _admin_check(user)
    r = await db.execute(
        select(CertificateTemplate).where(
            CertificateTemplate.id == template_id,
            CertificateTemplate.tenant_id == user.tenant_id,
        )
    )
    tmpl = r.scalar_one_or_none()
    if tmpl:
        await db.delete(tmpl)
        await db.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# SPACE CERTIFICATE CONFIGS  (creator / admin)
# ═══════════════════════════════════════════════════════════════════════════════

class CertConfigCreate(_BM):
    template_id: Optional[str] = None
    trigger_type: str = "all_items"   # all_items | percentage | assessment | manual
    trigger_value: dict = {}
    custom_title: Optional[str] = None
    custom_message: Optional[str] = None
    position: int = 0


@router.get("/spaces/{space_id}/cert-configs")
async def list_space_cert_configs(
    space_id: uuid.UUID,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    user = await _get_current_user(creds, db)
    # Learners with space access can see configs (to render milestone cards)
    # Creators/admins also allowed
    space = await _assert_space_access(space_id, user, db)
    r = await db.execute(
        select(SpaceCertificateConfig, CertificateTemplate)
        .outerjoin(CertificateTemplate, SpaceCertificateConfig.template_id == CertificateTemplate.id)
        .where(SpaceCertificateConfig.space_id == space_id)
        .order_by(SpaceCertificateConfig.position)
    )
    rows = r.all()
    return [
        {
            "id": str(cfg.id),
            "template_id": str(cfg.template_id) if cfg.template_id else None,
            "template_name": tmpl.name if tmpl else None,
            "template_layout": tmpl.layout_style if tmpl else None,
            "trigger_type": cfg.trigger_type,
            "trigger_value": cfg.trigger_value,
            "custom_title": cfg.custom_title,
            "custom_message": cfg.custom_message,
            "position": cfg.position,
            "is_active": cfg.is_active,
        }
        for cfg, tmpl in rows
    ]


@router.post("/spaces/{space_id}/cert-configs", status_code=201)
async def add_space_cert_config(
    space_id: uuid.UUID,
    body: CertConfigCreate,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await _get_current_user(creds, db)
    await _assert_creator_or_admin(space_id, user, db)
    cfg = SpaceCertificateConfig(
        space_id=space_id,
        template_id=uuid.UUID(body.template_id) if body.template_id else None,
        trigger_type=body.trigger_type,
        trigger_value=body.trigger_value,
        custom_title=body.custom_title,
        custom_message=body.custom_message,
        position=body.position,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return {"id": str(cfg.id), "created": True}


@router.delete("/spaces/{space_id}/cert-configs/{config_id}", status_code=204)
async def remove_space_cert_config(
    space_id: uuid.UUID,
    config_id: uuid.UUID,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> None:
    user = await _get_current_user(creds, db)
    await _assert_creator_or_admin(space_id, user, db)
    r = await db.execute(
        select(SpaceCertificateConfig).where(
            SpaceCertificateConfig.id == config_id,
            SpaceCertificateConfig.space_id == space_id,
        )
    )
    cfg = r.scalar_one_or_none()
    if cfg:
        await db.delete(cfg)
        await db.commit()


# ── Helper ─────────────────────────────────────────────────────────────────
async def _assert_creator_or_admin(
    space_id: uuid.UUID,
    user: AxisUser,
    db: AsyncSession,
) -> LearningSpace:
    r = await db.execute(select(LearningSpace).where(LearningSpace.id == space_id))
    space = r.scalar_one_or_none()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    if space.creator_id != user.id and user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")
    return space


# ── Serve logo images ──────────────────────────────────────────────────────
from fastapi.responses import FileResponse as _FileResponse

@router.get("/cert-logos/{filename}")
async def serve_cert_logo(
    filename: str,
    creds: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> _FileResponse:
    await _get_current_user(creds, db)  # must be logged in
    path = _os.path.join(_get_logo_dir(), filename)
    if not _os.path.exists(path):
        raise HTTPException(status_code=404, detail="Logo not found")
    return _FileResponse(path)
