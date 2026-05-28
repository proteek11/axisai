"""
Scheduled maintenance tasks (run via Celery Beat).
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="app.tasks.maintenance.cleanup_stale_jobs")
def cleanup_stale_jobs() -> dict:
    """
    Mark jobs that have been PROCESSING for > 1 hour as FAILED.
    Guards against worker crashes that leave jobs stuck in processing.
    """
    import asyncio
    from datetime import datetime, timezone, timedelta
    from app.core.database import AsyncSessionFactory
    from app.models.job import ProcessingJob, JobStatus

    async def _run():
        async with AsyncSessionFactory() as session:
            from sqlalchemy import select, update
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            result = await session.execute(
                update(ProcessingJob)
                .where(
                    ProcessingJob.status == JobStatus.PROCESSING,
                    ProcessingJob.updated_at < cutoff,
                )
                .values(
                    status=JobStatus.FAILED,
                    error_message="Job timed out — worker may have crashed",
                )
                .returning(ProcessingJob.id)
            )
            failed_ids = result.fetchall()
            await session.commit()
            if failed_ids:
                logger.warning(f"Cleaned up {len(failed_ids)} stale jobs")
            return {"cleaned_up": len(failed_ids)}

    # asyncio.get_event_loop() raises RuntimeError in Python 3.10+ when there is
    # no current event loop on the thread (Celery worker threads). Use asyncio.run()
    # which always creates a fresh loop — same pattern as process_content.py.
    return asyncio.run(_run())


@shared_task(name="app.tasks.maintenance.aggregate_token_usage")
def aggregate_token_usage() -> dict:
    """
    Periodic aggregation of token usage for fast dashboard queries.
    Phase 8 implementation — stub for now.
    """
    logger.debug("Token usage aggregation (stub)")
    return {"status": "stub"}
