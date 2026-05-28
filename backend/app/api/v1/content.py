"""
Content output endpoints (read-only, for learner-facing delivery).

GET  /api/v1/content/{content_item_id}/quiz         — quiz payload (raw)
GET  /api/v1/content/{content_item_id}/mindmap
GET  /api/v1/content/{content_item_id}/objectives
GET  /api/v1/content/{content_item_id}/blooms
GET  /api/v1/content/{content_item_id}/outputs      — list all outputs
GET  /api/v1/content/{content_item_id}/transcript
POST /api/v1/content/{content_item_id}/generate

NOTE: summary, flashcards, glossary, and quiz-questions are served by the
teacher-management CRUD router (crud.py) which returns richer pool-based
responses with individual item management. Those routes supersede the plain
ai_outputs.payload routes for those three output types.

_get_output still respects edited_content overrides for the remaining output types.
"""
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ContentNotFoundError, OutputNotReadyError
from app.core.security import get_current_tenant
from app.models.content import ContentItem, ContentStatus
from app.models.job import JobStatus, JobType, ProcessingJob
from app.models.output import AIOutput, OutputStatus, OutputType
from app.models.tenant import Tenant
from app.models.transcript import Transcript
from app.schemas.output import (
    AIOutputResponse,
    ChapterItem,
    ChaptersResponse,
    ColourPalette,
    FAQItem,
    FAQResponse,
    GenerateRequest,
    InfographicResponse,
    TranscriptResponse,
    TranscriptSegment,
)

router = APIRouter()
log = structlog.get_logger(__name__)


# ── Output retrieval endpoints ─────────────────────────────────────────────────

async def _get_output(
    content_item_id: str,
    output_type: OutputType,
    language: str,
    db: AsyncSession,
    tenant: Tenant,
) -> AIOutputResponse:
    """Shared logic for all output GET endpoints."""
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    # Verify content item belongs to tenant
    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    if content_item.status == ContentStatus.PROCESSING:
        raise OutputNotReadyError(
            "Content is still being processed. Poll /api/v1/jobs/ for status."
        )

    # Get the active (latest) output for this type + language
    result = await db.execute(
        select(AIOutput)
        .where(
            AIOutput.content_item_id == item_uuid,
            AIOutput.output_type == output_type,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()

    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No {output_type} output found for this content. "
                f"Submit a generate request: POST /api/v1/content/{content_item_id}/generate"
            ),
        )

    # Serve edited_content if teacher has saved an edit; otherwise serve original payload.
    effective_payload = output.edited_content if output.is_teacher_edited else output.payload

    return AIOutputResponse(
        content_item_id=str(output.content_item_id),
        output_type=output.output_type,
        language=output.language,
        status=output.status,
        payload=effective_payload,
        model=output.model,
        provider=output.provider,
        prompt_version=output.prompt_version,
        prompt_tokens=output.prompt_tokens,
        completion_tokens=output.completion_tokens,
        confidence=output.confidence,
        quality_reviewed=output.quality_reviewed,
        quality_rating=output.quality_rating,
        is_teacher_edited=output.is_teacher_edited,
        last_edited_by=output.last_edited_by,
        last_edited_at=output.last_edited_at,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


# NOTE: GET /summary, GET /flashcards, GET /glossary are intentionally omitted here.
# They are handled by the teacher-management CRUD router (crud.py) which returns
# richer pool-based responses (FlashcardPoolResponse, GlossaryPoolResponse, SummaryResponse).
# Registering them here would create duplicate routes — content_router registers first
# so we must not shadow the richer crud.py endpoints.

@router.get("/{content_item_id}/quiz", response_model=AIOutputResponse)
async def get_quiz(
    content_item_id: str,
    language: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    return await _get_output(content_item_id, OutputType.QUIZ, language, db, tenant)


@router.get("/{content_item_id}/mindmap", response_model=AIOutputResponse)
async def get_mindmap(
    content_item_id: str,
    language: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    return await _get_output(content_item_id, OutputType.MINDMAP, language, db, tenant)


@router.get("/{content_item_id}/objectives", response_model=AIOutputResponse)
async def get_objectives(
    content_item_id: str,
    language: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    return await _get_output(content_item_id, OutputType.OBJECTIVES, language, db, tenant)


@router.get("/{content_item_id}/blooms", response_model=AIOutputResponse)
async def get_blooms(
    content_item_id: str,
    language: str = Query(default="en"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    return await _get_output(content_item_id, OutputType.BLOOMS, language, db, tenant)


@router.get("/{content_item_id}/outputs", response_model=list[AIOutputResponse])
async def list_outputs(
    content_item_id: str,
    language: str = Query(default="en"),
    include_superseded: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """List all available outputs for a content item."""
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    query = select(AIOutput).where(
        AIOutput.content_item_id == item_uuid,
        AIOutput.language == language,
    )
    if not include_superseded:
        query = query.where(AIOutput.status == OutputStatus.ACTIVE)

    result = await db.execute(query.order_by(AIOutput.output_type, AIOutput.created_at.desc()))
    outputs = result.scalars().all()

    return [
        AIOutputResponse(
            content_item_id=str(o.content_item_id),
            output_type=o.output_type,
            language=o.language,
            status=o.status,
            payload=o.payload,
            model=o.model,
            provider=o.provider,
            prompt_version=o.prompt_version,
            prompt_tokens=o.prompt_tokens,
            completion_tokens=o.completion_tokens,
            confidence=o.confidence,
            quality_reviewed=o.quality_reviewed,
            quality_rating=o.quality_rating,
            created_at=o.created_at,
            updated_at=o.updated_at,
        )
        for o in outputs
    ]


# ── Transcript ────────────────────────────────────────────────────────────────

@router.get("/{content_item_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(
    content_item_id: str,
    language: str = Query(default="en", description="Language code, e.g. 'en', 'fr'"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return the stored transcript for a video content item.

    Only available for video content types (youtube, vimeo, peertube).
    Returns 404 if the content item has no transcript (e.g. it's a PDF,
    or the video was processed before Phase 2b, or no captions were found).
    """
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    # Verify content item belongs to this tenant
    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    # Fetch transcript for requested language
    t_result = await db.execute(
        select(Transcript).where(
            Transcript.content_item_id == item_uuid,
            Transcript.language == language,
        )
    )
    transcript = t_result.scalar_one_or_none()

    if not transcript:
        # Try to find any language variant before returning 404
        any_result = await db.execute(
            select(Transcript)
            .where(Transcript.content_item_id == item_uuid)
            .order_by(Transcript.created_at.desc())
            .limit(1)
        )
        any_transcript = any_result.scalar_one_or_none()

        if any_transcript:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"No transcript found for language '{language}'. "
                    f"Available language: '{any_transcript.language}'. "
                    f"Try: GET /api/v1/content/{content_item_id}/transcript?language={any_transcript.language}"
                ),
            )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No transcript found for content item {content_item_id}. "
                "Transcripts are only available for video content (youtube, vimeo). "
                "Check that the video had captions available during processing."
            ),
        )

    # Build typed segment list
    segments = [
        TranscriptSegment(
            start_sec=seg.get("start_sec", 0.0),
            end_sec=seg.get("end_sec", 0.0),
            text=seg.get("text", ""),
        )
        for seg in (transcript.segments or [])
    ]

    return TranscriptResponse(
        content_item_id=content_item_id,
        language=transcript.language,
        source=transcript.source,
        word_count=transcript.word_count,
        segment_count=len(segments),
        full_text=transcript.full_text,
        segments=segments,
        created_at=transcript.created_at,
        updated_at=transcript.updated_at,
    )


# ── Chapters ──────────────────────────────────────────────────────────────────

@router.get("/{content_item_id}/chapters", response_model=ChaptersResponse)
async def get_chapters(
    content_item_id: str,
    language: str = Query(default="en", description="Language code, e.g. 'en', 'fr'"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return AI-generated video chapters for a content item.

    Each chapter includes:
    - title       — concise label shown in the chapters panel
    - start_sec   — seek to this value when the learner clicks the chapter
    - end_sec     — when this chapter ends (= start_sec of next chapter)
    - summary     — 1-2 sentence description of what is covered

    Only available for video content types that have timed transcripts
    (youtube, vimeo, peertube).  Returns 404 if chapters haven't been
    generated yet — trigger generation via:
      POST /api/v1/content/{content_item_id}/generate  { "tasks": ["chapters"] }
    """
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    # Verify ownership
    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    if content_item.status == ContentStatus.PROCESSING:
        raise OutputNotReadyError(
            "Content is still being processed. Poll /api/v1/jobs/ for status."
        )

    # Fetch the active chapters output for this language
    result = await db.execute(
        select(AIOutput)
        .where(
            AIOutput.content_item_id == item_uuid,
            AIOutput.output_type == OutputType.CHAPTERS,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()

    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No chapters found for this content in language '{language}'. "
                f"Trigger generation: POST /api/v1/content/{content_item_id}/generate"
                ' with body {"tasks": ["chapters"]}'
            ),
        )

    # Serve edited_content if a teacher has overridden the payload
    effective_payload = output.edited_content if output.is_teacher_edited else output.payload

    # Deserialise chapter items — handle both valid and empty/note-only payloads
    raw_chapters = effective_payload.get("chapters", [])
    chapter_items = [
        ChapterItem(
            title=ch.get("title", ""),
            start_sec=float(ch.get("start_sec", 0.0)),
            end_sec=float(ch.get("end_sec", 0.0)),
            summary=ch.get("summary", ""),
        )
        for ch in raw_chapters
        if ch.get("title")
    ]

    return ChaptersResponse(
        content_item_id=content_item_id,
        language=output.language,
        chapter_count=len(chapter_items),
        total_duration_sec=float(effective_payload.get("total_duration_sec", 0.0)),
        content_type=effective_payload.get("content_type", content_item.content_type),
        chapters=chapter_items,
        model=output.model,
        prompt_version=output.prompt_version,
        is_teacher_edited=output.is_teacher_edited,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


# ── FAQ ───────────────────────────────────────────────────────────────────────

@router.get("/{content_item_id}/faq", response_model=FAQResponse)
async def get_faq(
    content_item_id: str,
    language: str = Query(default="en", description="Language code, e.g. 'en', 'fr'"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return AI-generated FAQs for a content item.

    Each FAQ includes a question, answer, topic, and difficulty level.
    Works for all content types: video, PDF, page.

    Returns 404 if FAQs haven't been generated yet — trigger via:
      POST /api/v1/content/{content_item_id}/generate  { "tasks": ["faq"] }
    """
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    if content_item.status == ContentStatus.PROCESSING:
        raise OutputNotReadyError(
            "Content is still being processed. Poll /api/v1/jobs/ for status."
        )

    result = await db.execute(
        select(AIOutput)
        .where(
            AIOutput.content_item_id == item_uuid,
            AIOutput.output_type == OutputType.FAQ,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()

    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No FAQ found for this content in language '{language}'. "
                f"Trigger generation: POST /api/v1/content/{content_item_id}/generate"
                ' with body {"tasks": ["faq"]}'
            ),
        )

    effective_payload = output.edited_content if output.is_teacher_edited else output.payload

    raw_faqs = effective_payload.get("faqs", [])
    faq_items = [
        FAQItem(
            question=f.get("question", ""),
            answer=f.get("answer", ""),
            topic=f.get("topic", ""),
            difficulty=f.get("difficulty", "beginner"),
        )
        for f in raw_faqs
        if f.get("question") and f.get("answer")
    ]

    return FAQResponse(
        content_item_id=content_item_id,
        language=output.language,
        faq_count=len(faq_items),
        content_type=effective_payload.get("content_type", content_item.content_type),
        faqs=faq_items,
        model=output.model,
        prompt_version=output.prompt_version,
        is_teacher_edited=output.is_teacher_edited,
        last_edited_by=output.last_edited_by,
        last_edited_at=output.last_edited_at,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


# ── Infographic ────────────────────────────────────────────────────────────────

@router.get("/{content_item_id}/infographic", response_model=InfographicResponse)
async def get_infographic(
    content_item_id: str,
    language: str = Query(default="en", description="Language code, e.g. 'en', 'fr'"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return the AI-generated infographic for a content item as JSON.

    The payload contains a 'html' field with the complete, self-contained
    HTML document.  To receive the HTML document directly (for iframe embedding)
    use GET /content/{id}/infographic/html instead.

    Returns 404 if the infographic hasn't been generated yet — trigger via:
      POST /api/v1/content/{content_item_id}/generate  { "tasks": ["infographic"] }
    """
    output, content_item = await _get_infographic_output(
        content_item_id, language, db, tenant
    )

    effective_payload = output.edited_content if output.is_teacher_edited else output.payload
    html = effective_payload.get("html", "")

    palette_raw = effective_payload.get("colour_palette", {})
    palette = ColourPalette(
        primary=palette_raw.get("primary", "#1a7a8a"),
        accent1=palette_raw.get("accent1", "#f0a500"),
        accent2=palette_raw.get("accent2", "#e8f4f8"),
    )

    return InfographicResponse(
        content_item_id=content_item_id,
        language=output.language,
        content_type=effective_payload.get("content_type", content_item.content_type),
        title=effective_payload.get("title", content_item.title or ""),
        sections=effective_payload.get("sections", []),
        colour_palette=palette,
        html=html,
        html_char_count=len(html),
        model=output.model,
        prompt_version=output.prompt_version,
        is_teacher_edited=output.is_teacher_edited,
        created_at=output.created_at,
        updated_at=output.updated_at,
    )


@router.get("/{content_item_id}/infographic/html", response_class=HTMLResponse)
async def get_infographic_html(
    content_item_id: str,
    language: str = Query(default="en", description="Language code, e.g. 'en', 'fr'"),
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
):
    """
    Return the AI-generated infographic as a raw HTML document (text/html).

    Ideal for:
    - Embedding directly in a Moodle page via <iframe src="...">
    - Opening as a standalone .html file
    - Rendering in a webview in mobile apps

    Returns 404 if the infographic hasn't been generated yet.
    """
    output, _ = await _get_infographic_output(content_item_id, language, db, tenant)
    effective_payload = output.edited_content if output.is_teacher_edited else output.payload
    html = effective_payload.get("html", "")

    if not html:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Infographic HTML is empty. Re-generate the infographic.",
        )

    return HTMLResponse(content=html, status_code=200)


async def _get_infographic_output(
    content_item_id: str,
    language: str,
    db: AsyncSession,
    tenant: "Tenant",
) -> tuple[AIOutput, ContentItem]:
    """Shared lookup for both infographic endpoints."""
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    if content_item.status == ContentStatus.PROCESSING:
        raise OutputNotReadyError(
            "Content is still being processed. Poll /api/v1/jobs/ for status."
        )

    result = await db.execute(
        select(AIOutput)
        .where(
            AIOutput.content_item_id == item_uuid,
            AIOutput.output_type == OutputType.INFOGRAPHIC,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .order_by(AIOutput.created_at.desc())
        .limit(1)
    )
    output = result.scalar_one_or_none()

    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No infographic found for this content in language '{language}'. "
                f"Trigger generation: POST /api/v1/content/{content_item_id}/generate"
                ' with body {"tasks": ["infographic"]}'
            ),
        )

    return output, content_item


# ── On-demand generation ──────────────────────────────────────────────────────

@router.post("/{content_item_id}/generate", status_code=status.HTTP_202_ACCEPTED)
async def generate_outputs(
    content_item_id: str,
    request: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    tenant: Tenant = Depends(get_current_tenant),
) -> dict:
    """
    Trigger generation of specific outputs for an already-processed content item.
    Content must already be extracted and embedded (status=READY or stale).
    """
    try:
        item_uuid = uuid.UUID(content_item_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid content_item_id")

    ci_result = await db.execute(
        select(ContentItem).where(
            ContentItem.id == item_uuid,
            ContentItem.tenant_id == tenant.id,
        )
    )
    content_item = ci_result.scalar_one_or_none()
    if not content_item:
        raise ContentNotFoundError(f"Content item {content_item_id} not found")

    # Create a generation job
    job = ProcessingJob(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        tenant_id=tenant.id,
        job_type=JobType.GENERATE_OUTPUTS,
        status=JobStatus.QUEUED,
        progress=0,
        job_config={
            "tasks": request.tasks,
            "options": {
                "language": request.language,
                "count": request.count,       # How many items to generate (flashcards/quiz)
                **request.options,
            },
            "force_regenerate": request.force_regenerate,
            "regenerate": request.regenerate,  # If True, adds to pool instead of replacing
        },
    )
    db.add(job)
    await db.flush()

    # FIX 2026-03-28: Same shared_task/AMQP broker fix as ingest.py.
    # Replaced run_pipeline.apply_async() with celery_app.send_task() so
    # dispatch always uses our Redis-backed celery_app, not the default AMQP app.
    from app.tasks.celery_app import celery_app
    celery_app.send_task(
        "app.tasks.process_content.run_pipeline",
        kwargs={
            "job_id": str(job.id),
            "content_item_id": str(content_item.id),
            "tenant_id": str(tenant.id),
            "job_config": job.job_config,
        },
        queue="priority",  # On-demand generation goes to priority queue
    )
    await db.commit()

    return {
        "job_id": str(job.id),
        "content_item_id": content_item_id,
        "tasks": request.tasks,
        "status": "queued",
        "message": f"Generation job queued. Poll /api/v1/jobs/{job.id}",
    }
