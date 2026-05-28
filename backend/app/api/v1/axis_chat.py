"""
JWT-compatible chat endpoint for the axis.edzlms.com frontend.

The existing chat.py uses Moodle tenant API key auth. This module wraps
the same underlying chat service using the axis JWT user system instead.

Routes (all require axis JWT auth):
  POST /axis/chat/sessions             — create or retrieve a session
  POST /axis/chat/sessions/{id}/message — send a message, get AI response
  GET  /axis/chat/sessions/{id}/history — conversation history

The axis user is mapped to a synthetic Moodle user via their UUID so the
underlying chat service works unchanged. A dedicated axis tenant is created
at seed time (see scripts/seed_users.py).
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user, get_current_user_dep
from app.core.database import get_db, AsyncSessionFactory
from app.core.exceptions import RateLimitExceededError
from app.models.chat import ChatSession, ChatMessage
from app.models.user import AxisUser

log = structlog.get_logger(__name__)
router = APIRouter()

# ── Schemas ───────────────────────────────────────────────────────────────────


class CreateAxisSessionRequest(BaseModel):
    content_item_id: Optional[str] = None
    space_id: Optional[str] = None


class AxisSessionResponse(BaseModel):
    session_id: str
    content_item_id: Optional[str]
    created_at: str


class SendAxisMessageRequest(BaseModel):
    session_id: str
    message: str
    content_item_id: Optional[str] = None


class AxisMessageResponse(BaseModel):
    session_id: str
    answer: str
    suggestions: list[str] = []
    sources: list[dict] = []


class AxisHistoryMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str
    created_at: str


class AxisHistoryResponse(BaseModel):
    session_id: str
    messages: list[AxisHistoryMessage]


# ── Session management ────────────────────────────────────────────────────────


@router.post(
    "/axis/chat/sessions",
    response_model=AxisSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_axis_chat_session(
    req: CreateAxisSessionRequest,
    current_user: AxisUser = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Create a new chat session tied to this axis user + optional content item."""
    # Check for existing open session to avoid duplication
    if req.content_item_id:
        existing = (
            await db.execute(
                select(ChatSession).where(
                    ChatSession.axis_user_id == current_user.id,
                    ChatSession.content_item_id == uuid.UUID(req.content_item_id),
                )
                .order_by(ChatSession.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing:
            return AxisSessionResponse(
                session_id=str(existing.id),
                content_item_id=str(existing.content_item_id) if existing.content_item_id else None,
                created_at=existing.created_at.isoformat(),
            )

    session = ChatSession(
        axis_user_id=current_user.id,
        content_item_id=uuid.UUID(req.content_item_id) if req.content_item_id else None,
        tenant_id=current_user.tenant_id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)

    return AxisSessionResponse(
        session_id=str(session.id),
        content_item_id=str(session.content_item_id) if session.content_item_id else None,
        created_at=session.created_at.isoformat(),
    )


# ── Send message ──────────────────────────────────────────────────────────────


@router.post(
    "/axis/chat/sessions/{session_id}/message",
    response_model=AxisMessageResponse,
)
async def send_axis_chat_message(
    session_id: str,
    req: SendAxisMessageRequest,
    current_user: AxisUser = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a message and receive an AI response.

    Uses the same RAG pipeline as the Moodle chat, but authenticated via
    the axis JWT system rather than the tenant API key.
    """
    # Verify session belongs to this user
    session = (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == uuid.UUID(session_id),
                ChatSession.axis_user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    # Import the process_message service — same pipeline as Moodle chat
    try:
        from app.services.chat.axis_message import process_axis_message

        response = await process_axis_message(
            db=db,
            session_factory=AsyncSessionFactory,
            session=session,
            user=current_user,
            message=req.message,
        )

        return AxisMessageResponse(
            session_id=session_id,
            answer=response.get("answer", ""),
            suggestions=response.get("suggestions", []),
            sources=response.get("sources", []),
        )

    except Exception as e:
        log.error("axis_chat_failed", error=str(e), session_id=session_id)
        # Return a graceful fallback rather than a 500 — the chat UI should
        # still show the error in a user-friendly way
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat is temporarily unavailable. Please try again in a moment.",
        )


# ── History ───────────────────────────────────────────────────────────────────


@router.get(
    "/axis/chat/sessions/{session_id}/history",
    response_model=AxisHistoryResponse,
)
async def get_axis_chat_history(
    session_id: str,
    current_user: AxisUser = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return the message history for a chat session."""
    session = (
        await db.execute(
            select(ChatSession).where(
                ChatSession.id == uuid.UUID(session_id),
                ChatSession.axis_user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")

    messages = (
        await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at.asc())
        )
    ).scalars().all()

    return AxisHistoryResponse(
        session_id=session_id,
        messages=[
            AxisHistoryMessage(
                role=m.role,
                content=m.content,
                created_at=m.created_at.isoformat(),
            )
            for m in messages
        ],
    )
