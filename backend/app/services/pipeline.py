"""
Pipeline orchestrator — wires all services together for a full processing run.

Called by Celery tasks. The pipeline is fully async. Celery wraps it with asyncio.run().

Flow:
  1. Load ContentItem from DB → validate it exists
  2. Update ProcessingJob status → PROCESSING
  3. Route to correct Extractor based on content_type
  4. Save ExtractedContent to DB
  5. Chunk the text
  6. Embed chunks (with Redis cache)
  7. Upsert vectors to Qdrant
  8. Update ContentItem: content_hash, chunk_count, status
  9. Run requested generators in parallel (where possible)
  10. Save AIOutput records (with prompt versioning — supersede old outputs)
  11. For quiz: also save to quiz_questions table + Qdrant question_intelligence
  12. Update ProcessingJob → COMPLETED

Error handling:
  - Any step failure sets ProcessingJob → FAILED with traceback
  - Content item remains at last known state (doesn't reset to PENDING)
  - Celery will retry the task based on its retry config
"""
import asyncio
import traceback
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.api.v1.axis_admin import get_current_ai_models
from app.core.qdrant import get_qdrant
from app.core.redis import get_redis
from app.models.content import ContentItem, ContentStatus, ExtractedContent
from app.models.job import ProcessingJob, JobStatus
from app.models.output import AIOutput, OutputStatus, OutputType
from app.services.ai.client import AIClient
from app.services.ai.prompts.loader import get_prompt_version
from app.services.chunkers import ChunkingConfig, get_chunker
from app.services.extractors.page import MoodlePageExtractor
from app.services.extractors.pdf import PDFExtractor
from app.services.extractors.text import TextExtractor
from app.services.extractors.youtube import YouTubeExtractor
from app.services.extractors.vimeo import VimeoExtractor
from app.services.extractors.peertube import PeerTubeExtractor
from app.services.extractors.video_upload import VideoUploadExtractor
from app.services.extractors.slides import SlidesExtractor
from app.services.generators import GENERATOR_REGISTRY
from app.services.generators.chapters import ChaptersGenerator
from app.services.generators.faq import FaqGenerator
from app.services.generators.flashcards import FlashcardsGenerator
from app.services.generators.glossary import GlossaryGenerator
from app.services.generators.infographic import InfographicGenerator
from app.services.generators.discussion_prompts import DiscussionPromptsGenerator
from app.services.generators.quiz import QuizGenerator
from app.services.vector.embedder import Embedder
from app.services.vector.store import QdrantStore

log = structlog.get_logger(__name__)

# Map content_type → extractor class
# NOTE: The canonical content_type for Moodle page modules AND generic web URLs is
# "html_page" (matching ContentType.HTML_PAGE enum value).  The old key "page" was
# a legacy name used before the enum was finalised — do NOT add it back.
EXTRACTOR_REGISTRY = {
    "pdf": PDFExtractor,
    "text": TextExtractor,
    "youtube": YouTubeExtractor,
    "vimeo": VimeoExtractor,
    "peertube": PeerTubeExtractor,
    "html_page": MoodlePageExtractor,   # mod_page (HTML in metadata) + mod_url (URL fetch fallback)
    "video_upload": VideoUploadExtractor,  # locally-uploaded video files (whisper transcription)
    "audio": VideoUploadExtractor,         # locally-uploaded audio files (whisper transcription)
    "interactive_pdf": PDFExtractor,          # PF-05: Interactive PDF (same extraction, different viewer)
    "interactive_slides": SlidesExtractor,    # PF-03: PPTX slide extractor
    # Phase 5+: scorm, h5p
}


async def run_full_pipeline(
    job_id: str,
    content_item_id: str,
    tenant_id: str,
    job_config: dict,
    session_factory: async_sessionmaker[AsyncSession],
    axis_user_id: str | None = None,
) -> None:
    """
    Full content processing pipeline.

    Args:
        job_id:            UUID of the ProcessingJob
        content_item_id:   UUID of the ContentItem
        tenant_id:         UUID of the Tenant
        job_config:        Dict from ProcessingJob.job_config:
                           {tasks: [str], options: {chunk_size, chunk_overlap, etc.}}
        session_factory:   Async SQLAlchemy session factory
    """
    async with session_factory() as db:
        try:
            await _run_pipeline(
                db=db,
                job_id=job_id,
                content_item_id=content_item_id,
                tenant_id=tenant_id,
                job_config=job_config,
                session_factory=session_factory,
                axis_user_id=axis_user_id,
            )
        except Exception as exc:
            log.error("pipeline_failed", job_id=job_id, error=str(exc))
            await _mark_job_failed(db, job_id, exc)


async def _run_pipeline(
    db: AsyncSession,
    job_id: str,
    content_item_id: str,
    tenant_id: str,
    job_config: dict,
    session_factory: async_sessionmaker,
    axis_user_id: str | None = None,
) -> None:
    """Inner pipeline — raises on error so caller can handle."""

    # ── Load records ───────────────────────────────────────────────────────
    job = await _get_job(db, job_id)
    content_item = await _get_content_item(db, content_item_id)

    if not job or not content_item:
        raise RuntimeError(f"Job {job_id} or ContentItem {content_item_id} not found")

    structlog.contextvars.bind_contextvars(
        job_id=job_id,
        content_item_id=content_item_id,
        content_type=content_item.content_type,
    )

    # ── Step 1: Mark PROCESSING ────────────────────────────────────────────
    await _update_job(db, job, status=JobStatus.PROCESSING, progress=5,
                      message="Starting pipeline")
    content_item.status = ContentStatus.PROCESSING
    await db.flush()

    # ── Step 2: Extract (or skip if regenerating) ──────────────────────────
    content_type = content_item.content_type
    options = job_config.get("options", {})
    skip_extraction = job_config.get("skip_extraction", False)

    if skip_extraction:
        # Regeneration path — re-use already-extracted text + existing Qdrant chunks
        await _update_job(db, job, progress=10, message="Loading existing extracted content")
        ec_r = await db.execute(
            select(ExtractedContent).where(ExtractedContent.content_item_id == content_item.id)
        )
        ec = ec_r.scalar_one_or_none()
        if not ec:
            raise ValueError(
                f"skip_extraction=True but no ExtractedContent row found for {content_item_id}. "
                "Run a full pipeline first."
            )
        source_language = content_item.language or "en"
        output_language = options.get("output_language", "").strip() or source_language
        # Use a lightweight extracted object with just the raw_text for generators
        from app.services.extractors.base import ExtractedContent as _EC
        extracted = _EC(
            raw_text=ec.raw_text,
            content_hash=content_item.content_hash or "",
            word_count=ec.word_count,
            page_count=ec.page_count,
        )
        log.info("skip_extraction_mode", words=ec.word_count, content_item_id=content_item_id)
    else:
        extract_msg = {
            "youtube": "Fetching YouTube transcript",
            "vimeo": "Fetching Vimeo transcript",
            "peertube": "Fetching PeerTube transcript",
            "html_page": "Extracting page content and embedded videos",
            "video_upload": "Transcribing uploaded video",
            "audio": "Transcribing uploaded audio",
        }.get(content_type, "Extracting content")

        await _update_job(db, job, progress=10, message=extract_msg)

        extractor_class = EXTRACTOR_REGISTRY.get(content_type)
        if not extractor_class:
            raise ValueError(f"No extractor for content type: {content_type}")

        extractor = extractor_class()
        extracted = await extractor.extract(
            url=content_item.source_url,
            content_item_metadata={
                **content_item.moodle_metadata,
                "language": content_item.language,
            },
        )

        log.info(
            "content_extracted",
            words=extracted.word_count,
            pages=extracted.page_count,
            segments=len(extracted.segments),
            languages=list(extracted.all_segments.keys()) if extracted.all_segments else [],
            detected_language=extracted.detected_source_language,
            content_type=content_type,
        )

        # ── Step 2b: Resolve source language ──────────────────────────────
        source_language = content_item.language or ""
        if extracted.detected_source_language and (not source_language or source_language == "auto"):
            content_item.language = extracted.detected_source_language
            source_language = extracted.detected_source_language
            log.info(
                "source_language_auto_detected",
                language=source_language,
                content_item_id=content_item_id,
            )
            await db.flush()
        elif not source_language or source_language == "auto":
            source_language = "en"
            content_item.language = source_language
            await db.flush()

        output_language = options.get("output_language", "").strip() or source_language

        # ── Step 3: Save extracted content ────────────────────────────────
        await _save_extracted_content(db, content_item, extracted)
        await db.flush()

        # ── Step 3b: Save ALL Transcript records (video only) ─────────────
        if extracted.all_segments or extracted.segments:
            await _save_all_transcripts(db, content_item, extracted)
            await db.flush()

    if not skip_extraction:
        # ── Step 4: Chunk ──────────────────────────────────────────────────
        await _update_job(db, job, progress=25, message="Chunking content")
        chunking_config = ChunkingConfig(
            strategy=options.get("chunking_strategy", settings.default_chunking_strategy),
            chunk_size=options.get("chunk_size", settings.default_chunk_size),
            chunk_overlap=options.get("chunk_overlap", settings.default_chunk_overlap),
        )
        chunker = get_chunker(chunking_config)
        chunks = chunker.chunk(extracted.raw_text)

        log.info("content_chunked", chunk_count=len(chunks), strategy=chunking_config.strategy)

    # ── Step 5: Embed + Qdrant upsert (skip when regenerating) ──────────────
    redis = await get_redis()
    qdrant_client = get_qdrant()

    # AIClient is needed for both embedding (step 5) and generation (step 6)
    ai_client = AIClient(
        session_factory=session_factory,
        redis=redis,
        tenant_id=tenant_id,
        content_item_id=content_item_id,
        job_id=job_id,
        moodle_course_id=content_item.moodle_course_id,
        moodle_cmid=content_item.moodle_cmid,
        axis_user_id=axis_user_id,
    )

    if not skip_extraction:
        await _update_job(db, job, progress=35, message="Embedding and indexing")
        # FIX 2026-03-28: Use the session_factory passed into this function instead
        # of re-importing the module-level AsyncSessionFactory.
        embedder = Embedder(
            ai_client=ai_client,
            redis=redis,
            model=settings.default_embedding_model,
        )
        embeddings = await embedder.embed_chunks(chunks)

        # Update content_hash on the item before upsert (deterministic IDs use it)
        content_item.content_hash = extracted.content_hash
        content_item.chunk_count = len(chunks)

        # PF-03: persist slide image paths for PPTX content
        if extracted.extraction_metadata.get('slide_assets'):
            content_item.slide_assets = extracted.extraction_metadata['slide_assets']
        content_item.word_count = extracted.word_count
        await db.flush()

        qdrant_store = QdrantStore(client=qdrant_client)
        await qdrant_store.upsert_chunks(content_item, chunks, embeddings)

        await _update_job(db, job, progress=55, message="Content indexed in vector DB")
    else:
        await _update_job(db, job, progress=55, message="Using existing index — running generators")

    # ── Step 6: Generate AI outputs ────────────────────────────────────────
    requested_tasks = job_config.get("tasks", ["summary"])
    total_tasks = len(requested_tasks)
    failed_tasks: list[str] = []   # track generator failures
    succeeded_tasks: list[str] = []

    for task_idx, task_name in enumerate(requested_tasks):
        progress = 55 + int(35 * task_idx / total_tasks)
        await _update_job(db, job, progress=progress,
                          message=f"Generating {task_name} ({task_idx + 1}/{total_tasks})")

        output_type = _task_to_output_type(task_name)
        if output_type is None:
            log.warning("unknown_task_type", task=task_name)
            continue

        generator_class = GENERATOR_REGISTRY.get(output_type)
        if not generator_class:
            log.warning("no_generator_for_task", task=task_name)
            continue

        # Use admin-configured model; fast model for lightweight tasks
        _main_model, _fast_model = await get_current_ai_models(db)
        _fast_tasks = {'summary', 'flashcards', 'glossary', 'faq', 'mindmap', 'objectives', 'blooms', 'discussion_prompts'}
        model = _fast_model if task_name in _fast_tasks else _main_model
        generator = generator_class(ai_client=ai_client)

        # Count parameter — controls how many items to generate for pool-based types.
        # Passed through job_config.options (Moodle can override the default of 10).
        gen_count = options.get("count", 10)

        try:
            # ── Parameterized generate call ─────────────────────────────────
            # Pool-based generators (flashcards, quiz) accept a count parameter.
            # All generators now accept output_language for multilingual output.
            if output_type == OutputType.FLASHCARDS and isinstance(generator, FlashcardsGenerator):
                payload = await generator.generate(
                    content_item=content_item,
                    full_text=extracted.raw_text,
                    model=model,
                    output_language=output_language,
                    count=gen_count,
                )
            elif output_type == OutputType.QUIZ and isinstance(generator, QuizGenerator):
                payload = await generator.generate(
                    content_item=content_item,
                    full_text=extracted.raw_text,
                    model=model,
                    output_language=output_language,
                    question_count=gen_count,
                )
            elif output_type == OutputType.CHAPTERS and isinstance(generator, ChaptersGenerator):
                # Pass timed transcript segments so the generator can produce
                # seek-able chapter timestamps.  Segments may be None/empty for
                # non-video content — ChaptersGenerator handles that gracefully.
                payload = await generator.generate(
                    content_item=content_item,
                    full_text=extracted.raw_text,
                    model=model,
                    output_language=output_language,
                    segments=extracted.segments or [],
                )
            elif output_type == OutputType.FAQ and isinstance(generator, FaqGenerator):
                payload = await generator.generate(
                    content_item=content_item,
                    full_text=extracted.raw_text,
                    model=model,
                    output_language=output_language,
                    count=gen_count,
                )
            else:
                payload = await generator.generate(
                    content_item=content_item,
                    full_text=extracted.raw_text,
                    model=model,
                    output_language=output_language,
                )

            # Mark old outputs as SUPERSEDED (prompt versioning Option A)
            await _supersede_old_outputs(db, content_item_id, output_type,
                                         output_language)

            prompt_ver = get_prompt_version(generator.prompt_name)
            usage = _get_last_usage(ai_client)

            ai_output = AIOutput(
                id=uuid.uuid4(),
                content_item_id=content_item.id,
                tenant_id=content_item.tenant_id,
                job_id=job.id,
                output_type=output_type,
                language=output_language,
                status=OutputStatus.ACTIVE,
                payload=payload,
                model=model,
                provider=ai_client._get_provider(model),
                prompt_version=prompt_ver,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                confidence=0.85,
            )
            db.add(ai_output)
            await db.flush()

            # ── Save pool rows for pool-based output types ──────────────────
            # These go into dedicated tables (flashcard_items, glossary_terms,
            # quiz_questions) so they can be individually managed, edited,
            # and extended via the regenerate API.
            if output_type == OutputType.QUIZ and isinstance(generator, QuizGenerator):
                await generator.save_questions_to_db(
                    db=db,
                    content_item=content_item,
                    ai_output=ai_output,
                    payload=payload,
                    model=model,
                    generation_batch=1,  # First generation is always batch 1
                )

            elif output_type == OutputType.FLASHCARDS and isinstance(generator, FlashcardsGenerator):
                await generator.save_cards_to_db(
                    db=db,
                    content_item=content_item,
                    ai_output=ai_output,
                    payload=payload,
                    generation_batch=1,
                )

            elif output_type == OutputType.GLOSSARY and isinstance(generator, GlossaryGenerator):
                await generator.save_terms_to_db(
                    db=db,
                    content_item=content_item,
                    ai_output=ai_output,
                    payload=payload,
                    generation_batch=1,
                )

            succeeded_tasks.append(task_name)

        except Exception as e:
            err_msg = str(e)
            log.error("generator_failed", task=task_name, error=err_msg,
                      hint="Check OPENAI_API_KEY / ANTHROPIC_API_KEY in .env" if "auth" in err_msg.lower() or "api key" in err_msg.lower() or "apikey" in err_msg.lower() else None)
            failed_tasks.append(f"{task_name}: {err_msg[:120]}")
            # Don't abort entire pipeline for one failed generator
            continue

    # ── Step 7: Mark READY ─────────────────────────────────────────────────
    content_item.status = ContentStatus.READY
    now = datetime.now(timezone.utc).isoformat()
    job.status = JobStatus.COMPLETED
    job.progress = 100

    if failed_tasks and not succeeded_tasks:
        # ALL generators failed — surface this clearly
        job.progress_message = f"Extraction succeeded but AI generation failed for all tasks. Check API key. Errors: {'; '.join(failed_tasks[:2])}"
        log.error("all_generators_failed", failed=failed_tasks,
                  hint="Verify OPENAI_API_KEY or ANTHROPIC_API_KEY is set in .env and workers are restarted")
    elif failed_tasks:
        job.progress_message = f"Completed with {len(succeeded_tasks)} output(s). {len(failed_tasks)} task(s) failed: {', '.join(t.split(':')[0] for t in failed_tasks)}"
        log.warning("some_generators_failed", succeeded=succeeded_tasks, failed=failed_tasks)
    else:
        job.progress_message = "All outputs generated"

    job.completed_at = now
    await db.commit()

    # ── Step 8: Notify creator that content is ready ────────────────────────
    if axis_user_id:
        try:
            import uuid as _uuid
            from sqlalchemy import text as _text
            sql = (
                "INSERT INTO user_notifications "
                "(id, user_id, title, body, link, notif_type, is_read, created_at) "
                "VALUES (:id, :uid, :title, :body, :link, :ntype, false, NOW())"
            )
            ct_title = content_item.title or "Content"
            await db.execute(
                _text(sql),
                {
                    "id": str(_uuid.uuid4()),
                    "uid": axis_user_id,
                    "title": f'"{ct_title}" is ready',
                    "body": "AI outputs have been generated.",
                    "link": f"/spaces/{content_item.space_id}" if content_item.space_id else None,
                    "ntype": "job_done",
                },
            )
            await db.commit()
        except Exception:
            pass  # never fail pipeline on notification error

    log.info(
        "pipeline_completed",
        job_id=job_id,
        content_item_id=content_item_id,
        tasks_completed=len(requested_tasks),
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_job(db: AsyncSession, job_id: str) -> ProcessingJob | None:
    result = await db.execute(
        select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id))
    )
    return result.scalar_one_or_none()


async def _get_content_item(db: AsyncSession, content_item_id: str) -> ContentItem | None:
    result = await db.execute(
        select(ContentItem).where(ContentItem.id == uuid.UUID(content_item_id))
    )
    return result.scalar_one_or_none()


async def _update_job(
    db: AsyncSession,
    job: ProcessingJob,
    status: JobStatus | None = None,
    progress: int | None = None,
    message: str | None = None,
) -> None:
    if status is not None:
        job.status = status
        # Record timestamps on status transitions
        if status == JobStatus.PROCESSING and not job.started_at:
            job.started_at = datetime.now(timezone.utc).isoformat()
    if progress is not None:
        job.progress = progress
    if message is not None:
        job.progress_message = message
    await db.flush()


async def _save_extracted_content(
    db: AsyncSession,
    content_item: ContentItem,
    extracted,
) -> None:
    """Save ExtractedContent, replacing any existing record."""
    from sqlalchemy import delete
    await db.execute(
        delete(ExtractedContent).where(
            ExtractedContent.content_item_id == content_item.id
        )
    )
    ec = ExtractedContent(
        id=uuid.uuid4(),
        content_item_id=content_item.id,
        raw_text=extracted.raw_text,
        page_count=extracted.page_count,
        word_count=extracted.word_count,
        extraction_metadata=extracted.extraction_metadata,
    )
    db.add(ec)


async def _save_all_transcripts(
    db: AsyncSession,
    content_item: ContentItem,
    extracted,
) -> None:
    """
    Persist ALL available caption language tracks to the transcripts table.

    For video sources (YouTube, Vimeo, PeerTube) the extractor returns every
    caption language it could find in `all_segments`. Each language gets its
    own row with a UNIQUE(content_item_id, language) constraint, so reprocessing
    is safe — existing rows are replaced.

    If `all_segments` is empty but `segments` is populated (e.g. Whisper fallback
    returned segments without populating all_segments), a single transcript is
    saved using the resolved content_item.language.

    caption_source in extraction_metadata maps to TranscriptSource:
      "api_captions"  → API_CAPTIONS
      "ytdlp"         → API_CAPTIONS  (yt-dlp scraped from platform, same quality)
      "whisper_local" → WHISPER_LOCAL
      "whisper_api"   → WHISPER_API
      "manual"        → MANUAL
    """
    from sqlalchemy import delete
    from app.models.transcript import Transcript, TranscriptSource

    caption_source = extracted.extraction_metadata.get("caption_source", "api_captions")
    source_map = {
        "api_captions": TranscriptSource.API_CAPTIONS,
        "ytdlp": TranscriptSource.API_CAPTIONS,
        "whisper_local": TranscriptSource.WHISPER_LOCAL,
        "whisper_api": TranscriptSource.WHISPER_API,
        "manual": TranscriptSource.MANUAL,
    }
    transcript_source = source_map.get(caption_source, TranscriptSource.API_CAPTIONS)

    # Build the dict of tracks to save.
    # all_segments is the canonical source: {lang_code: [segments]}
    # Fall back to primary segments if all_segments is empty.
    tracks: dict[str, list[dict]] = extracted.all_segments or {}
    if not tracks and extracted.segments:
        primary_lang = content_item.language or "en"
        tracks = {primary_lang: extracted.segments}

    if not tracks:
        return

    saved_count = 0
    for lang_code, segments in tracks.items():
        if not segments:
            continue

        # Determine the full transcript text for this language track
        # (join all segment text the same way extractors do)
        full_text = " ".join(
            seg["text"].strip() for seg in segments if seg.get("text", "").strip()
        )
        word_count = len(full_text.split())

        # Replace existing row for this (content_item, language) pair
        await db.execute(
            delete(Transcript).where(
                Transcript.content_item_id == content_item.id,
                Transcript.language == lang_code,
            )
        )

        transcript = Transcript(
            id=uuid.uuid4(),
            content_item_id=content_item.id,
            language=lang_code,
            source=transcript_source,
            full_text=full_text,
            word_count=word_count,
            segments=segments,
        )
        db.add(transcript)
        saved_count += 1

    log.info(
        "transcripts_saved",
        content_item_id=str(content_item.id),
        languages=list(tracks.keys()),
        track_count=saved_count,
        source=transcript_source,
    )


async def _supersede_old_outputs(
    db: AsyncSession,
    content_item_id: str,
    output_type: OutputType,
    language: str,
) -> None:
    """Mark existing ACTIVE outputs as SUPERSEDED (prompt versioning Option A)."""
    from sqlalchemy import update
    await db.execute(
        update(AIOutput)
        .where(
            AIOutput.content_item_id == uuid.UUID(content_item_id),
            AIOutput.output_type == output_type,
            AIOutput.language == language,
            AIOutput.status == OutputStatus.ACTIVE,
        )
        .values(status=OutputStatus.SUPERSEDED)
    )


async def _mark_job_failed(db: AsyncSession, job_id: str, exc: Exception) -> None:
    """Mark job as FAILED with error details. Also updates ContentItem status."""
    try:
        job = await _get_job(db, job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error_message = str(exc)[:1000]
            job.error_traceback = traceback.format_exc()[:5000]
            # Also mark the content item FAILED so it doesn't get permanently stuck
            # in PROCESSING if the pipeline fails after marking it as in-progress.
            content_item = await _get_content_item(db, str(job.content_item_id))
            if content_item and content_item.status == ContentStatus.PROCESSING:
                content_item.status = ContentStatus.FAILED
            await db.commit()
    except Exception as e:
        log.error("failed_to_mark_job_failed", error=str(e))


def _task_to_output_type(task_name: str) -> OutputType | None:
    mapping = {
        "summary": OutputType.SUMMARY,
        "flashcards": OutputType.FLASHCARDS,
        "glossary": OutputType.GLOSSARY,
        "mindmap": OutputType.MINDMAP,
        "objectives": OutputType.OBJECTIVES,
        "blooms": OutputType.BLOOMS,
        "quiz": OutputType.QUIZ,
        "chapters": OutputType.CHAPTERS,
        "faq": OutputType.FAQ,
        "infographic": OutputType.INFOGRAPHIC,
        "discussion_prompts": OutputType.DISCUSSION_PROMPTS,
    }
    return mapping.get(task_name.lower())


def _get_last_usage(ai_client: AIClient) -> dict:
    """Placeholder — Phase 3 will track token usage per call on the client."""
    return {"prompt_tokens": 0, "completion_tokens": 0}
