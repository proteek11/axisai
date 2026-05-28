"""
GET /api/v1/jobs/{job_id} — job status polling endpoint.

Accepts two authentication schemes:
  - Bearer <JWT>        → standalone Next.js frontend (JWT user auth)
  - Bearer axisai_<key> → Moodle plugin (tenant API key auth)

The tenant_id is resolved from whichever scheme is used, and applied to
the DB query for tenant isolation.
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.job import ProcessingJob
from app.schemas.job import JobStatusResponse

router = APIRouter()
log = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=False)


async def _resolve_tenant_id(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """
    Dual-auth dependency: accepts either a JWT (standalone frontend) or a
    tenant API key (Moodle plugin). Returns the caller's tenant_id.

    Priority:
      1. If token looks like a JWT (3 dot-separated parts) → try JWT decode.
         On success return user.tenant_id.
      2. Otherwise (or if JWT decode fails) → treat as API key.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Use: Authorization: Bearer <token>",
        )

    token = credentials.credentials

    # ── Try JWT first ─────────────────────────────────────────────────────────
    if token.count(".") == 2:  # JWTs always have exactly 3 dot-separated segments
        try:
            from app.api.v1.auth import get_current_user
            user = await get_current_user(token, db)
            return user.tenant_id
        except HTTPException:
            pass  # Not a valid JWT → fall through to API key check

    # ── Fall back to API key ───────────────────────────────────────────────────
    from app.core.security import get_current_tenant
    tenant = await get_current_tenant(credentials, db)
    return tenant.id


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_id: uuid.UUID = Depends(_resolve_tenant_id),
) -> JobStatusResponse:
    """
    Get the status and progress of a processing job.

    Poll this endpoint after POST /ingest until status = 'completed' or 'failed'.

    Typical polling strategy: every 2s for first 30s, then every 10s.
    """
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid job ID: {job_id}")

    result = await db.execute(
        select(ProcessingJob).where(
            ProcessingJob.id == job_uuid,
            ProcessingJob.tenant_id == tenant_id,  # Tenant isolation
        )
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found",
        )

    return JobStatusResponse(
        job_id=str(job.id),
        content_item_id=str(job.content_item_id),
        status=job.status,
        progress=job.progress,
        progress_message=job.progress_message,
        job_type=job.job_type,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )
