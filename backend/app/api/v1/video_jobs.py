"""
Video job API — POST /api/v1/video/jobs and GET /api/v1/video/jobs/{job_id}.

Design mirrors ingest.py:
  POST returns 202 Accepted immediately and dispatches a Celery task.
  GET supports both the internal UUID and the integer moodle_job_id.

Idempotency:
  If a job with the same (tenant_id, moodle_job_id) already exists and is
  queued or processing, the existing record is returned — no duplicate dispatch.
  A failed job can be retried by sending the same request again; the record is
  reset and re-queued.

Preview / Approval flow (Step 10):
  POST /{id}/preview  — queue a 30-s preview render
  POST /{id}/approve  — approve the preview and dispatch the full render
"""
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant
from app.models.tenant import Tenant
from app.models.video_job import VideoJob, VideoJobStatus
from app.schemas.video_job import (
    VideoJobListResponse,
    VideoJobCreateRequest,
    VideoJobCreateResponse,
    VideoJobPreviewResponse,
    VideoJobStatusResponse,
)

router = APIRouter()
log = structlog.get_logger(__name__)

# Statuses that mean a job is actively being worked on (no re-dispatch)
_ACTIVE_STATUSES = frozenset({
    VideoJobStatus.QUEUED.value,
    VideoJobStatus.PROCESSING.value,
    VideoJobStatus.PREVIEW_PENDING.value,
})


# ── POST /api/v1/video/jobs ───────────────────────────────────────────────────

@router.post(
    "",
    response_model=VideoJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_video_job(
    request: VideoJobCreateRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoJobCreateResponse:
    """
    Queue a video creation job dispatched from local_edzaxisvideo.

    Returns 202 Accepted immediately.
    Poll GET /api/v1/video/jobs/{job_id} for status + output_url.
    """
    log.info(
        "video_job_received",
        tenant_id=str(tenant.id),
        moodle_job_id=request.job_id,
        video_type=request.video_type,
    )

    # ── Idempotency check ─────────────────────────────────────────────────────
    existing = await _get_existing_job(db, tenant.id, request.job_id)

    if existing:
        if existing.status in _ACTIVE_STATUSES:
            log.info(
                "video_job_already_active",
                job_id=str(existing.id),
                status=existing.status,
            )
            return VideoJobCreateResponse(
                job_id=str(existing.id),
                moodle_job_id=existing.moodle_job_id,
                status=existing.status,
                message=f"Job already {existing.status}. Poll for status.",
            )

        if existing.status == VideoJobStatus.DONE.value:
            return VideoJobCreateResponse(
                job_id=str(existing.id),
                moodle_job_id=existing.moodle_job_id,
                status=existing.status,
                message="Job already completed.",
            )

        # status == FAILED (or any other terminal) — reset and retry
        log.info("video_job_retrying_failed", job_id=str(existing.id))
        existing.status       = VideoJobStatus.QUEUED.value
        existing.progress     = 0
        existing.progress_msg = "Queued (retry)"
        existing.error_message = None
        existing.output_url    = None
        existing.thumbnail_url = None
        existing.preview_url   = None
        existing.celery_task_id = None
        existing.started_at    = None
        existing.completed_at  = None
        existing.settings      = request.settings.model_dump(by_alias=True)
        existing.script        = request.script
        existing.callback_url  = request.callback_url
        await db.flush()
        video_job = existing

    else:
        # ── Create new VideoJob row ───────────────────────────────────────────
        video_job = VideoJob(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            moodle_job_id=request.job_id,
            video_type=request.video_type,
            title=request.title,
            script=request.script,
            language=request.language,
            settings=request.settings.model_dump(by_alias=True),
            status=VideoJobStatus.QUEUED.value,
            progress=0,
            progress_msg="Queued",
            callback_url=request.callback_url,
        )
        db.add(video_job)
        await db.flush()

    # ── Dispatch Celery task ──────────────────────────────────────────────────
    from app.tasks.celery_app import celery_app
    task = celery_app.send_task(
        "app.tasks.render_video.render_video",
        kwargs={"video_job_id": str(video_job.id)},
        queue="video",
    )

    video_job.celery_task_id = task.id
    await db.commit()

    log.info(
        "video_job_queued",
        job_id=str(video_job.id),
        celery_task_id=task.id,
        video_type=request.video_type,
        moodle_job_id=request.job_id,
    )

    return VideoJobCreateResponse(
        job_id=str(video_job.id),
        moodle_job_id=video_job.moodle_job_id,
        status=VideoJobStatus.QUEUED.value,
        message=f"Video job queued. Poll /api/v1/video/jobs/{video_job.id} for status.",
    )


# ── GET /api/v1/video/jobs/{job_id} ──────────────────────────────────────────

@router.get(
    "/{job_id}",
    response_model=VideoJobStatusResponse,
)
async def get_video_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoJobStatusResponse:
    """
    Poll the status of a video creation job.

    job_id accepts:
      - The internal UUID returned by POST (e.g. "550e8400-e29b-41d4-a716-446655440000")
      - The integer moodle_job_id as a string (e.g. "42")

    Returns output_url and thumbnail_url when status == "done".
    Returns preview_url when status == "preview_ready".
    """
    job = await _lookup_job(db, tenant.id, job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video job '{job_id}' not found for this tenant.",
        )

    return VideoJobStatusResponse(
        job_id=str(job.id),
        moodle_job_id=job.moodle_job_id,
        video_type=job.video_type,
        status=job.status,
        progress=job.progress,
        progress_message=job.progress_msg,
        output_url=job.output_url,
        thumbnail_url=job.thumbnail_url,
        preview_url=job.preview_url,
        duration_seconds=job.duration_sec,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


# ── POST /api/v1/video/jobs/{job_id}/preview ─────────────────────────────────

@router.post(
    "/{job_id}/preview",
    response_model=VideoJobPreviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_video_preview(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoJobPreviewResponse:
    """
    Request a 30-second preview clip for human review before the full render.

    Allowed from statuses: queued, failed, preview_ready (re-preview), approved.
    Not allowed if job is already processing, preview_pending, or done.

    The preview Celery task runs the renderer capped at 30 s and stores
    the result in job.preview_url.  Poll GET /{job_id} until
    status == "preview_ready".
    """
    job = await _lookup_job(db, tenant.id, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video job '{job_id}' not found for this tenant.",
        )

    # Guard: don't queue a preview if already running
    _BLOCKED_FOR_PREVIEW = {
        VideoJobStatus.PROCESSING.value,
        VideoJobStatus.PREVIEW_PENDING.value,
        VideoJobStatus.DONE.value,
    }
    if job.status in _BLOCKED_FOR_PREVIEW:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot request preview: job is currently '{job.status}'. "
                f"Allowed from: queued, failed, preview_ready, approved."
            ),
        )

    # Reset to preview_pending and dispatch preview task
    job.status        = VideoJobStatus.PREVIEW_PENDING.value
    job.progress      = 0
    job.progress_msg  = "Preview queued"
    job.error_message = None
    job.preview_url   = None
    await db.flush()

    from app.tasks.celery_app import celery_app
    task = celery_app.send_task(
        "app.tasks.preview_video.generate_video_preview",
        kwargs={"video_job_id": str(job.id)},
        queue="video",
    )
    job.celery_task_id = task.id
    await db.commit()

    log.info(
        "video_preview_queued",
        job_id=str(job.id),
        celery_task_id=task.id,
    )

    return VideoJobPreviewResponse(
        job_id=str(job.id),
        moodle_job_id=job.moodle_job_id,
        status=job.status,
        message=(
            f"Preview render queued. "
            f"Poll /api/v1/video/jobs/{job.id} until status == 'preview_ready'."
        ),
    )


# ── POST /api/v1/video/jobs/{job_id}/approve ─────────────────────────────────

@router.post(
    "/{job_id}/approve",
    response_model=VideoJobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def approve_video_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoJobCreateResponse:
    """
    Approve the preview and trigger the full video render.

    Allowed only when status == "preview_ready".
    Transitions: preview_ready → queued → processing → done | failed

    Returns 202 Accepted.  Poll GET /{job_id} for final output_url.
    """
    job = await _lookup_job(db, tenant.id, job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video job '{job_id}' not found for this tenant.",
        )

    if job.status != VideoJobStatus.PREVIEW_READY.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Cannot approve: job status is '{job.status}'. "
                f"Approval requires status == 'preview_ready'."
            ),
        )

    # Reset and queue for full render
    job.status        = VideoJobStatus.QUEUED.value
    job.progress      = 0
    job.progress_msg  = "Approved — full render queued"
    job.error_message = None
    job.output_url    = None
    job.thumbnail_url = None
    job.started_at    = None
    job.completed_at  = None
    await db.flush()

    from app.tasks.celery_app import celery_app
    task = celery_app.send_task(
        "app.tasks.render_video.render_video",
        kwargs={"video_job_id": str(job.id)},
        queue="video",
    )
    job.celery_task_id = task.id
    await db.commit()

    log.info(
        "video_job_approved",
        job_id=str(job.id),
        celery_task_id=task.id,
    )

    return VideoJobCreateResponse(
        job_id=str(job.id),
        moodle_job_id=job.moodle_job_id,
        status=VideoJobStatus.QUEUED.value,
        message=(
            f"Full render queued after approval. "
            f"Poll /api/v1/video/jobs/{job.id} for output_url."
        ),
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_existing_job(
    db: AsyncSession, tenant_id: uuid.UUID, moodle_job_id: int
) -> VideoJob | None:
    result = await db.execute(
        select(VideoJob).where(
            VideoJob.tenant_id == tenant_id,
            VideoJob.moodle_job_id == moodle_job_id,
        )
    )
    return result.scalar_one_or_none()


async def _lookup_job(
    db: AsyncSession, tenant_id: uuid.UUID, job_id: str
) -> VideoJob | None:
    """Accepts UUID string or integer moodle_job_id string."""
    try:
        job_uuid = uuid.UUID(job_id)
        result = await db.execute(
            select(VideoJob).where(
                VideoJob.id == job_uuid,
                VideoJob.tenant_id == tenant_id,
            )
        )
        return result.scalar_one_or_none()
    except ValueError:
        pass

    try:
        moodle_id = int(job_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid job_id: '{job_id}'. Must be a UUID or integer.",
        )

    result = await db.execute(
        select(VideoJob).where(
            VideoJob.moodle_job_id == moodle_id,
            VideoJob.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


# ── GET /api/v1/video/jobs (list) ─────────────────────────────────────────────

from sqlalchemy import func as _func   # avoid name collision with FastAPI func

@router.get(
    "",
    response_model=VideoJobListResponse,
)
async def list_video_jobs(
    status: str | None = None,
    video_type: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> VideoJobListResponse:
    """
    Paginated list of video jobs for this tenant.

    Query params:
      status      — filter by status value (e.g. queued, processing, done, failed, preview_ready)
      video_type  — filter by video_type slug (e.g. explainer, conversational, auto)
      page        — 1-based page number (default 1)
      page_size   — items per page, 1–100 (default 20)

    Results are ordered by created_at DESC (newest first).
    """
    from fastapi import Query as _Q
    # clamp page_size
    page_size = max(1, min(100, page_size))
    page      = max(1, page)

    base_q = select(VideoJob).where(VideoJob.tenant_id == tenant.id)
    if status:
        base_q = base_q.where(VideoJob.status == status)
    if video_type:
        base_q = base_q.where(VideoJob.video_type == video_type)

    # total count
    count_q = select(_func.count()).select_from(base_q.subquery())
    total: int = (await db.execute(count_q)).scalar_one()

    # paginated rows
    offset = (page - 1) * page_size
    rows_q = (
        base_q
        .order_by(VideoJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = (await db.execute(rows_q)).scalars().all()

    items = [
        VideoJobStatusResponse(
            job_id=str(j.id),
            moodle_job_id=j.moodle_job_id,
            video_type=j.video_type,
            status=j.status,
            progress=j.progress,
            progress_message=j.progress_msg,
            output_url=j.output_url,
            thumbnail_url=j.thumbnail_url,
            preview_url=j.preview_url,
            duration_seconds=j.duration_sec,
            error_message=j.error_message,
            created_at=j.created_at,
            started_at=j.started_at,
            completed_at=j.completed_at,
        )
        for j in rows
    ]

    return VideoJobListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(rows)) < total,
    )
