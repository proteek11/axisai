"""
Main content processing pipeline task.
Delegates to app.services.pipeline for the actual work.
"""
# FIX 2026-03-28: Resolved asyncio event loop mismatch crashing all pipeline tasks.
# Error: "Task got Future attached to a different loop" — asyncpg's connection pool
# is created once at module import time, bound to that event loop. Each Celery task
# calls asyncio.run() which creates a NEW event loop. The existing pool cannot be
# reused in the new loop.
# Reason: The module-level AsyncSessionFactory (and the engine inside it) holds open
# asyncpg connections/futures anchored to the original loop. Passing that factory
# into asyncio.run() causes the mismatch.
# Fix:
#  1. Create a fresh SQLAlchemy engine + session factory INSIDE a single async
#     wrapper so all connections are born in the task's own event loop.
#  2. Combined the two separate asyncio.run() calls (record_task_id + pipeline)
#     into one, so there is exactly one event loop per task invocation.
#  3. Dispose the engine when done to release connections cleanly.
import asyncio

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.process_content.run_pipeline",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def run_pipeline(
    self,
    job_id: str,
    content_item_id: str,
    tenant_id: str,
    job_config: dict | None = None,
    axis_user_id: str | None = None,
) -> dict:
    """
    Full pipeline task: extract → chunk → embed → generate outputs.
    Runs the async pipeline inside a new event loop (Celery is sync).
    """
    from app.services.pipeline import run_full_pipeline
    from app.config import settings

    logger.info(f"Pipeline starting job={job_id} content={content_item_id}")

    async def _run():
        # Create a fresh engine + factory for this task's event loop.
        # This avoids the "Future attached to a different loop" error that
        # occurs when the module-level AsyncSessionFactory is reused across
        # different asyncio.run() calls (each of which creates its own loop).
        from sqlalchemy.ext.asyncio import (
            create_async_engine, async_sessionmaker, AsyncSession
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
            await _record_task_id(job_id, str(self.request.id), session_factory)
            await run_full_pipeline(
                job_id=job_id,
                content_item_id=content_item_id,
                tenant_id=tenant_id,
                job_config=job_config or {"tasks": ["summary"]},
                session_factory=session_factory,
                axis_user_id=axis_user_id,
            )
        finally:
            await engine.dispose()

    try:
        asyncio.run(_run())
        logger.info(f"Pipeline completed job={job_id}")
        return {"status": "completed", "job_id": job_id}

    except Exception as exc:
        logger.error(f"Pipeline failed job={job_id}: {exc}")
        try:
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {"status": "failed", "job_id": job_id, "error": str(exc)}


async def _record_task_id(job_id: str, celery_task_id: str, session_factory) -> None:
    """Record the Celery task ID on the ProcessingJob for status tracking."""
    import uuid
    from sqlalchemy import select
    from app.models.job import ProcessingJob

    async with session_factory() as db:
        result = await db.execute(
            select(ProcessingJob).where(ProcessingJob.id == uuid.UUID(job_id))
        )
        job = result.scalar_one_or_none()
        if job:
            job.celery_task_id = celery_task_id
            await db.commit()


@shared_task(
    name="app.tasks.process_content.translate_content",
    max_retries=3,
    acks_late=True,
)
def translate_content(job_id: str, content_item_id: str, target_language: str) -> dict:
    """Translation pipeline task. Implemented in Phase 6."""
    logger.info(f"Translate job={job_id} lang={target_language} (stub)")
    return {"status": "stub", "job_id": job_id}
