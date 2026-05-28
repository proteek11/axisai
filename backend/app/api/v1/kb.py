"""
KB (Knowledge Base) API — admin uploads support documents for the Support chatbot.

Admin uploads PDFs/URLs via POST /kb/ingest.
The document is extracted, chunked, embedded, and stored in axis_kb_chunks.
When a chat session uses chat_mode="support", RAG searches this collection.

Endpoints:
  POST /kb/ingest          — ingest a URL-based KB document
  POST /kb/ingest/file     — ingest an uploaded file
  GET  /kb/items           — list all KB items for the tenant
  GET  /kb/items/{id}      — get a single KB item
  PUT  /kb/items/{id}      — update metadata / toggle active
  DELETE /kb/items/{id}    — soft-delete (deactivate + remove vectors)
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_tenant
from app.models.kb import KnowledgeBaseItem, KBDocType, KBItemStatus
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.tenant import Tenant
from app.schemas.admin import KBIngestRequest, KBIngestResponse, KBItemResponse


class KBItemUpdateRequest(BaseModel):
    """Body for PUT/POST /kb/items/{id} — all fields optional (partial update)."""
    title: str | None = None
    doc_type: str | None = None
    is_active: bool | None = None

router = APIRouter()
log = structlog.get_logger(__name__)


@router.post("/ingest", response_model=KBIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def kb_ingest_url(
    req: KBIngestRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBIngestResponse:
    """
    Ingest a KB document from a URL.
    Creates a KBItem + ProcessingJob and dispatches Celery task.
    The Celery task extracts, chunks, embeds into axis_kb_chunks.
    """
    # Validate doc_type
    try:
        KBDocType(req.doc_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid doc_type '{req.doc_type}'. Valid values: {[e.value for e in KBDocType]}",
        )

    kb_item = KnowledgeBaseItem(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        title=req.title,
        doc_type=req.doc_type,
        source_url=req.source_url,
        status=KBItemStatus.PENDING.value,
        is_active=True,
        uploaded_by_moodle_user_id=req.uploaded_by_moodle_user_id,
        processing_metadata={"language": req.language},
    )
    db.add(kb_item)
    await db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=None,  # KB jobs don't have a content_item (separate table)
        tenant_id=tenant.id,
        job_type=JobType.KB_INGEST,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "kb_item_id": str(kb_item.id),
            "source_url": req.source_url,
            "doc_type": req.doc_type,
            "language": req.language,
            "title": req.title,
        },
    )
    db.add(job)
    await db.flush()

    # Dispatch Celery task
    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_kb.run_kb_pipeline",
        kwargs={
            "job_id": str(job.id),
            "kb_item_id": str(kb_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    await db.commit()
    log.info("kb_ingest_queued", kb_item_id=str(kb_item.id), title=req.title, doc_type=req.doc_type)

    return KBIngestResponse(
        kb_item_id=str(kb_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"KB document queued for processing. Poll /api/v1/jobs/{job.id} for status.",
    )


@router.post("/ingest/file", response_model=KBIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def kb_ingest_file(
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form(default="support"),
    language: str = Form(default="en"),
    uploaded_by_moodle_user_id: int | None = Form(None),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBIngestResponse:
    """Ingest a KB document from an uploaded file (PDF)."""
    import os
    import aiofiles
    from app.config import settings

    file_bytes = await file.read()
    from app.api.v1.axis_admin import get_upload_limit_bytes
    _max_bytes = await get_upload_limit_bytes(db)
    _max_mb = _max_bytes // (1024 * 1024)
    if len(file_bytes) > _max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {_max_mb} MB. Ask your admin to increase the limit.",
        )

    os.makedirs(settings.upload_dir, exist_ok=True)
    temp_filename = f"kb_{uuid.uuid4()}_{file.filename}"
    temp_path = os.path.join(settings.upload_dir, temp_filename)

    async with aiofiles.open(temp_path, "wb") as f:
        await f.write(file_bytes)

    req = KBIngestRequest(
        source_url=f"file://{temp_path}",
        title=title or file.filename,
        doc_type=doc_type,
        language=language,
        uploaded_by_moodle_user_id=uploaded_by_moodle_user_id,
    )
    return await kb_ingest_url(req, db, tenant)


@router.get("/items", response_model=list[KBItemResponse])
async def list_kb_items(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> list[KBItemResponse]:
    """List all KB items for this tenant."""
    query = select(KnowledgeBaseItem).where(KnowledgeBaseItem.tenant_id == tenant.id)
    if not include_inactive:
        query = query.where(KnowledgeBaseItem.is_active == True)
    query = query.order_by(KnowledgeBaseItem.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()
    return [KBItemResponse.model_validate(i) for i in items]


@router.get("/items/{kb_item_id}", response_model=KBItemResponse)
async def get_kb_item(
    kb_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBItemResponse:
    result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.id == kb_item_id,
            KnowledgeBaseItem.tenant_id == tenant.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="KB item not found.")
    return KBItemResponse.model_validate(item)


async def update_kb_item(
    kb_item_id: uuid.UUID,
    req: KBItemUpdateRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBItemResponse:
    """Update KB item metadata or toggle active state.

    Accepts both PUT and POST (POST alias exists because Moodle's curl wrapper
    cannot reliably send PUT).
    """
    result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.id == kb_item_id,
            KnowledgeBaseItem.tenant_id == tenant.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="KB item not found.")

    is_active_changed = req.is_active is not None and req.is_active != item.is_active

    if req.title is not None:
        item.title = req.title
    if req.doc_type is not None:
        item.doc_type = req.doc_type
    if req.is_active is not None:
        item.is_active = req.is_active

    await db.commit()
    await db.refresh(item)

    # Sync is_active into Qdrant chunk payloads so the chat retriever filter works.
    # The retriever filters on is_active=True; without this sync deactivated items
    # would still appear in support chat results (and vice-versa).
    if is_active_changed:
        try:
            from app.core.qdrant import get_qdrant
            from app.config import settings as _settings
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant = get_qdrant()
            await qdrant.set_payload(
                collection_name=_settings.qdrant_collection_kb_chunks,
                payload={"is_active": item.is_active},
                points_selector=Filter(
                    must=[FieldCondition(
                        key="kb_item_id",
                        match=MatchValue(value=str(kb_item_id)),
                    )]
                ),
            )
            log.info(
                "kb_qdrant_is_active_synced",
                kb_item_id=str(kb_item_id),
                is_active=item.is_active,
            )
        except Exception as e:
            # Non-fatal: Qdrant sync failure shouldn't break the API response.
            log.warning("kb_qdrant_is_active_sync_failed", error=str(e))

    return KBItemResponse.model_validate(item)


# Register for both PUT and POST (Moodle curl compat)
router.add_api_route(
    "/items/{kb_item_id}",
    update_kb_item,
    methods=["PUT", "POST"],
    response_model=KBItemResponse,
    tags=["Knowledge Base"],
    summary="Update KB item metadata / toggle active (PUT or POST)",
)


@router.delete("/items/{kb_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_item(
    kb_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """
    Soft-delete a KB item: marks is_active=False and status=DELETED.
    Qdrant vectors are removed by the maintenance Celery task.
    """
    result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.id == kb_item_id,
            KnowledgeBaseItem.tenant_id == tenant.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="KB item not found.")

    item.is_active = False
    item.status = KBItemStatus.DELETED.value
    await db.commit()
    log.info("kb_item_deleted", kb_item_id=str(kb_item_id), tenant_id=str(tenant.id))


# ---------------------------------------------------------------------------
# Reindex (update content of existing KB item without changing its UUID)
# ---------------------------------------------------------------------------

class KBReindexRequest(BaseModel):
    """Body for POST /kb/items/{id}/reindex — re-ingest new text for an existing item."""
    text: str
    title: str | None = None
    doc_type: str | None = None
    uploaded_by_moodle_user_id: int | None = None


@router.post("/items/{kb_item_id}/reindex", response_model=KBIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def reindex_kb_item(
    kb_item_id: uuid.UUID,
    req: KBReindexRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBIngestResponse:
    """Re-ingest new text content for an existing KB item.

    Keeps the same kb_item_id UUID — does NOT create a new row.
    Old Qdrant vectors for this item are deleted by the Celery task before
    inserting the new chunks, so the item is fully re-indexed with new content.

    Used by Moodle's KB edit flow so admins can update text without losing
    the item's identity, toggle state, or history.
    """
    result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.id == kb_item_id,
            KnowledgeBaseItem.tenant_id == tenant.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="KB item not found.")

    # Apply optional metadata updates
    if req.title is not None:
        item.title = req.title
    if req.doc_type is not None:
        try:
            KBDocType(req.doc_type)
            item.doc_type = req.doc_type
        except ValueError:
            pass  # ignore invalid doc_type — keep existing

    item.status = KBItemStatus.PENDING.value

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=None,
        tenant_id=tenant.id,
        job_type=JobType.KB_INGEST,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued for re-index",
        job_config={
            "kb_item_id": str(kb_item_id),
            "inline_text": req.text,
            "doc_type": item.doc_type,
            "title": item.title,
            "reindex": True,          # signals the worker to delete old vectors first
        },
    )
    db.add(job)
    await db.flush()
    await db.commit()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_kb.run_kb_pipeline",
        kwargs={
            "job_id": str(job.id),
            "kb_item_id": str(kb_item_id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    log.info("kb_reindex_queued", kb_item_id=str(kb_item_id), title=item.title)

    return KBIngestResponse(
        kb_item_id=str(kb_item_id),
        job_id=str(job.id),
        status="queued",
        message=f"Re-index queued. Poll /api/v1/jobs/{job.id} for status.",
    )


@router.post("/items/{kb_item_id}/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_item_post(
    kb_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """POST alias for DELETE /items/{id}.

    Moodle's curl wrapper cannot reliably send DELETE — CURLOPT_CUSTOMREQUEST
    is overridden by $curl->post(). PHP calls /items/{id}/delete via POST instead.
    """
    return await delete_kb_item(kb_item_id, db, tenant)


# ---------------------------------------------------------------------------
# Backfill is_active on existing Qdrant chunks (one-time migration helper)
# ---------------------------------------------------------------------------

@router.post("/backfill-active", status_code=200)
async def backfill_kb_active(
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict:
    """
    Stamp is_active=True onto every Qdrant chunk that belongs to an active
    KB item for this tenant but is missing the is_active payload field.

    Safe to call multiple times — set_payload is idempotent.
    Use this once after upgrading to the version that added is_active to the
    KB chunk payload, to fix items that were ingested before the change.
    """
    from app.core.qdrant import get_qdrant
    from app.config import settings as _settings
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    # Fetch all active + ready KB items for this tenant
    active_items_result = await db.execute(
        select(KnowledgeBaseItem).where(
            KnowledgeBaseItem.tenant_id == tenant.id,
            KnowledgeBaseItem.is_active == True,
            KnowledgeBaseItem.status == KBItemStatus.READY.value,
        )
    )
    active_items = active_items_result.scalars().all()

    if not active_items:
        return {"updated_items": 0, "message": "No active KB items found."}

    qdrant = get_qdrant()
    updated = 0

    for item in active_items:
        try:
            await qdrant.set_payload(
                collection_name=_settings.qdrant_collection_kb_chunks,
                payload={"is_active": True},
                points_selector=Filter(
                    must=[
                        FieldCondition(key="kb_item_id", match=MatchValue(value=str(item.id))),
                        FieldCondition(key="tenant_id",  match=MatchValue(value=str(tenant.id))),
                    ]
                ),
            )
            updated += 1
            log.info("kb_backfill_active", kb_item_id=str(item.id), title=item.title)
        except Exception as e:
            log.warning("kb_backfill_active_failed", kb_item_id=str(item.id), error=str(e))

    return {
        "updated_items": updated,
        "total_active_items": len(active_items),
        "message": f"Stamped is_active=True on chunks for {updated}/{len(active_items)} active KB items.",
    }


# ---------------------------------------------------------------------------
# Text ingestion (plain-text content, no URL required)
# ---------------------------------------------------------------------------

class KBIngestTextRequest(BaseModel):
    """Ingest plain-text content directly (no URL needed)."""
    text: str
    title: str
    doc_type: str = "support"
    language: str = "en"
    uploaded_by_moodle_user_id: int | None = None


@router.post("/ingest/text", response_model=KBIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def kb_ingest_text(
    req: KBIngestTextRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBIngestResponse:
    """Ingest plain-text content into the KB.

    Passes text inline in job_config — no temp file written at API level.
    This avoids filesystem-sharing issues when the Celery worker runs in a
    different process or container than the FastAPI server.
    The worker writes its own temp file locally if needed (e.g. for PDF extractor),
    but for plain text it uses the inline content directly.
    """
    try:
        KBDocType(req.doc_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid doc_type '{req.doc_type}'. Valid: {[e.value for e in KBDocType]}",
        )

    kb_item = KnowledgeBaseItem(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        title=req.title,
        doc_type=req.doc_type,
        source_url=None,          # no URL — content is inline
        status=KBItemStatus.PENDING.value,
        is_active=True,
        uploaded_by_moodle_user_id=req.uploaded_by_moodle_user_id,
        processing_metadata={"language": req.language, "source": "text_paste"},
    )
    db.add(kb_item)
    await db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=None,
        tenant_id=tenant.id,
        job_type=JobType.KB_INGEST,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "kb_item_id": str(kb_item.id),
            "inline_text": req.text,   # ← text carried in job_config, no file needed
            "doc_type": req.doc_type,
            "language": req.language,
            "title": req.title,
        },
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_kb.run_kb_pipeline",
        kwargs={
            "job_id": str(job.id),
            "kb_item_id": str(kb_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    await db.commit()
    log.info("kb_text_ingest_queued", kb_item_id=str(kb_item.id), title=req.title)

    return KBIngestResponse(
        kb_item_id=str(kb_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"Text content queued for processing. Poll /api/v1/jobs/{job.id} for status.",
    )


# ---------------------------------------------------------------------------
# Base64 file ingestion (Moodle cannot do multipart uploads via JS AJAX)
# ---------------------------------------------------------------------------

class KBIngestBase64Request(BaseModel):
    """Ingest a file passed as base64-encoded content."""
    filename: str
    file_base64: str    # standard base64, no data-URL prefix
    title: str
    doc_type: str = "support"
    language: str = "en"
    uploaded_by_moodle_user_id: int | None = None


@router.post("/ingest/base64", response_model=KBIngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def kb_ingest_base64(
    req: KBIngestBase64Request,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> KBIngestResponse:
    """Ingest a file encoded as base64 JSON body.

    Moodle's external function API cannot send multipart/form-data, so
    JavaScript reads the file as base64 and POSTs it as JSON instead.

    The base64 payload is validated here (size check, decode check) but the
    temp file is written by the Celery worker — not here — so the file always
    exists on the same machine where extraction runs.
    """
    import base64 as _base64
    from app.config import settings

    # Validate before queuing (fast fail)
    try:
        file_bytes = _base64.b64decode(req.file_base64)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid base64 file data")

    from app.api.v1.axis_admin import get_upload_limit_bytes
    _max_bytes = await get_upload_limit_bytes(db)
    _max_mb = _max_bytes // (1024 * 1024)
    if len(file_bytes) > _max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum upload size of {_max_mb} MB. Ask your admin to increase the limit.",
        )

    title = req.title or req.filename

    try:
        KBDocType(req.doc_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid doc_type '{req.doc_type}'. Valid: {[e.value for e in KBDocType]}",
        )

    kb_item = KnowledgeBaseItem(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        title=title,
        doc_type=req.doc_type,
        source_url=None,
        status=KBItemStatus.PENDING.value,
        is_active=True,
        uploaded_by_moodle_user_id=req.uploaded_by_moodle_user_id,
        processing_metadata={"language": req.language, "filename": req.filename, "source": "file_upload"},
    )
    db.add(kb_item)
    await db.flush()

    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=None,
        tenant_id=tenant.id,
        job_type=JobType.KB_INGEST,
        status=JobStatus.QUEUED,
        progress=0,
        progress_message="Queued",
        job_config={
            "kb_item_id": str(kb_item.id),
            "file_base64": req.file_base64,   # ← file carried inline; worker writes temp file
            "filename": req.filename,
            "doc_type": req.doc_type,
            "language": req.language,
            "title": title,
        },
    )
    db.add(job)
    await db.flush()

    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_kb.run_kb_pipeline",
        kwargs={
            "job_id": str(job.id),
            "kb_item_id": str(kb_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="default",
    )

    await db.commit()
    log.info("kb_file_ingest_queued", kb_item_id=str(kb_item.id), filename=req.filename)

    return KBIngestResponse(
        kb_item_id=str(kb_item.id),
        job_id=str(job.id),
        status="queued",
        message=f"File queued for processing. Poll /api/v1/jobs/{job.id} for status.",
    )
