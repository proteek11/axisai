"""
Learning event writer — writes UserLearningEvent rows after every chat turn.

Design:
  - Runs AFTER the response is sent (non-blocking background task pattern)
  - Maps intent + response_type → event_type
  - Captures topic_tags and content_item_ids from the response
  - Never raises — if DB write fails, we log and move on (never break chat)
  - SESSION_START and SESSION_END are written by the chat orchestrator
    at session create/end time respectively

This is the foundation for Phase 4 personalized learning plans.
Every event logged here is raw material for the analytics engine.
"""
from __future__ import annotations

import uuid
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatIntent, ChatResponseType
from app.models.learning_event import LearningEventType, UserLearningEvent
from app.services.chat.retriever import RetrievedChunk

log = structlog.get_logger(__name__)


# Map (intent, response_type) → LearningEventType
_EVENT_TYPE_MAP: dict[tuple[str, str], str] = {
    (ChatIntent.EXPLAIN_MORE.value, ChatResponseType.ANSWER.value): LearningEventType.ASKED_EXPLAIN.value,
    (ChatIntent.EXPLAIN_MORE.value, ChatResponseType.LOW_CONFIDENCE.value): LearningEventType.ASKED_EXPLAIN.value,
    (ChatIntent.SHOW_VISUAL.value, ChatResponseType.ANSWER.value): LearningEventType.ASKED_VISUAL.value,
    (ChatIntent.SHOW_VISUAL.value, ChatResponseType.LOW_CONFIDENCE.value): LearningEventType.ASKED_VISUAL.value,
    (ChatIntent.QUIZ_ME.value, ChatResponseType.ANSWER.value): LearningEventType.ASKED_QUIZ.value,
}


def _map_event_type(intent: str, response_type: str) -> str:
    """Map intent + response_type to the appropriate LearningEventType."""
    # Check specific mappings first
    specific = _EVENT_TYPE_MAP.get((intent, response_type))
    if specific:
        return specific

    # response_type overrides for knowledge gap signals
    if response_type == ChatResponseType.NO_CONTEXT.value:
        return LearningEventType.NO_CONTEXT.value
    if response_type == ChatResponseType.LOW_CONFIDENCE.value:
        return LearningEventType.LOW_CONFIDENCE.value

    # Default: generic ASKED
    return LearningEventType.ASKED.value


async def write_learning_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    moodle_user_id: int,
    moodle_course_id: int | None,
    moodle_cmid: int | None,
    chat_session_id: uuid.UUID,
    chat_message_id: uuid.UUID,
    intent: str,
    response_type: str,
    topic_tags: list[str],
    confidence_score: float,
    chunks: list[RetrievedChunk],
    extra_metadata: dict | None = None,
) -> None:
    """
    Write a UserLearningEvent row for this chat turn.
    Never raises — logs errors silently to avoid breaking the chat flow.
    """
    try:
        event_type = _map_event_type(intent, response_type)

        content_item_ids = list(dict.fromkeys(
            c.content_item_id for c in chunks if c.content_item_id
        ))

        event = UserLearningEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            moodle_user_id=moodle_user_id,
            moodle_course_id=moodle_course_id,
            moodle_cmid=moodle_cmid,
            event_type=event_type,
            topic_tags=topic_tags if topic_tags else None,
            content_item_ids=content_item_ids if content_item_ids else None,
            intent=intent,
            response_type=response_type,
            confidence_score=confidence_score,
            chat_session_id=chat_session_id,
            chat_message_id=chat_message_id,
            event_metadata=extra_metadata,
        )

        db.add(event)
        await db.flush()   # part of the caller's transaction

        log.debug(
            "learning_event_written",
            event_type=event_type,
            user=moodle_user_id,
            course=moodle_course_id,
            topics=topic_tags,
        )

    except Exception as e:
        log.error("learning_event_write_failed", error=str(e))


async def write_session_event(
    db: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    moodle_user_id: int,
    moodle_course_id: int | None,
    moodle_cmid: int | None,
    chat_session_id: uuid.UUID,
    event_type: str,   # LearningEventType.SESSION_START or SESSION_END
) -> None:
    """Write a SESSION_START or SESSION_END event."""
    try:
        event = UserLearningEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            moodle_user_id=moodle_user_id,
            moodle_course_id=moodle_course_id,
            moodle_cmid=moodle_cmid,
            event_type=event_type,
            chat_session_id=chat_session_id,
        )
        db.add(event)
        await db.flush()
    except Exception as e:
        log.error("session_event_write_failed", event_type=event_type, error=str(e))
