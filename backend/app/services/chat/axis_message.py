"""
process_axis_message — Axis-native chat pipeline.

Called by axis_chat.py (JWT-authenticated frontend endpoints).
Reuses the RAG retriever, prompt builder, and AI client from the
Moodle-compatible chat pipeline, but without the Tenant object.

Flow:
  1. Load recent history from DB
  2. Retrieve RAG chunks (if session has content_item_id)
  3. Build prompt via chat_answer YAML template
  4. Call LLM
  5. Parse answer + suggestions + sources
  6. Persist user message + assistant message
  7. Update session counters
  8. Return dict {answer, suggestions, sources}
"""
from __future__ import annotations

import time
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.core.qdrant import get_qdrant
from app.models.chat import ChatMessage, ChatMessageRole, ChatSession
from app.models.user import AxisUser
from app.services.ai.client import AIClient
from app.services.chat.builder import build_chat_messages
from app.services.chat.parser import parse_chat_response
from app.services.chat.retriever import retrieve_chunks

log = structlog.get_logger(__name__)

# Number of recent messages included in the history block
HISTORY_WINDOW = 10


async def process_axis_message(
    *,
    db: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    session: ChatSession,
    user: AxisUser,
    message: str,
) -> dict:
    """
    Process a chat message for an axis frontend user and return a response dict.

    Returns:
        {
            "answer":      str,
            "suggestions": list[str],   # plain-text follow-up chips
            "sources":     list[dict],  # [{title, chunk_text, relevance_score}]
        }
    """
    start = time.perf_counter()

    # ── 1. Load recent chat history ───────────────────────────────────────────
    history_rows = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_WINDOW)
        )
    ).scalars().all()

    # Reverse to chronological order for the prompt
    history = list(reversed(history_rows))

    # ── 2. RAG retrieval (only when session is scoped to a content item) ──────
    chunks = []
    if session.content_item_id and session.tenant_id:
        try:
            ai_client_embed = AIClient(session_factory=session_factory)
            qdrant = get_qdrant()
            chunks = await retrieve_chunks(
                query=message,
                tenant_id=str(session.tenant_id),
                ai_client=ai_client_embed,
                qdrant=qdrant,
                chat_mode="study",
                scoped_content_ids=[str(session.content_item_id)],
            )
        except Exception as exc:
            log.warning(
                "axis_chat_rag_failed",
                session_id=str(session.id),
                content_item_id=str(session.content_item_id),
                error=str(exc),
            )
            # Proceed without RAG context rather than failing entirely

    # ── 3. Build prompt ───────────────────────────────────────────────────────
    try:
        prompt_messages, _config = build_chat_messages(
            question=message,
            intent="GENERAL_QUESTION",
            language="en",
            history=history,
            chunks=chunks,
            session_summary=session.session_summary,
            chat_mode="study",
        )
    except Exception as exc:
        log.error("axis_chat_prompt_build_failed", error=str(exc))
        # Minimal fallback so the user still gets a response
        prompt_messages = [
            {"role": "system", "content": "You are a helpful AI study assistant."},
            {"role": "user", "content": message},
        ]

    # ── 4. Call LLM ───────────────────────────────────────────────────────────
    ai_client = AIClient(
        session_factory=session_factory,
        axis_user_id=str(user.id),
        tenant_id=str(session.tenant_id) if session.tenant_id else None,
        chat_session_id=str(session.id),
    )
    raw_response = await ai_client.complete(
        messages=prompt_messages,
        model=settings.model_chat,
        task_type="axis_chat",
        temperature=0.4,
        max_tokens=1200,
    )
    raw_text = raw_response.choices[0].message.content or ""
    prompt_tokens = raw_response.usage.prompt_tokens if raw_response.usage else 0
    completion_tokens = raw_response.usage.completion_tokens if raw_response.usage else 0
    latency_ms = int((time.perf_counter() - start) * 1000)

    # ── 5. Parse structured response ──────────────────────────────────────────
    parsed = parse_chat_response(raw_text)
    answer = parsed.answer or raw_text

    # Normalise suggestions → list[str] for the API response
    suggestions: list[str] = []
    for s in (parsed.suggestions or []):
        if hasattr(s, "label"):
            suggestions.append(s.label)
        elif isinstance(s, dict):
            suggestions.append(s.get("label") or s.get("text") or str(s))
        else:
            suggestions.append(str(s))

    # ── 6. Build sources list ─────────────────────────────────────────────────
    sources = [
        {
            "content_item_id": c.content_item_id,
            "title": c.title,
            "chunk_text": c.text[:300],
            "relevance_score": round(c.score, 3),
        }
        for c in chunks[:5]  # Top 5 sources only
    ]

    # ── 7. Persist messages ───────────────────────────────────────────────────
    user_msg = ChatMessage(
        session_id=session.id,
        role=ChatMessageRole.USER,
        content=message,
    )
    assistant_msg = ChatMessage(
        session_id=session.id,
        role=ChatMessageRole.ASSISTANT,
        content=answer,
        retrieved_chunks=[c.to_dict() for c in chunks],
        suggestions=suggestions,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        model=settings.model_chat,
        provider="openai",
    )
    db.add(user_msg)
    db.add(assistant_msg)

    # ── 8. Update session counters ────────────────────────────────────────────
    session.message_count = (session.message_count or 0) + 2
    session.total_tokens_used = (
        (session.total_tokens_used or 0) + prompt_tokens + completion_tokens
    )

    await db.commit()

    log.info(
        "axis_chat_processed",
        session_id=str(session.id),
        user_id=str(user.id),
        tokens=prompt_tokens + completion_tokens,
        latency_ms=latency_ms,
        rag_chunks=len(chunks),
    )

    return {
        "answer": answer,
        "suggestions": suggestions,
        "sources": sources,
    }
