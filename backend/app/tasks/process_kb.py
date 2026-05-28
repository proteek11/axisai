"""
KB (Knowledge Base) processing pipeline task.

Handles text extraction, chunking, embedding, and Qdrant upsert for
admin-uploaded support documents (PDF, TXT, DOCX, or plain-text paste).

All source documents arrive as file:// paths (written to /tmp/axis_uploads
by the API before queueing this task).

Pipeline steps:
  1. Load KnowledgeBaseItem + ProcessingJob from DB
  2. Mark ProcessingJob → PROCESSING
  3. Read file bytes from file:// URL
  4. Route to extractor by file extension (PDF → PDFExtractor, else plain text)
  5. Chunk extracted text
  6. Embed chunks
  7. Upsert to axis_kb_chunks Qdrant collection
  8. Update KnowledgeBaseItem: status=READY, chunk_count, word_count, content_hash
  9. Mark ProcessingJob → COMPLETED

Uses the same asyncio.run() + fresh-engine pattern as process_content.py
to avoid "Future attached to a different loop" errors.
"""
import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.process_kb.run_kb_pipeline",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_kb_pipeline(
    self,
    job_id: str,
    kb_item_id: str,
    tenant_id: str,
    job_config: dict | None = None,
) -> dict:
    """
    Full KB ingest task: extract → chunk → embed → upsert to axis_kb_chunks.
    Runs the async pipeline inside a new event loop (Celery is sync).
    """
    logger.info(
        f"KB pipeline starting job={job_id} kb_item={kb_item_id}"
    )

    async def _run():
        from sqlalchemy.ext.asyncio import (
            create_async_engine, async_sessionmaker, AsyncSession
        )
        from app.config import settings

        engine = create_async_engine(
            settings.database_url,
            pool_size=2,
            max_overflow=5,
            pool_pre_ping=True,
        )
        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        try:
            await _run_kb_pipeline(
                job_id=job_id,
                kb_item_id=kb_item_id,
                tenant_id=tenant_id,
                job_config=job_config or {},
                session_factory=session_factory,
                celery_task_id=str(self.request.id),
            )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
        logger.info(f"KB pipeline completed job={job_id}")
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        logger.error(f"KB pipeline failed job={job_id}: {exc}")
        try:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {"status": "failed", "job_id": job_id, "error": str(exc)}


# ---------------------------------------------------------------------------
# Async pipeline implementation
# ---------------------------------------------------------------------------

async def _run_kb_pipeline(
    job_id: str,
    kb_item_id: str,
    tenant_id: str,
    job_config: dict,
    session_factory,
    celery_task_id: str,
) -> None:
    import uuid
    import os
    import traceback

    import structlog
    from sqlalchemy import select

    from app.config import settings
    from app.core.qdrant import get_qdrant
    from app.models.kb import KnowledgeBaseItem, KBItemStatus
    from app.models.job import ProcessingJob, JobStatus
    from app.services.chunkers import ChunkingConfig, get_chunker
    from app.services.vector.embedder import Embedder
    from app.utils.hashing import sha256_text

    log = structlog.get_logger(__name__)

    async with session_factory() as db:
        # ── 1. Load records ───────────────────────────────────────────────
        kb_item_uuid = uuid.UUID(kb_item_id)
        job_uuid = uuid.UUID(job_id)

        kb_item = (await db.execute(
            select(KnowledgeBaseItem).where(KnowledgeBaseItem.id == kb_item_uuid)
        )).scalar_one_or_none()

        job = (await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == job_uuid)
        )).scalar_one_or_none()

        if not kb_item:
            raise ValueError(f"KnowledgeBaseItem {kb_item_id} not found")
        if not job:
            raise ValueError(f"ProcessingJob {job_id} not found")

        # ── 2. Mark PROCESSING ────────────────────────────────────────────
        job.status = JobStatus.PROCESSING
        job.celery_task_id = celery_task_id
        job.progress = 5
        job.progress_message = "Starting extraction"
        kb_item.status = KBItemStatus.PROCESSING.value
        await db.commit()

        try:
            source_url  = job_config.get("source_url") or kb_item.source_url or ""
            inline_text = job_config.get("inline_text")
            file_base64 = job_config.get("file_base64")
            filename    = job_config.get("filename", "upload.pdf")
            language    = job_config.get("language", "en")
            doc_type    = job_config.get("doc_type", "support")
            title       = job_config.get("title") or kb_item.title

            # ── 3. Extract text ───────────────────────────────────────────
            # Priority: inline_text > file_base64 > source_url (file://)
            if inline_text:
                log.info("kb_extracting_inline_text", kb_item_id=kb_item_id, chars=len(inline_text))
                raw_text = inline_text
            elif file_base64:
                log.info("kb_extracting_base64_file", kb_item_id=kb_item_id, filename=filename)
                raw_text = await _extract_from_base64(file_base64, filename, language)
            else:
                log.info("kb_extracting", source_url=source_url, kb_item_id=kb_item_id)
                raw_text = await _extract_text(source_url, language)

            job.progress = 40
            job.progress_message = "Chunking text"
            await db.commit()

            # ── 4. Chunk ──────────────────────────────────────────────────
            chunking_config = ChunkingConfig(
                strategy=settings.default_chunking_strategy,
                chunk_size=settings.default_chunk_size,
                chunk_overlap=settings.default_chunk_overlap,
            )
            chunker = get_chunker(chunking_config)
            chunks = chunker.chunk(raw_text)

            log.info("kb_chunked", chunk_count=len(chunks), kb_item_id=kb_item_id)

            job.progress = 55
            job.progress_message = "Embedding chunks"
            await db.commit()

            # ── 5. Embed ──────────────────────────────────────────────────
            content_hash = sha256_text(raw_text)

            if not chunks:
                # Text too short to produce any chunks (e.g. < min chunk size).
                # Store the whole text as a single synthetic chunk so the item
                # is still searchable, instead of silently indexing nothing.
                from app.services.chunkers.base import Chunk
                chunk_text = raw_text.strip() or title
                chunks = [Chunk(text=chunk_text, chunk_index=0, chunk_hash=sha256_text(chunk_text))]
                log.info("kb_single_chunk_fallback", kb_item_id=kb_item_id, chars=len(chunk_text))

            from app.services.ai.client import AIClient
            from app.core.redis import get_redis as _get_redis

            redis = await _get_redis()
            ai_client = AIClient(
                session_factory=session_factory,
                redis=redis,
                tenant_id=tenant_id,
                job_id=job_id,
            )
            embedder = Embedder(
                ai_client=ai_client,
                redis=redis,
                model=settings.default_embedding_model,
            )
            embeddings = await embedder.embed_chunks(chunks)

            job.progress = 80
            job.progress_message = "Storing vectors"
            await db.commit()

            # ── 6. Upsert to axis_kb_chunks ───────────────────────────────
            qdrant_client = get_qdrant()
            upserted = await _upsert_kb_chunks(
                client=qdrant_client,
                collection=settings.qdrant_collection_kb_chunks,
                kb_item_id=kb_item_id,
                tenant_id=tenant_id,
                title=title,
                doc_type=doc_type,
                language=language,
                content_hash=content_hash,
                chunks=chunks,
                embeddings=embeddings,
            )

            log.info("kb_upserted", chunk_count=upserted, kb_item_id=kb_item_id)

            # ── 7. Update KBItem → READY ──────────────────────────────────
            kb_item.status = KBItemStatus.READY.value
            kb_item.chunk_count = upserted
            kb_item.word_count = len(raw_text.split())
            kb_item.content_hash = content_hash
            kb_item.error_message = None

            # ── 8. Mark job COMPLETED ─────────────────────────────────────
            job.status = JobStatus.COMPLETED
            job.progress = 100
            job.progress_message = "Completed"
            await db.commit()

            log.info(
                "kb_pipeline_complete",
                kb_item_id=kb_item_id,
                chunks=upserted,
                words=kb_item.word_count,
            )

        except Exception as exc:
            log.error(
                "kb_pipeline_error",
                kb_item_id=kb_item_id,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            kb_item.status = KBItemStatus.ERROR.value
            kb_item.error_message = str(exc)[:1000]
            job.status = JobStatus.FAILED
            job.progress_message = f"Error: {str(exc)[:200]}"
            await db.commit()
            raise


# ---------------------------------------------------------------------------
# Text extraction helper — routes by file extension
# ---------------------------------------------------------------------------

async def _extract_text(source_url: str, language: str = "en") -> str:
    """
    Extract plain text from a source URL.

    Supports:
      file:///tmp/.../<name>.pdf  → PDFExtractor
      file:///tmp/.../<name>.docx → python-docx
      file:///tmp/.../<name>.txt  → plain read
      http(s)://...               → PDFExtractor (assumes PDF for now)

    Returns raw text string ready for chunking.
    """
    import os
    import aiofiles

    lower = source_url.lower()

    if source_url.startswith("file://"):
        file_path = source_url[len("file://"):]

        # ── TXT ───────────────────────────────────────────────────────────
        if lower.endswith(".txt"):
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                return await f.read()

        # ── DOCX ──────────────────────────────────────────────────────────
        if lower.endswith(".docx") or lower.endswith(".doc"):
            return await _extract_docx_text(file_path)

        # ── PDF (default for file:// paths) ───────────────────────────────
        async with aiofiles.open(file_path, "rb") as f:
            file_bytes = await f.read()

        from app.services.extractors.pdf import PDFExtractor
        extractor = PDFExtractor()
        result = await extractor.extract(
            file_bytes=file_bytes,
            content_item_metadata={"language": language},
        )
        return result.raw_text

    # ── Remote URL — PDF vs HTML ──────────────────────────────────────────────
    stripped = source_url.lower().split("?")[0].split("#")[0]
    if stripped.endswith(".pdf"):
        from app.services.extractors.pdf import PDFExtractor
        extractor = PDFExtractor()
        result = await extractor.extract(
            url=source_url,
            content_item_metadata={"language": language},
        )
        return result.raw_text

    # HTML / generic web page — trafilatura gives clean article text
    import asyncio

    def _fetch_and_extract(url: str) -> str:
        import trafilatura
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            raise ValueError(f"KB URL fetch failed: {url}")
        text = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            favor_recall=True,
        )
        if not text or len(text.strip()) < 50:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(downloaded, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
        if not text or len(text.strip()) < 20:
            raise ValueError(f"No readable text found at URL: {url}")
        return text.strip()

    return await asyncio.get_event_loop().run_in_executor(None, _fetch_and_extract, source_url)


async def _extract_from_base64(file_base64: str, filename: str, language: str = "en") -> str:
    """
    Decode a base64 payload, write to a local temp file, extract text, then clean up.

    Writing the temp file here (inside the Celery worker process) ensures the
    file always exists on the same machine as the extractor — regardless of
    whether the API server and the worker share a filesystem.
    """
    import base64 as _b64
    import os
    import uuid as _uuid
    import aiofiles
    from app.config import settings

    file_bytes = _b64.b64decode(file_base64)
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    temp_path = os.path.join(settings.upload_dir, f"kb_{_uuid.uuid4()}_{safe_name}")

    async with aiofiles.open(temp_path, "wb") as f:
        await f.write(file_bytes)

    try:
        return await _extract_text(f"file://{temp_path}", language)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


async def _extract_docx_text(file_path: str) -> str:
    """Extract text from a .docx file using python-docx (sync, run in thread)."""
    import asyncio

    def _sync_extract():
        try:
            import docx  # python-docx
            doc = docx.Document(file_path)
            return "\n".join(para.text for para in doc.paragraphs if para.text.strip())
        except ImportError:
            # Fallback: try mammoth
            import mammoth
            with open(file_path, "rb") as f:
                result = mammoth.extract_raw_text(f)
            return result.value

    return await asyncio.get_event_loop().run_in_executor(None, _sync_extract)


# ---------------------------------------------------------------------------
# KB-specific Qdrant upsert
# ---------------------------------------------------------------------------

async def _upsert_kb_chunks(
    *,
    client,
    collection: str,
    kb_item_id: str,
    tenant_id: str,
    title: str,
    doc_type: str,
    language: str,
    content_hash: str,
    chunks,
    embeddings: list[list[float]],
) -> int:
    """
    Delete existing vectors for this kb_item_id, then upsert new ones.

    Payload mirrors axis_kb_chunks schema:
      tenant_id, kb_item_id, doc_type, chunk_index, text, title, language,
      content_hash
    """
    import uuid as _uuid
    from qdrant_client.models import (
        Filter, FieldCondition, MatchValue, PointStruct, UpdateStatus
    )

    if not chunks or not embeddings:
        return 0

    # ── Delete old vectors for this KB item ───────────────────────────────
    await client.delete(
        collection_name=collection,
        points_selector=Filter(
            must=[
                FieldCondition(key="kb_item_id", match=MatchValue(value=kb_item_id))
            ]
        ),
    )

    # ── Build points with deterministic UUIDs ─────────────────────────────
    points = []
    for chunk, embedding in zip(chunks, embeddings):
        name = f"{tenant_id}:{kb_item_id}:{chunk.chunk_index}:{content_hash}"
        point_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, name))

        points.append(PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "tenant_id": tenant_id,
                "kb_item_id": kb_item_id,
                "doc_type": doc_type,
                "language": language,
                "title": title,
                "chunk_index": chunk.chunk_index,
                "chunk_hash": chunk.chunk_hash,
                "text": chunk.text,
                "content_hash": content_hash,
                # is_active MUST be stored so the chat retriever can filter on it.
                # The retriever does: FieldCondition(key="is_active", match=MatchValue(value=True))
                # Without this field in the payload Qdrant treats every chunk as non-matching.
                "is_active": True,
            },
        ))

    # ── Upsert in batches of 100 ──────────────────────────────────────────
    total = 0
    batch_size = 100
    for i in range(0, len(points), batch_size):
        batch = points[i: i + batch_size]
        result = await client.upsert(
            collection_name=collection,
            points=batch,
            wait=True,
        )
        if result.status == UpdateStatus.COMPLETED:
            total += len(batch)

    return total
