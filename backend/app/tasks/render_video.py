"""
Celery task: render_video

Full video rendering pipeline:
  1.  Load VideoJob + Tenant from DB
  2.  Mark job PROCESSING, record started_at
  3.  Build ProviderBundle via ProviderRegistry (per-tenant config)
  4.  Resolve renderer class for the video_type
  5.  Create exclusive temp directory for all intermediate files
  6.  Run renderer.render()  →  RenderResult(raw_mp4_path, duration_seconds)
  7.  FFmpeg quality gate    →  enterprise-standard H.264/AAC MP4
  8.  Upload encoded MP4     →  output_url (local or S3)
  9.  Extract thumbnail      →  JPEG frame at 2 s
  10. Upload thumbnail       →  thumbnail_url
  11. Mark job DONE, store output_url, thumbnail_url, duration_sec, file_size_bytes
  12. Fire callback_url       →  POST to Moodle with final status
  13. Cleanup temp directory

Error path (any exception in steps 3-12):
  - Mark job FAILED, store error_message
  - Fire callback_url with failed status
  - Cleanup temp directory

Worker start command:
    celery -A app.tasks.celery_app worker \\
        --queues=video --concurrency=2 --max-tasks-per-child=10 -l info

Asyncio note:
    Celery workers are synchronous.  All async work runs inside
    asyncio.run(_run()) with a fresh SQLAlchemy engine created inside _run()
    to avoid the "Future attached to a different loop" error (same fix used
    in process_content.py).
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.render_video.render_video",
    acks_late=True,
    max_retries=2,
    default_retry_delay=30,
)
def render_video(self, video_job_id: str) -> dict:
    """
    Main video rendering task.

    Args:
        video_job_id: UUID string of the VideoJob row (NOT moodle_job_id).
    """
    logger.info(f"render_video started job={video_job_id}")

    from app.config import settings

    async def _run() -> None:
        # ── Fresh engine per task (avoids asyncpg loop mismatch) ─────────────
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

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
            await _render_pipeline(video_job_id, session_factory)
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
        logger.info(f"render_video completed job={video_job_id}")
        return {"status": "done", "video_job_id": video_job_id}

    except Exception as exc:
        logger.error(f"render_video fatal error job={video_job_id}: {exc}", exc_info=True)
        # At this point the job should already be FAILED (set inside _render_pipeline).
        # We only retry on transient infrastructure errors (DB unreachable, etc.)
        try:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {"status": "failed", "video_job_id": video_job_id, "error": str(exc)}


# ── Core async pipeline ───────────────────────────────────────────────────────

async def _render_pipeline(
    video_job_id: str,
    session_factory,
) -> None:
    """
    Full async rendering pipeline.  All steps run inside a single event loop
    so DB sessions, httpx clients, and asyncio primitives share the same loop.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.tenant import Tenant
    from app.models.video_job import VideoJob, VideoJobStatus

    # ── Phase 1: Load job & tenant ────────────────────────────────────────────
    async with session_factory() as db:
        result = await db.execute(
            select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
        )
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"VideoJob {video_job_id} not found — nothing to render")
            return

        result = await db.execute(
            select(Tenant).where(Tenant.id == job.tenant_id)
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            logger.error(f"Tenant {job.tenant_id} not found for job {video_job_id}")
            await _mark_failed(db, job, "Tenant record not found")
            return

        # ── Phase 2: Mark PROCESSING ──────────────────────────────────────────
        job.status = VideoJobStatus.PROCESSING.value
        job.started_at = datetime.now(timezone.utc)
        job.progress = 5
        job.progress_msg = "Initializing render pipeline..."
        await db.commit()

        logger.info(
            f"render_pipeline started "
            f"job={video_job_id} type={job.video_type} tenant={job.tenant_id}"
        )

    # ── Phase 3–12: Render in isolated temp directory ─────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"axis_video_{video_job_id[:8]}_"))
    logger.info(f"tmp_dir={tmp_dir}")

    try:
        await _render_with_cleanup(
            video_job_id=video_job_id,
            session_factory=session_factory,
            tenant=tenant,
            tmp_dir=tmp_dir,
        )
    finally:
        # Always clean up temp files — even on failure
        _cleanup_tmp(tmp_dir)


async def _render_with_cleanup(
    video_job_id: str,
    session_factory,
    tenant,
    tmp_dir: Path,
) -> None:
    """
    Phases 3–12.  Wraps the full render in try/except so the job is always
    marked DONE or FAILED regardless of what goes wrong.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.video_job import VideoJob, VideoJobStatus
    from app.services.video.registry import ProviderRegistry
    from app.services.video import RenderResult
    from app.services.video import ffmpeg_gate, storage as video_storage, thumbnail

    storage = video_storage.VideoStorageService()

    async def _load_fresh_job() -> VideoJob:
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            return result.scalar_one()

    async def _save_job(**kwargs) -> None:
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            job = result.scalar_one()
            for k, v in kwargs.items():
                setattr(job, k, v)
            await db.commit()

    job = await _load_fresh_job()

    try:
        # ── Phase 3: Build providers ──────────────────────────────────────────
        await _save_job(progress=10, progress_msg="Building provider bundle...")
        registry = ProviderRegistry(tenant)
        providers = registry.get_providers()
        logger.info(
            f"providers resolved: {providers.provider_names} job={video_job_id}"
        )

        # ── Phase 4: Resolve renderer class ──────────────────────────────────
        renderer_class = ProviderRegistry.get_renderer_class(job.video_type)
        logger.info(
            f"renderer={renderer_class.__name__} job={video_job_id}"
        )

        # ── Phase 5: Run renderer ─────────────────────────────────────────────
        await _save_job(progress=15, progress_msg="Starting render...")
        renderer = renderer_class(
            job=job,
            providers=providers,
            tmp_dir=tmp_dir,
            session_factory=session_factory,
        )
        render_result: RenderResult = await renderer.render()

        logger.info(
            f"render complete: duration={render_result.duration_seconds:.1f}s "
            f"raw_mp4={render_result.raw_mp4_path} job={video_job_id}"
        )

        # ── Phase 6: FFmpeg quality gate ──────────────────────────────────────
        await _save_job(progress=80, progress_msg="Encoding to enterprise standard...")
        resolution = (job.settings or {}).get("resolution", "1080p")
        encoded_path = tmp_dir / "encoded.mp4"
        await ffmpeg_gate.encode(
            input_path=render_result.raw_mp4_path,
            output_path=encoded_path,
            resolution=resolution,
        )

        # ── Phase 7: Upload MP4 ───────────────────────────────────────────────
        await _save_job(progress=90, progress_msg="Uploading video...")
        output_url = await storage.upload_mp4(
            local_path=encoded_path,
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
        )

        # ── Phase 8: Extract + upload thumbnail ───────────────────────────────
        await _save_job(progress=94, progress_msg="Generating thumbnail...")
        thumb_local = tmp_dir / "thumb.jpg"
        await thumbnail.extract(mp4_path=encoded_path, output_path=thumb_local)
        thumbnail_url = await storage.upload_thumbnail(
            local_path=thumb_local,
            tenant_id=str(job.tenant_id),
            job_id=str(job.id),
        )

        # ── Phase 9: Mark DONE ────────────────────────────────────────────────
        file_size = encoded_path.stat().st_size if encoded_path.exists() else None
        duration_rounded = int(render_result.duration_seconds)

        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            job = result.scalar_one()
            job.status        = VideoJobStatus.DONE.value
            job.progress      = 100
            job.progress_msg  = "Done"
            job.output_url    = output_url
            job.thumbnail_url = thumbnail_url
            job.duration_sec  = duration_rounded
            job.file_size_bytes = file_size
            job.completed_at  = datetime.now(timezone.utc)
            job.provider_used = providers.provider_names
            await db.commit()

        logger.info(
            f"render_video DONE job={video_job_id} "
            f"url={output_url} duration={duration_rounded}s"
        )

        # ── Phase 10: Fire callback ────────────────────────────────────────────
        if job.callback_url:
            await _fire_callback(
                callback_url=job.callback_url,
                moodle_job_id=job.moodle_job_id,
                status="done",
                output_url=output_url,
                thumbnail_url=thumbnail_url,
                duration_sec=duration_rounded,
                error_message=None,
            )

    except Exception as exc:  # noqa: BLE001
        logger.error(
            f"render_video FAILED job={video_job_id}: {exc}",
            exc_info=True,
        )
        # Load a fresh copy so we don't risk stale ORM state
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            failed_job = result.scalar_one_or_none()
            if failed_job:
                from datetime import datetime, timezone
                from app.models.video_job import VideoJobStatus
                failed_job.status        = VideoJobStatus.FAILED.value
                failed_job.error_message = str(exc)[:2000]
                failed_job.progress      = 0
                failed_job.progress_msg  = "Failed"
                failed_job.completed_at  = datetime.now(timezone.utc)
                await db.commit()

                if failed_job.callback_url:
                    await _fire_callback(
                        callback_url=failed_job.callback_url,
                        moodle_job_id=failed_job.moodle_job_id,
                        status="failed",
                        output_url=None,
                        thumbnail_url=None,
                        duration_sec=None,
                        error_message=str(exc)[:500],
                    )
        raise   # Re-raise so Celery can retry if retries remain


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _mark_failed(db, job, message: str) -> None:
    """Set job status to FAILED in the current session."""
    from datetime import datetime, timezone
    from app.models.video_job import VideoJobStatus

    job.status        = VideoJobStatus.FAILED.value
    job.error_message = message
    job.progress      = 0
    job.progress_msg  = "Failed"
    job.completed_at  = datetime.now(timezone.utc)
    await db.commit()


async def _fire_callback(
    callback_url: str,
    moodle_job_id: int,
    status: str,
    output_url: str | None,
    thumbnail_url: str | None,
    duration_sec: int | None,
    error_message: str | None,
) -> None:
    """
    POST result to Moodle's callback endpoint.

    Moodle plugin local_edzaxisvideo handles this in callback.php.
    Never raises — a failed callback is logged and ignored so it doesn't
    roll back an otherwise successful render.
    """
    import httpx

    payload = {
        "job_id":        moodle_job_id,
        "status":        status,           # "done" | "failed"
        "output_url":    output_url,
        "thumbnail_url": thumbnail_url,
        "duration_sec":  duration_sec,
        "error_message": error_message,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(callback_url, json=payload)
            response.raise_for_status()
        logger.info(
            f"callback fired: moodle_job={moodle_job_id} "
            f"status={status} url={callback_url}"
        )
    except Exception as exc:  # noqa: BLE001
        # Callback failure must never fail the task — the video is already uploaded
        logger.warning(
            f"callback failed (non-fatal): moodle_job={moodle_job_id} "
            f"url={callback_url} error={exc}"
        )


def _cleanup_tmp(tmp_dir: Path) -> None:
    """Delete the temp directory tree. Errors are logged and swallowed."""
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.debug(f"tmp_dir cleaned: {tmp_dir}")
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"tmp_dir cleanup failed: {tmp_dir} — {exc}")
