"""
Celery task: generate_video_preview

Renders a 30-second preview clip for human approval before the full render.

Preview flow:
  1. POST /api/v1/video/jobs/{id}/preview
       → status = preview_pending, dispatches this task
  2. This task renders the first 30 s of the video via the normal renderer
       → status = preview_ready, preview_url populated
  3. POST /api/v1/video/jobs/{id}/approve
       → status = approved, dispatches the normal render_video task

The preview renderer is the same class as the full renderer, but:
  - settings["duration_seconds"] is capped at 30
  - Output is uploaded with a "preview_" prefix path

Worker start command:
    celery -A app.tasks.celery_app worker \\
        --queues=video --concurrency=2 --max-tasks-per-child=10 -l info

(Preview tasks share the same "video" queue as full renders.)
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

_PREVIEW_MAX_SECONDS = 30


@shared_task(
    bind=True,
    name="app.tasks.preview_video.generate_video_preview",
    acks_late=True,
    max_retries=1,
    default_retry_delay=15,
)
def generate_video_preview(self, video_job_id: str) -> dict:
    """
    Generate a 30-second preview MP4 for the given VideoJob.

    Args:
        video_job_id: UUID string of the VideoJob row.
    """
    try:
        return asyncio.run(_run(video_job_id))
    except Exception as exc:
        logger.error(
            f"generate_video_preview FAILED job={video_job_id}: {exc}",
            exc_info=True,
        )
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            asyncio.run(_mark_preview_failed(video_job_id, str(exc)))
        raise


async def _run(video_job_id: str) -> dict:
    """Async implementation — runs inside asyncio.run() in the Celery worker."""
    import copy

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

    from app.config import settings as app_settings
    from app.models.video_job import VideoJob, VideoJobStatus
    from app.services.video.registry import ProviderRegistry
    from app.services.video import RenderResult
    from app.services.video.storage import VideoStorage
    from app.services.video.ffmpeg_gate import FFmpegGate

    # ── Build a dedicated async engine (fresh event loop) ─────────────────────
    engine = create_async_engine(
        app_settings.database_url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=30,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    storage    = VideoStorage(app_settings)
    ffmpeg_gate = FFmpegGate(app_settings)

    tmp_dir = Path(tempfile.mkdtemp(prefix="axis_preview_"))

    try:
        # ── Load job + tenant ─────────────────────────────────────────────────
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(
                    VideoJob.id == _uuid.UUID(video_job_id)
                )
            )
            job = result.scalar_one_or_none()
            if job is None:
                raise ValueError(f"VideoJob {video_job_id} not found")

            from sqlalchemy import select as sa_select
            from app.models.tenant import Tenant
            tenant_result = await db.execute(
                sa_select(Tenant).where(Tenant.id == job.tenant_id)
            )
            tenant = tenant_result.scalar_one()

        # ── Mark preview as processing ────────────────────────────────────────
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            job = result.scalar_one()
            job.status        = VideoJobStatus.PREVIEW_PENDING.value
            job.progress      = 5
            job.progress_msg  = "Preview: starting…"
            job.started_at    = datetime.now(timezone.utc)
            await db.commit()

        # ── Build providers ───────────────────────────────────────────────────
        registry  = ProviderRegistry(tenant)
        providers = registry.get_providers()

        # ── Cap duration at 30 seconds ────────────────────────────────────────
        preview_settings = dict(job.settings or {})
        preview_settings["duration_seconds"] = _PREVIEW_MAX_SECONDS
        # Patch the in-memory job so the renderer sees the capped duration
        job.settings = preview_settings

        # ── Resolve renderer + run ────────────────────────────────────────────
        RendererClass  = ProviderRegistry.get_renderer_class(job.video_type)
        renderer       = RendererClass(
            job=job,
            providers=providers,
            tmp_dir=tmp_dir,
            session_factory=session_factory,
        )
        render_result: RenderResult = await renderer.render()

        # ── FFmpeg encode ─────────────────────────────────────────────────────
        resolution    = (job.settings or {}).get("resolution", "1080p")
        encoded_path  = tmp_dir / "preview_encoded.mp4"
        await ffmpeg_gate.encode(
            input_path=render_result.raw_mp4_path,
            output_path=encoded_path,
            resolution=resolution,
        )

        # ── Upload with "preview_" prefix ─────────────────────────────────────
        preview_url = await storage.upload_mp4(
            local_path=encoded_path,
            tenant_id=str(job.tenant_id),
            job_id=f"preview_{job.id}",
        )

        # ── Mark PREVIEW_READY ────────────────────────────────────────────────
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            job = result.scalar_one()
            job.status      = VideoJobStatus.PREVIEW_READY.value
            job.preview_url = preview_url
            job.progress    = 100
            job.progress_msg = "Preview ready"
            await db.commit()

        logger.info(
            f"generate_video_preview DONE job={video_job_id} "
            f"preview_url={preview_url}"
        )
        return {"status": "preview_ready", "preview_url": preview_url}

    finally:
        _cleanup_tmp(tmp_dir)
        await engine.dispose()


async def _mark_preview_failed(video_job_id: str, error: str) -> None:
    """Mark the job FAILED after max retries are exhausted."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.config import settings as app_settings
    from app.models.video_job import VideoJob, VideoJobStatus

    engine = create_async_engine(app_settings.database_url, pool_size=1, max_overflow=0)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as db:
            result = await db.execute(
                select(VideoJob).where(VideoJob.id == _uuid.UUID(video_job_id))
            )
            job = result.scalar_one_or_none()
            if job:
                job.status        = VideoJobStatus.FAILED.value
                job.error_message = f"Preview failed: {error[:1800]}"
                job.completed_at  = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()


def _cleanup_tmp(tmp_dir: Path) -> None:
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"preview tmp_dir cleanup failed: {tmp_dir} — {exc}")
