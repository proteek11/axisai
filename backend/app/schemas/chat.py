"""
Chat API schemas — request and response Pydantic models.

Design principles:
  - All IDs as UUID type for consistency with the rest of the API
  - response_type + default_message: Python classifies, Moodle may override display
  - suggestions: structured array — Moodle renders as chips/buttons
  - visual_data: Chart.js-compatible or Mermaid — Moodle renders client-side
  - meta: token/cost/latency data for admin dashboard, never shown to students
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Suggestion Types ──────────────────────────────────────────────────────────

class ChatSuggestion(BaseModel):
    """A follow-up suggestion returned alongside every AI response."""
    id: str = Field(..., description="Short ID like 's1', 's2' — for click tracking")
    type: Literal["follow_up_question", "action", "related_topic"]
    label: str = Field(..., description="Display text shown on the chip/button")
    action: Literal["ask", "quiz_me", "visualize", "explain_more", "summarize"]
    payload: str | None = Field(
        None,
        description="Message to send when clicked (null for action types like quiz_me)"
    )


# ── RAG Source ────────────────────────────────────────────────────────────────

class ChatSource(BaseModel):
    """A course material chunk that was used to answer the question."""
    content_item_id: str
    title: str | None = None
    chunk_text: str = Field(..., description="The relevant text excerpt")
    relevance_score: float = Field(..., ge=0.0, le=1.0)


# ── Session Endpoints ─────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """
    Create a new chat session.
    Called by Moodle after validating enrollment.
    """
    moodle_user_id: int
    moodle_course_id: int | None = None
    moodle_cmid: int | None = None
    language: str = Field("en", description="ISO 639-1 response language code")
    chat_mode: str = Field(
        "study",
        description="study|support|learning — controls which Qdrant collection is searched. "
                    "'study' = course content RAG; 'support' = admin KB docs; 'learning' = future personalised mode."
    )
    scoped_content_ids: list[str] | None = Field(
        None,
        description="Restrict RAG to specific content item UUIDs. Null = all course content. Only applies to 'study' mode."
    )
    session_config: dict = Field(default_factory=dict)


class SessionResponse(BaseModel):
    """Response when creating or fetching a session."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    moodle_user_id: int
    moodle_course_id: int | None
    moodle_cmid: int | None
    language: str
    chat_mode: str
    title: str | None
    message_count: int
    total_tokens_used: int
    is_active: bool
    created_at: datetime
    current_topic_tags: list[str] | None = None


# ── Message Endpoints ─────────────────────────────────────────────────────────

class SendMessageRequest(BaseModel):
    """
    Send a message in an existing session.
    Called by Moodle on every user submission.
    """
    session_id: uuid.UUID
    message: str = Field(..., min_length=1, max_length=4000)
    suggestion_clicked_id: str | None = Field(
        None,
        description="The suggestion.id that was clicked to trigger this message (for analytics)"
    )
    language: str | None = Field(
        None,
        description="Override response language for this message (uses session default if null)"
    )


class ResponseMeta(BaseModel):
    """Internal metadata — for admin dashboard, never display to students."""
    tokens_prompt: int
    tokens_completion: int
    tokens_total: int
    model: str
    provider: str
    latency_ms: int
    rag_chunks_retrieved: int
    rag_chunks_used: int
    estimated_cost_usd: float | None = None


class MessageResponse(BaseModel):
    """
    Full response to a user message.

    response_type: Python's classification — Moodle maps this to its own display text.
    default_message: Fallback display text if Moodle doesn't override for this response_type.
    answer: The actual AI-generated answer (null if response_type != ANSWER / LOW_CONFIDENCE).
    suggestions: Rendered as clickable chips/buttons in the UI.
    visual_data: Chart.js or Mermaid data — render client-side with JS.
    sources: Course material citations — show as collapsible references.
    meta: Token/cost/latency data — only for admin/teacher dashboards.
    """
    session_id: uuid.UUID
    message_id: uuid.UUID

    # ── Core response ─────────────────────────────────────────────────────────
    response_type: str = Field(
        ...,
        description="ANSWER|LOW_CONFIDENCE|NO_CONTEXT|OUT_OF_SCOPE|AMBIGUOUS|ERROR"
    )
    default_message: str | None = Field(
        None,
        description="Default display message for non-ANSWER types. Moodle can override."
    )
    answer: str | None = Field(
        None,
        description="AI-generated answer in markdown. Null for NO_CONTEXT/OUT_OF_SCOPE."
    )
    intent: str = Field(..., description="Detected user intent (ChatIntent enum value)")

    # ── Rendering ─────────────────────────────────────────────────────────────
    render_hint: str = Field(
        "markdown",
        description="text|markdown|visual_chart|visual_mermaid — how client renders answer"
    )
    visual_data: dict | Any | None = Field(
        None,
        description="Chart.js data object OR {'mermaid': '...'} string"
    )

    # ── Citations ─────────────────────────────────────────────────────────────
    sources: list[ChatSource] = Field(
        default_factory=list,
        description="Course material chunks that grounded this answer"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Answer confidence score")

    # ── Follow-ups ────────────────────────────────────────────────────────────
    suggestions: list[ChatSuggestion] = Field(
        default_factory=list,
        description="Follow-up chips/buttons for the student"
    )

    # ── Metadata ──────────────────────────────────────────────────────────────
    meta: ResponseMeta


# ── History Endpoint ──────────────────────────────────────────────────────────

class MessageHistoryItem(BaseModel):
    """Single message in the history list."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    intent: str | None
    response_type: str | None
    render_hint: str | None
    visual_data: dict | None = None
    suggestions: list[dict] | None = None
    sources: list[dict] | None = None
    confidence_score: float | None
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    """Full conversation history for a session — used to restore UI on page reload."""
    session_id: uuid.UUID
    title: str | None
    language: str
    message_count: int
    messages: list[MessageHistoryItem]


# ── End Session ───────────────────────────────────────────────────────────────

class EndSessionRequest(BaseModel):
    session_id: uuid.UUID
