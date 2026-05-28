"""
Chat orchestrator — the main entry point for processing a chat message.

Full flow per message:
  0. Sanitize input (strip control chars, prompt injection check)
  0b. Rate limit check (cooldown → session max → user daily)
  0c. Set cooldown key immediately (blocks rapid-fire before any LLM work)
  0d. Session TTL check (auto-expire sessions idle > TTL hours)
  1. Load session + history from DB
  2. Classify intent (fast LLM call) → also detects message language
  3. Retrieve relevant chunks from Qdrant (RAG)
  4. Compute confidence + pre-classify response_type
  5. Build chat prompt (history + context + question)
  6. Call main LLM (chat_answer prompt) — responds in detected language
  7. Parse structured response (answer, suggestions, visual_data)
  8. Save user message + assistant message to DB
  9. Update session (token totals, topic_tags, message_count)
  10. Write UserLearningEvent (in same transaction)
  11. Record token usage in rate limiter (best-effort)
  12. Return MessageResponse to the router

Also handles:
  - Session creation (with SESSION_START learning event)
  - Session history loading (full message history for UI restore)
  - Session ending (with SESSION_END learning event)

Security layers:
  - Input sanitization: control chars, unicode normalization, injection patterns
  - Structured JSON output: LLM cannot "escape" into instruction mode
  - Rate limiting: cooldown + session cap + daily + monthly
  - Session ownership: every load validates tenant_id
  - Session TTL: idle sessions auto-expired at message-send time

Language:
  - Intent classifier detects the language of every message
  - Response language = detected_language (user's actual language wins)
  - Falls back to session.language if detection fails or message is too short
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.qdrant import get_qdrant
from app.models.chat import (
    ChatMessage,
    ChatMessageRole,
    ChatResponseType,
    ChatSession,
)
from app.models.learning_event import LearningEventType
from app.models.tenant import Tenant
from app.schemas.chat import (
    ChatSource,
    ChatSuggestion,
    CreateSessionRequest,
    MessageResponse,
    ResponseMeta,
    SendMessageRequest,
    SessionHistoryResponse,
    SessionResponse,
    MessageHistoryItem,
)
from app.core.redis import get_redis
from app.services.ai.client import AIClient
from app.services.chat.builder import (
    build_chat_messages,
    determine_response_type,
)
from app.services.chat.intent import classify_intent
from app.services.chat.learning_events import write_learning_event, write_session_event
from app.services.chat.parser import parse_chat_response, ParsedChatResponse
from app.services.chat.rate_limiter import ChatRateLimiter
from app.services.chat.retriever import RetrievedChunk, compute_confidence, retrieve_chunks
from app.services.chat.sanitizer import SanitizationError, sanitize_message
from app.utils.cost import estimate_cost

log = structlog.get_logger(__name__)

# History window loaded from DB (we load more than the prompt uses — the
# intent classifier and context-threading code may need the full window)
DB_HISTORY_LOAD = 20

# When message_count exceeds this, generate a rolling session summary
SUMMARY_THRESHOLD = 15

# Model to use for high-stakes intents
_HIGH_STAKES_INTENTS = {"QUIZ_ME", "COMPARE"}


def _get_chat_model(intent: str, session_config: dict) -> str:
    """Select the model for the main chat completion."""
    # Session-level model override (set by admin/teacher)
    if session_config.get("model"):
        return session_config["model"]
    # Intent-based routing
    if intent in _HIGH_STAKES_INTENTS:
        return "gpt-4o"   # more capable for quiz generation + comparisons
    return settings.default_chat_model


async def _load_recent_history(db: AsyncSession, session_id: uuid.UUID) -> list[ChatMessage]:
    """Load recent messages for a session, ordered oldest first."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(DB_HISTORY_LOAD)
    )
    messages = result.scalars().all()
    # Reverse to chronological order
    return list(reversed(messages))


async def _get_prior_chunk_ids(messages: list[ChatMessage]) -> list[str]:
    """
    Extract Qdrant chunk IDs from the last assistant message.
    Used to bias RAG retrieval toward the current conversation topic.
    """
    for msg in reversed(messages):
        if msg.role == ChatMessageRole.ASSISTANT and msg.retrieved_chunks:
            return [
                c.get("chunk_id", "")
                for c in msg.retrieved_chunks
                if c.get("chunk_id")
            ]
    return []


# ── Session Management ────────────────────────────────────────────────────────

async def create_session(
    db: AsyncSession,
    tenant: Tenant,
    req: CreateSessionRequest,
) -> SessionResponse:
    """Create a new chat session and write a SESSION_START learning event."""
    session = ChatSession(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        moodle_user_id=req.moodle_user_id,
        moodle_course_id=req.moodle_course_id,
        moodle_cmid=req.moodle_cmid,
        language=req.language,
        chat_mode=req.chat_mode,
        scoped_content_ids=req.scoped_content_ids,
        session_config=req.session_config,
        total_tokens_used=0,
        message_count=0,
        is_active=True,
    )
    db.add(session)
    await db.flush()

    # Write SESSION_START learning event
    await write_session_event(
        db,
        tenant_id=tenant.id,
        moodle_user_id=req.moodle_user_id,
        moodle_course_id=req.moodle_course_id,
        moodle_cmid=req.moodle_cmid,
        chat_session_id=session.id,
        event_type=LearningEventType.SESSION_START.value,
    )

    await db.commit()
    await db.refresh(session)

    log.info(
        "chat_session_created",
        session_id=str(session.id),
        user=req.moodle_user_id,
        course=req.moodle_course_id,
    )

    return SessionResponse.model_validate(session)


async def get_session_history(
    db: AsyncSession,
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> SessionHistoryResponse:
    """Load a session and its full message history (for UI restore on page reload)."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return None

    messages_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
    )
    messages = messages_result.scalars().all()

    return SessionHistoryResponse(
        session_id=session.id,
        title=session.title,
        language=session.language,
        message_count=session.message_count,
        messages=[
            MessageHistoryItem(
                id=msg.id,
                role=msg.role,
                content=msg.content,
                intent=msg.intent,
                response_type=msg.response_type,
                render_hint=msg.render_hint,
                visual_data=msg.visual_data,
                suggestions=msg.suggestions,
                sources=msg.retrieved_chunks,
                confidence_score=msg.confidence_score,
                created_at=msg.created_at,
            )
            for msg in messages
        ],
    )


async def end_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> bool:
    """Mark a session as ended and write a SESSION_END learning event."""
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.tenant_id == tenant_id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        return False

    session.is_active = False
    session.ended_at = datetime.now(timezone.utc)

    await write_session_event(
        db,
        tenant_id=tenant_id,
        moodle_user_id=session.moodle_user_id,
        moodle_course_id=session.moodle_course_id,
        moodle_cmid=session.moodle_cmid,
        chat_session_id=session_id,
        event_type=LearningEventType.SESSION_END.value,
    )

    await db.commit()
    return True


# ── Main Message Processing ───────────────────────────────────────────────────

async def process_message(
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    tenant: Tenant,
    req: SendMessageRequest,
) -> MessageResponse:
    """
    Process a user message end-to-end and return a structured response.
    This is the single entry point called by the chat router.
    """
    start_time = time.perf_counter()

    # ── 0. Input sanitization ─────────────────────────────────────────────────
    try:
        clean_message = sanitize_message(req.message)
    except SanitizationError as e:
        log.warning("chat_message_blocked", reason=e.reason, score=e.score)
        return _blocked_response(req.session_id, e.reason)
    except ValueError as e:
        return _error_response(req.session_id, str(e))

    # ── 0b. Load session (needed for rate limit checks) ───────────────────────
    session_result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == req.session_id,
            ChatSession.tenant_id == tenant.id,
        )
    )
    session = session_result.scalar_one_or_none()
    if not session:
        return _error_response(req.session_id, "Session not found")

    # ── 0c. Session TTL check — auto-expire idle sessions ─────────────────────
    if session.is_active:
        ttl_hours = settings.chat_session_ttl_hours
        if session.updated_at:
            idle_hours = (
                datetime.now(timezone.utc) - session.updated_at.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            if idle_hours > ttl_hours:
                session.is_active = False
                session.ended_at = datetime.now(timezone.utc)
                await write_session_event(
                    db,
                    tenant_id=tenant.id,
                    moodle_user_id=session.moodle_user_id,
                    moodle_course_id=session.moodle_course_id,
                    moodle_cmid=session.moodle_cmid,
                    chat_session_id=session.id,
                    event_type=LearningEventType.SESSION_END.value,
                )
                await db.commit()
                log.info(
                    "chat_session_expired_ttl",
                    session_id=str(session.id),
                    idle_hours=round(idle_hours, 1),
                )
                return _error_response(
                    req.session_id,
                    f"Session expired after {ttl_hours}h of inactivity. Please start a new session.",
                )

    if not session.is_active:
        return _error_response(req.session_id, "Session has ended. Please start a new session.")

    # ── 0d. Rate limit checks ─────────────────────────────────────────────────
    redis = await get_redis()
    rate_limiter = ChatRateLimiter(redis)

    # Check FIRST (cooldown from a previous message, session cap, daily limit)
    # — must happen before set_cooldown, otherwise the newly-set key would
    #   always trigger the cooldown check on the very same request.
    await rate_limiter.check_pre_message(
        tenant_id=str(tenant.id),
        moodle_user_id=session.moodle_user_id,
        session_message_count=session.message_count or 0,
    )

    # Set cooldown key AFTER passing all checks — blocks rapid-fire on the
    # NEXT request before any LLM work starts there.
    await rate_limiter.set_cooldown(str(tenant.id), session.moodle_user_id)

    # ── 1. Load recent history ────────────────────────────────────────────────
    history = await _load_recent_history(db, session.id)
    prior_chunk_ids = await _get_prior_chunk_ids(history)

    # ── 2. Set up AIClient with full context for audit logging ────────────────
    ai_client = AIClient(
        session_factory=session_factory,
        tenant_id=str(tenant.id),
        moodle_user_id=session.moodle_user_id,
        moodle_course_id=session.moodle_course_id,
        moodle_cmid=session.moodle_cmid,
        chat_session_id=str(session.id),
    )

    # ── 3. Classify intent + detect language ─────────────────────────────────
    intent_result = await classify_intent(
        message=clean_message,
        history=history,
        ai_client=ai_client,
    )

    # Language resolution: detected > explicit override > session default
    # Only trust detected_language if message is long enough (short messages
    # like "ok" or "yes" often mis-detect as unknown language)
    if len(clean_message) >= 15 and intent_result.detected_language not in ("", "en"):
        language = intent_result.detected_language
    elif req.language:
        language = req.language
    else:
        language = session.language

    log.info(
        "chat_intent_classified",
        intent=intent_result.intent,
        detected_lang=intent_result.detected_language,
        response_lang=language,
        tags=intent_result.topic_tags,
        is_continuation=intent_result.is_continuation,
        session_id=str(session.id),
    )

    # ── 5. RAG retrieval — route to correct collection based on chat_mode ────
    qdrant = get_qdrant()
    chunks = await retrieve_chunks(
        query=intent_result.rephrased_query,
        tenant_id=str(tenant.id),
        ai_client=ai_client,
        qdrant=qdrant,
        chat_mode=session.chat_mode or "study",
        moodle_course_id=session.moodle_course_id,
        scoped_content_ids=session.scoped_content_ids,
        prior_chunk_ids=prior_chunk_ids if intent_result.is_continuation else [],
        intent=intent_result.intent,
    )

    confidence = compute_confidence(chunks)
    pre_response_type = determine_response_type(
        confidence=confidence,
        chunks_count=len(chunks),
        intent=intent_result.intent,
    )

    # ── 6. Build prompt + call LLM ────────────────────────────────────────────
    model = _get_chat_model(intent_result.intent, session.session_config)

    messages_payload, prompt_config = build_chat_messages(
        question=intent_result.rephrased_query,
        intent=intent_result.intent,
        language=language,
        history=history,
        chunks=chunks,
        session_summary=session.session_summary,
        chat_mode=session.chat_mode or "study",
    )

    llm_response = await ai_client.complete(
        messages=messages_payload,
        model=model,
        task_type="chat",
        temperature=prompt_config["temperature"],
        max_tokens=prompt_config["max_tokens"],
        response_format={"type": "json_object"},
    )

    raw_content = llm_response.choices[0].message.content
    usage = llm_response.usage

    # ── 7. Parse response ─────────────────────────────────────────────────────
    parsed: ParsedChatResponse = parse_chat_response(
        raw_content=raw_content,
        fallback_confidence=confidence,
        fallback_response_type=pre_response_type,
        chat_mode=session.chat_mode or "study",
    )

    # Merge topic_tags: use LLM's tags if available, else use intent classifier's
    final_topic_tags = parsed.topic_tags if parsed.topic_tags else intent_result.topic_tags

    total_latency_ms = int((time.perf_counter() - start_time) * 1000)
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0

    # ── 8. Save messages to DB ────────────────────────────────────────────────
    user_msg = ChatMessage(
        id=uuid.uuid4(),
        session_id=session.id,
        role=ChatMessageRole.USER,
        content=clean_message,       # store the sanitized version
        intent=intent_result.intent,
        suggestion_clicked_id=req.suggestion_clicked_id,
    )
    db.add(user_msg)
    await db.flush()

    assistant_msg_id = uuid.uuid4()
    assistant_msg = ChatMessage(
        id=assistant_msg_id,
        session_id=session.id,
        role=ChatMessageRole.ASSISTANT,
        content=parsed.answer or parsed.default_message or "",
        intent=intent_result.intent,
        response_type=parsed.response_type,
        confidence_score=parsed.confidence,
        render_hint=parsed.render_hint,
        visual_data=parsed.visual_data,
        suggestions=[s.to_dict() for s in parsed.suggestions],
        retrieved_chunks=[c.to_dict() for c in chunks],
        rag_chunks_retrieved=len(chunks),
        rag_chunks_used=min(len(chunks), 8),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=total_latency_ms,
        model=model,
        provider=ai_client._get_provider(model),
    )
    db.add(assistant_msg)
    await db.flush()

    # ── 9. Update session stats ───────────────────────────────────────────────
    session.message_count = (session.message_count or 0) + 2   # user + assistant
    session.total_tokens_used = (session.total_tokens_used or 0) + prompt_tokens + completion_tokens
    session.current_topic_tags = final_topic_tags

    # Auto-generate title from first user message
    if not session.title and session.message_count <= 2:
        session.title = req.message[:80] + ("..." if len(req.message) > 80 else "")

    # ── 10. Write learning event ──────────────────────────────────────────────
    await write_learning_event(
        db,
        tenant_id=tenant.id,
        moodle_user_id=session.moodle_user_id,
        moodle_course_id=session.moodle_course_id,
        moodle_cmid=session.moodle_cmid,
        chat_session_id=session.id,
        chat_message_id=assistant_msg_id,
        intent=intent_result.intent,
        response_type=parsed.response_type,
        topic_tags=final_topic_tags,
        confidence_score=parsed.confidence,
        chunks=chunks,
        extra_metadata=(
            {"suggestion_clicked_id": req.suggestion_clicked_id}
            if req.suggestion_clicked_id else None
        ),
    )

    await db.commit()

    # ── 11. Record token usage in rate limiter (best-effort, post-commit) ─────
    await rate_limiter.record_tokens_used(
        tenant_id=str(tenant.id),
        moodle_user_id=session.moodle_user_id,
        tokens=prompt_tokens + completion_tokens,
    )

    # ── 12. Build and return response ─────────────────────────────────────────
    provider = ai_client._get_provider(model)
    cost = estimate_cost(provider, model, prompt_tokens, completion_tokens)

    sources = [
        ChatSource(
            content_item_id=c.content_item_id,
            title=c.title,
            chunk_text=c.text[:400],   # truncate for API response
            relevance_score=round(c.score, 3),
        )
        for c in chunks[:5]   # top 5 sources in response
    ]

    # In support mode, strip quiz/visual actions — they're for course study only.
    _support_blocked_actions = {"quiz_me", "visualize"}
    filtered_suggestions = parsed.suggestions
    if (session.chat_mode or "study") == "support":
        filtered_suggestions = [
            s for s in parsed.suggestions
            if s.action not in _support_blocked_actions
        ]

    suggestions = [
        ChatSuggestion(
            id=s.id,
            type=s.type,
            label=s.label,
            action=s.action,
            payload=s.payload,
        )
        for s in filtered_suggestions
    ]

    log.info(
        "chat_message_processed",
        session_id=str(session.id),
        intent=intent_result.intent,
        response_type=parsed.response_type,
        confidence=parsed.confidence,
        chunks_used=len(chunks),
        latency_ms=total_latency_ms,
        tokens=prompt_tokens + completion_tokens,
    )

    return MessageResponse(
        session_id=session.id,
        message_id=assistant_msg_id,
        response_type=parsed.response_type,
        default_message=parsed.default_message,
        answer=parsed.answer,
        intent=intent_result.intent,
        render_hint=parsed.render_hint,
        visual_data=parsed.visual_data,
        sources=sources,
        confidence=parsed.confidence,
        suggestions=suggestions,
        meta=ResponseMeta(
            tokens_prompt=prompt_tokens,
            tokens_completion=completion_tokens,
            tokens_total=prompt_tokens + completion_tokens,
            model=model,
            provider=provider,
            latency_ms=total_latency_ms,
            rag_chunks_retrieved=len(chunks),
            rag_chunks_used=assistant_msg.rag_chunks_used or 0,
            estimated_cost_usd=float(cost) if cost else None,
        ),
    )


def _error_response(session_id: uuid.UUID, reason: str) -> MessageResponse:
    """Build a safe error response — never exposes internal details."""
    return MessageResponse(
        session_id=session_id,
        message_id=uuid.uuid4(),
        response_type=ChatResponseType.ERROR.value,
        default_message="An error occurred. Please try again.",
        answer=None,
        intent="GENERAL_QUESTION",
        render_hint="text",
        visual_data=None,
        sources=[],
        confidence=0.0,
        suggestions=[],
        meta=ResponseMeta(
            tokens_prompt=0,
            tokens_completion=0,
            tokens_total=0,
            model="",
            provider="",
            latency_ms=0,
            rag_chunks_retrieved=0,
            rag_chunks_used=0,
        ),
    )


def _blocked_response(session_id: uuid.UUID, reason: str) -> MessageResponse:
    """Build a response for sanitization-blocked messages. Generic — no leak of pattern details."""
    return MessageResponse(
        session_id=session_id,
        message_id=uuid.uuid4(),
        response_type=ChatResponseType.OUT_OF_SCOPE.value,
        default_message="Your message could not be processed. Please rephrase your question.",
        answer=None,
        intent="GENERAL_QUESTION",
        render_hint="text",
        visual_data=None,
        sources=[],
        confidence=0.0,
        suggestions=[],
        meta=ResponseMeta(
            tokens_prompt=0,
            tokens_completion=0,
            tokens_total=0,
            model="",
            provider="",
            latency_ms=0,
            rag_chunks_retrieved=0,
            rag_chunks_used=0,
        ),
    )
