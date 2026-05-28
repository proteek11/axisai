"""
POST /api/v1/ingest — submit content for AI processing.

Accepts a URL (PDF, YouTube, Vimeo, etc.) or a file upload.
Creates a ContentItem + ProcessingJob, dispatches Celery task, returns immediately.
Client polls GET /api/v1/jobs/{job_id} for status.
"""
import hashlib
import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import FileTooLargeError, UnsupportedContentTypeError
from app.core.security import get_current_tenant
from app.config import settings
from app.models.content import ContentItem, ContentStatus, ContentType
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.tenant import Tenant
from app.schemas.ingest import IngestURLRequest, IngestResponse, StructuredIngestRequest
from app.utils.url_utils import detect_content_type_from_url

router = APIRouter()
log = structlog.get_logger(__name__)

SUPPORTED_CONTENT_TYPES = {ct.value for ct in ContentType} - {ContentType.UNKNOWN.value}


@router.post("", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_url(
    request: IngestURLRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> IngestResponse:
    """
    Submit a content URL for processing.

    Returns 202 Accepted immediately — processing happens asynchronously.
    Poll GET /api/v1/jobs/{job_id} for status.

    If the same (tenant, moodle_cmid) already exists:
    - If status=READY and content hasn't changed: returns existing content_item_id
    - If status=STALE or hash will change: creates a new job to reprocess
    - If status=PROCESSING: returns the in-progress job
    """
    # ── Validate content type ─────────────────────────────────────────────
    content_type_str = request.content_type.lower()
    if content_type_str not in SUPPORTED_CONTENT_TYPES:
        raise UnsupportedContentTypeError(
            f"Unsupported content type: '{content_type_str}'",
            detail={"supported": list(SUPPORTED_CONTENT_TYPES)},
        )

    try:
        content_type = ContentType(content_type_str)
    except ValueError:
        content_type = ContentType.UNKNOWN

    # ── Check for existing ContentItem ────────────────────────────────────
    result = await db.execute(
        select(ContentItem).where(
            ContentItem.tenant_id == tenant.id,
            ContentItem.moodle_cmid == request.moodle_cmid,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Already processing — return existing job (or reset if stuck)
        if existing.status == ContentStatus.PROCESSING:
            active_job = await _get_active_job(db, existing.id)
            if active_job:
                return IngestResponse(
                    content_item_id=str(existing.id),
                    job_id=str(active_job.id),
                    status="processing",
                    message="Content is already being processed. Poll the job ID for status.",
                )
            # No active job found — pipeline died/got stuck. Reset and requeue.
            log.warning(
                "ingest_stuck_reset",
                content_item_id=str(existing.id),
                message="Content stuck in PROCESSING with no active job — resetting to PENDING",
            )
            existing.status = ContentStatus.PENDING
            content_item = existing
            # Fall through to create a new job below

        # For html_page content, detect changes via HTML hash (URL stays the same
        # when a teacher edits the page in Moodle — only the HTML changes).
        incoming_html_hash: str | None = None
        if content_type_str == "html_page":
            html_body = request.metadata.get("html_content", "")
            if html_body:
                incoming_html_hash = hashlib.sha256(
                    html_body.encode("utf-8")
                ).hexdigest()

        url_changed = existing.source_url != request.source_url
        html_changed = (
            incoming_html_hash is not None
            and existing.content_hash is not None
            and existing.content_hash != incoming_html_hash
        )

        # Already ready — reprocess only if something actually changed
        if existing.status == ContentStatus.READY and not url_changed and not html_changed:
            return IngestResponse(
                content_item_id=str(existing.id),
                job_id="",
                status="ready",
                message="Content already processed. Use POST /content/{id}/generate to run specific tasks.",
            )

        # URL changed, HTML changed, or content is stale — reprocess
        existing.status = ContentStatus.PENDING
        existing.source_url = request.source_url
        existing.title = request.title or existing.title
        content_item = existing

    else:
        # Create new ContentItem
        content_item = ContentItem(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            moodle_course_id=request.moodle_course_id,
            moodle_cmid=request.moodle_cmid,
            moodle_section_id=request.moodle_section_id,
            content_type=content_type,
            title=request.title,
            source_url=request.source_url,
            language=request.options.language,
            status=ContentStatus.PENDING,
            processing_config={
                "tasks": request.options.tasks,
                "chunk_size": request.options.chunk_size,
                "chunk_overlap": request.options.chunk_overlap,
                "chunking_strategy": request.options.chunking_strategy,
            },
            moodle_metadata={
                "moodle_user_id": request.moodle_user_id,
                **request.metadata,
            },
        )
        db.add(content_item)

    # ── Create ProcessingJob ──────────────────────────────────────────────
    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=tenant.id,
        job_type=JobType.FULL_PIPELINE,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "tasks": request.options.tasks,
            "options": {
                "chunk_size": request.options.chunk_size,
                "chunk_overlap": request.options.chunk_overlap,
                "chunking_strategy": request.options.chunking_strategy,
                "language": request.options.language,
            },
            "moodle_user_id": request.moodle_user_id,
        },
    )
    db.add(job)
    await db.flush()  # Get IDs before dispatching task

    # ── Dispatch Celery task ──────────────────────────────────────────────
    # FIX 2026-03-28: Replaced run_pipeline.apply_async() with celery_app.send_task().
    # Error: kombu.exceptions.OperationalError: [Errno 61] Connection refused —
    # Celery tried to connect via AMQP (RabbitMQ) instead of Redis.
    # Reason: run_pipeline is decorated with @shared_task, which binds to whichever
    # Celery app is "current" at dispatch time. In the FastAPI process celery_app.py
    # was never imported, so shared_task fell back to Celery's default app, which
    # uses amqp://guest:guest@localhost// as its broker (RabbitMQ default).
    # Fix: Dispatch via celery_app.send_task(name, ...) so the broker URL always
    # comes from our configured celery_app (Redis), regardless of import order.
    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    await db.commit()

    log.info(
        "ingest_queued",
        job_id=str(job.id),
        content_item_id=str(content_item.id),
        content_type=content_type_str,
        cmid=request.moodle_cmid,
        tasks=request.options.tasks,
    )

    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Job queued. Poll /api/v1/jobs/{job.id} for status.",
    )


@router.post("/file", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_file(
    file: UploadFile = File(...),
    content_type: str = Form(...),
    moodle_course_id: int = Form(...),
    moodle_cmid: int = Form(...),
    moodle_user_id: int | None = Form(None),
    title: str | None = Form(None),
    tasks: str = Form(default="summary"),  # comma-separated
    language: str = Form(default="en"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> IngestResponse:
    """
    Submit a file upload for processing.
    File is saved to temp storage; URL-based ingest is preferred for large files.
    """
    import os
    import aiofiles

    # Check file size (limit from admin settings, falls back to config default)
    from app.api.v1.axis_admin import get_upload_limit_bytes
    _max_bytes = await get_upload_limit_bytes(db)
    _max_mb = _max_bytes // (1024 * 1024)
    file_bytes = await file.read()
    if len(file_bytes) > _max_bytes:
        raise FileTooLargeError(
            f"File exceeds maximum upload size of {_max_mb} MB. Ask your admin to increase the limit.",
            detail={"size_mb": round(len(file_bytes) / 1024 / 1024, 1), "limit_mb": _max_mb},
        )

    # Persist the uploaded file via the storage abstraction.
    # Local backend → writes to /data/axis/uploads/{uuid}_{name}, returns file:// URL.
    # S3 backend    → uploads to S3, returns public/CDN HTTPS URL.
    # The PDF extractor handles both file:// (disk read) and https:// (httpx download
    # with follow_redirects=True), so no extractor changes are needed.
    import asyncio as _asyncio
    from app.core import storage as _storage

    safe_name = f"{uuid.uuid4()}_{file.filename}"
    relative_path = f"uploads/{safe_name}"

    # save_bytes is synchronous (boto3 blocking I/O) — run in executor
    loop = _asyncio.get_event_loop()
    file_url = await loop.run_in_executor(
        None, _storage.save_bytes, relative_path, file_bytes
    )

    from app.schemas.ingest import IngestOptions
    url_request = IngestURLRequest(
        source_url=file_url,
        content_type=content_type,
        moodle_course_id=moodle_course_id,
        moodle_cmid=moodle_cmid,
        moodle_user_id=moodle_user_id,
        title=title or file.filename,
        options=IngestOptions(
            tasks=tasks.split(","),
            language=language,
        ),
    )

    return await ingest_url(url_request, db, tenant)


@router.post("/structured", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_structured(
    request: StructuredIngestRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> IngestResponse:
    """
    Ingest pre-extracted structured content (SCORM/H5P).

    Called by the Moodle edzaiaxisfront PHP plugin after SCORM extraction.
    PHP does the heavy SCORM parsing; this endpoint receives clean chunk JSON.
    Skips the extraction phase — goes straight to: merge text → chunk → embed → generate.

    The full_text is assembled from chunks: title + text + audio_transcript per chunk.
    A 'synthetic' source_url is constructed from tenant + cmid for dedup purposes.
    """
    # Build a synthetic "URL" for dedup — same cmid always deduplicates
    synthetic_url = f"structured://{tenant.id}/{request.moodle_cmid}"

    # Assemble full text from chunks (preserve sequence order)
    text_parts = []
    for chunk in sorted(request.chunks, key=lambda c: c.sequence):
        if chunk.title:
            text_parts.append(f"## {chunk.title}")
        if chunk.text:
            text_parts.append(chunk.text)
        if chunk.audio_transcript:
            text_parts.append(f"[Audio]: {chunk.audio_transcript}")
    full_text = "\n\n".join(text_parts)

    # Check for existing ContentItem (same tenant + cmid)
    result = await db.execute(
        select(ContentItem).where(
            ContentItem.tenant_id == tenant.id,
            ContentItem.moodle_cmid == request.moodle_cmid,
        )
    )
    import hashlib
    content_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    existing = result.scalar_one_or_none()

    if existing and existing.status == ContentStatus.READY and existing.content_hash == content_hash:
        return IngestResponse(
            content_item_id=str(existing.id),
            job_id="",
            status="ready",
            message="Content already processed and unchanged. Use POST /content/{id}/generate to run specific tasks.",
        )

    if existing:
        existing.status = ContentStatus.PENDING
        existing.source_url = synthetic_url
        existing.title = request.title
        existing.content_hash = content_hash
        content_item = existing
    else:
        content_item = ContentItem(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            moodle_course_id=request.moodle_course_id,
            moodle_cmid=request.moodle_cmid,
            moodle_section_id=request.moodle_section_id,
            content_type=ContentType(request.content_type) if request.content_type in [e.value for e in ContentType] else ContentType.UNKNOWN,
            title=request.title,
            source_url=synthetic_url,
            content_hash=content_hash,
            language=request.language,
            status=ContentStatus.PENDING,
            processing_config={
                "tasks": request.options.tasks,
                "chunk_size": request.options.chunk_size,
                "chunk_overlap": request.options.chunk_overlap,
                "chunking_strategy": request.options.chunking_strategy,
            },
            moodle_metadata={
                "moodle_user_id": request.moodle_user_id,
                "structured_ingest": True,
                "chunk_count": len(request.chunks),
                **request.metadata,
            },
        )
        db.add(content_item)

    await db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=tenant.id,
        job_type=JobType.STRUCTURED_INGEST,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "tasks": request.options.tasks,
            "full_text": full_text,           # pre-assembled text — pipeline skips extraction
            "structured": True,
            "chunks_metadata": [              # chunk titles for context threading
                {"sequence": c.sequence, "title": c.title, "type": c.chunk_type}
                for c in request.chunks
            ],
            "options": {
                "chunk_size": request.options.chunk_size,
                "chunk_overlap": request.options.chunk_overlap,
                "chunking_strategy": request.options.chunking_strategy,
                "language": request.language,
                "output_language": request.output_language,
            },
            "moodle_user_id": request.moodle_user_id,
        },
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    await db.commit()
    log.info(
        "structured_ingest_queued",
        job_id=str(job.id),
        content_item_id=str(content_item.id),
        content_type=request.content_type,
        cmid=request.moodle_cmid,
        chunk_count=len(request.chunks),
        tasks=request.options.tasks,
    )

    return IngestResponse(
        content_item_id=str(content_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Structured ingest queued. Poll /api/v1/jobs/{job.id} for status.",
    )


async def _get_active_job(db: AsyncSession, content_item_id) -> ProcessingJob | None:
    result = await db.execute(
        select(ProcessingJob)
        .where(
            ProcessingJob.content_item_id == content_item_id,
            ProcessingJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING]),
        )
        .order_by(ProcessingJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
