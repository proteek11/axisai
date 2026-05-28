"""
Celery tasks for the Skills system.

award_skills
    Fired after a learner completes a content item.
    Delegates to skills_service.award_skills_for_completion() via a
    fresh async engine (avoids event-loop mismatch — same pattern as
    process_content.py).
"""
import asyncio
import uuid

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(
    bind=True,
    name="app.tasks.skills_tasks.award_skills",
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def award_skills(self, user_id: str, content_item_id: str, tenant_id: str) -> dict:
    """
    Award skills to a learner after completing a content item.

    Creates a fresh SQLAlchemy async engine inside the task's own event loop
    to avoid the "Future attached to a different loop" error that would occur
    if the module-level engine/session-factory were reused across
    asyncio.run() calls.

    Returns:
        {"awarded": [list of skill dicts], "count": int}
    """
    from app.services import skills_service
    from app.config import settings

    logger.info(
        f"award_skills starting user={user_id} content={content_item_id} tenant={tenant_id}"
    )

    async def _run() -> dict:
        from sqlalchemy.ext.asyncio import (
            create_async_engine,
            async_sessionmaker,
            AsyncSession,
        )

        engine = create_async_engine(settings.database_url, echo=False, future=True)
        factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        try:
            async with factory() as db:
                result = await skills_service.award_skills_for_completion(
                    uuid.UUID(user_id),
                    uuid.UUID(content_item_id),
                    db,
                )
            return {"awarded": result, "count": len(result)}
        finally:
            await engine.dispose()

    try:
        outcome = asyncio.run(_run())
        logger.info(
            f"award_skills complete user={user_id} "
            f"content={content_item_id} count={outcome['count']}"
        )
        return outcome

    except Exception as exc:
        logger.error(
            f"award_skills failed user={user_id} content={content_item_id}: {exc}"
        )
        try:
            raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))
        except self.MaxRetriesExceededError:
            return {
                "awarded": [],
                "count": 0,
                "error": str(exc),
                "status": "failed",
            }
