"""
Individual output generation tasks.
Each can be retried independently — important for long jobs with many generators.
Phase 1: Stubs. Phase 4: Real generation.
"""
from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)


@shared_task(name="app.tasks.generate_outputs.generate_summary", acks_late=True)
def generate_summary(content_item_id: str, tenant_id: str, **kwargs) -> dict:
    logger.info(f"Generate summary for {content_item_id} (stub)")
    return {"status": "stub"}


@shared_task(name="app.tasks.generate_outputs.generate_flashcards", acks_late=True)
def generate_flashcards(content_item_id: str, tenant_id: str, **kwargs) -> dict:
    logger.info(f"Generate flashcards for {content_item_id} (stub)")
    return {"status": "stub"}


@shared_task(name="app.tasks.generate_outputs.generate_quiz", acks_late=True)
def generate_quiz(content_item_id: str, tenant_id: str, **kwargs) -> dict:
    logger.info(f"Generate quiz for {content_item_id} (stub)")
    return {"status": "stub"}


@shared_task(name="app.tasks.generate_outputs.generate_glossary", acks_late=True)
def generate_glossary(content_item_id: str, tenant_id: str, **kwargs) -> dict:
    logger.info(f"Generate glossary for {content_item_id} (stub)")
    return {"status": "stub"}


@shared_task(name="app.tasks.generate_outputs.generate_mindmap", acks_late=True)
def generate_mindmap(content_item_id: str, tenant_id: str, **kwargs) -> dict:
    logger.info(f"Generate mindmap for {content_item_id} (stub)")
    return {"status": "stub"}
