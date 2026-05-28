"""
Chat API endpoints.

Endpoints:
  POST   /api/v1/chat/sessions          — Create a new chat session
  POST   /api/v1/chat/message           — Send a message (main chat endpoint)
  GET    /api/v1/chat/sessions/{id}     — Get session info
  GET    /api/v1/chat/sessions/{id}/history  — Load full message history (UI restore)
  POST   /api/v1/chat/sessions/{id}/end — End a session

All endpoints require API key auth (same Bearer token as the rest of the API).
Moodle validates enrollment BEFORE calling these endpoints — axis-ai trusts
that the moodle_user_id in the request is authorized for this course.

Error handling:
  - 404: session not found or belongs to different tenant
  - 422: validation errors (FastAPI handles automatically)
  - 500: unexpected errors (logged, generic message returned)
"""
from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db, AsyncSessionFactory
from app.core.exceptions import RateLimitExceededError
from app.core.security import get_current_tenant
from app.models.tenant import Tenant
from app.schemas.chat import (
    CreateSessionRequest,
    EndSessionRequest,
    MessageResponse,
    SendMessageRequest,
    SessionHistoryResponse,
    SessionResponse,
)
from app.services.chat.orchestrator import (
    create_session,
    end_session,
    get_session_history,
    process_message,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Create Session ────────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
    description=(
        "Create a new chat session scoped to a Moodle user + optional course/content. "
        "Call this when the student opens the chatbot UI. "
        "Moodle MUST validate enrollment before calling this endpoint."
    ),
)
async def create_chat_session(
    req: CreateSessionRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    try:
        return await create_session(db=db, tenant=tenant, req=req)
    except Exception as e:
        log.error("create_session_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create session",
        )


# ── Send Message ──────────────────────────────────────────────────────────────

@router.post(
    "/message",
    response_model=MessageResponse,
    summary="Send a message and get an AI response",
    description=(
        "The main chat endpoint. Processes the user's message through:\n"
        "intent classification → RAG retrieval → LLM generation → "
        "response parsing → learning event logging.\n\n"
        "Returns a structured response with answer, suggestions, optional visual data, "
        "and source citations."
    ),
)
async def send_message(
    req: SendMessageRequest,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    log.info(
        "chat_message_received",
        session_id=str(req.session_id),
        message_len=len(req.message),
        tenant_id=str(tenant.id),
    )
    try:
        return await process_message(
            db=db,
            session_factory=AsyncSessionFactory,
            tenant=tenant,
            req=req,
        )
    except RateLimitExceededError as e:
        # Return 429 with Retry-After header so Moodle can display a countdown
        headers = {}
        if e.retry_after and e.retry_after > 0:
            headers["Retry-After"] = str(e.retry_after)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": str(e), "error_code": "RATE_LIMIT_EXCEEDED"},
            headers=headers,
        )
    except Exception as e:
        log.error("send_message_failed", error=str(e), session_id=str(req.session_id))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process message. Please try again.",
        )


# ── Get Session ───────────────────────────────────────────────────────────────

@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get session info",
)
async def get_session(
    session_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    from sqlalchemy import select
    from app.models.chat import ChatSession

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.tenant_id == tenant.id,
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionResponse.model_validate(session)


# ── Session History ───────────────────────────────────────────────────────────

@router.get(
    "/sessions/{session_id}/history",
    response_model=SessionHistoryResponse,
    summary="Load full conversation history",
    description=(
        "Returns all messages in a session in chronological order. "
        "Use this to restore the chat UI when a student returns to the page."
    ),
)
async def get_history(
    session_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> SessionHistoryResponse:
    result = await get_session_history(
        db=db,
        session_id=session_id,
        tenant_id=tenant.id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return result


# ── End Session ───────────────────────────────────────────────────────────────

@router.post(
    "/sessions/{session_id}/end",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End a chat session",
    description=(
        "Mark the session as ended. Writes a SESSION_END learning event. "
        "Call when the student closes the chatbot or navigates away."
    ),
)
async def end_chat_session(
    session_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> None:
    success = await end_session(
        db=db,
        session_id=session_id,
        tenant_id=tenant.id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
