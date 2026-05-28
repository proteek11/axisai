"""
Chat / Chatbot models.
Supports multi-lingual RAG-backed chatbot sessions.
Designed to be called from any frontend: Moodle plugin, Next.js app, mobile, etc.
"""
import uuid
import enum

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ChatMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatResponseType(str, enum.Enum):
    ANSWER = "ANSWER"                      # Good answer found — high confidence
    LOW_CONFIDENCE = "LOW_CONFIDENCE"      # Answer found but chunks scored below threshold
    NO_CONTEXT = "NO_CONTEXT"              # No relevant vectors found in course content
    OUT_OF_SCOPE = "OUT_OF_SCOPE"          # Question detected as irrelevant to course
    AMBIGUOUS = "AMBIGUOUS"               # Question needs clarification
    ERROR = "ERROR"                        # Internal failure


class ChatIntent(str, enum.Enum):
    GENERAL_QUESTION = "GENERAL_QUESTION"  # Standard RAG Q&A
    EXPLAIN_MORE = "EXPLAIN_MORE"          # Deeper explanation of last topic
    GIVE_EXAMPLES = "GIVE_EXAMPLES"        # User wants concrete examples
    QUIZ_ME = "QUIZ_ME"                    # User wants to be tested
    SHOW_VISUAL = "SHOW_VISUAL"            # User wants graphical representation
    SUMMARIZE = "SUMMARIZE"                # Summarize a topic
    COMPARE = "COMPARE"                    # Compare two things
    FOLLOW_UP = "FOLLOW_UP"               # Generic continuation of prior turn


class ChatMode(str, enum.Enum):
    STUDY = "study"          # RAG over course content (axis_content_chunks)
    SUPPORT = "support"      # RAG over KB docs (axis_kb_chunks) — admin-uploaded
    LEARNING = "learning"    # Future: personalised learning assistant


class ChatSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    A conversation session between a user and the AI chatbot.

    Scoped to:
    - tenant (required)
    - moodle_user_id (required — always know who is chatting)
    - moodle_course_id (optional — course-scoped chat uses course KB)
    - moodle_cmid (optional — content-scoped chat uses specific content item)

    The same session ID is used as chat_session_id in audit_logs,
    so you can trace exactly which AI calls a conversation triggered.

    session_summary: rolling LLM-generated summary of messages beyond the
    context window (lazy-generated when message_count > SUMMARY_THRESHOLD).

    language: the user's preferred response language (ISO 639-1).
    Any frontend (Moodle, Next.js, mobile) calls the same /chat endpoint.
    """

    __tablename__ = "chat_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── User & Moodle context ─────────────────────────────────────────────────
    moodle_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moodle_course_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moodle_cmid: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # ── Axis frontend user (NULL for Moodle-plugin sessions) ─────────────────
    axis_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="Set for axis frontend sessions; NULL for Moodle-plugin sessions",
    )

    # ── Content item scope (NULL = whole course) ──────────────────────────────
    content_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Scopes RAG to a specific content item; NULL = all course content",
    )

    # ── Chat mode — controls which Qdrant collection RAG searches ────────────
    chat_mode: Mapped[str] = mapped_column(
        String(20), default=ChatMode.STUDY.value, nullable=False, index=True,
        comment="study|support|learning — routes RAG to correct vector collection"
    )

    # ── Chat config ───────────────────────────────────────────────────────────
    language: Mapped[str] = mapped_column(
        String(10), default="en", nullable=False,
        comment="User's preferred response language (ISO 639-1)"
    )
    title: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Auto-generated or user-set session title"
    )

    # Which content items are in scope for RAG
    # NULL = all content for the course; specific list = only those items
    scoped_content_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Session-level config (model override, system prompt override, etc.)
    session_config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Token usage totals for this session (quick display; audit_logs is ground truth)
    total_tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_cost_usd: Mapped[float | None] = mapped_column(
        Numeric(12, 8), nullable=True,
        comment="Running cost total for this session (display convenience)"
    )

    # ── Intelligence fields (Phase 6) ─────────────────────────────────────────
    session_summary: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="LLM-generated rolling summary of messages beyond the context window"
    )
    current_topic_tags: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="['OSI model', 'network layers'] — updated each turn for context-aware RAG"
    )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    ended_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def __repr__(self) -> str:
        return (
            f"<ChatSession user={self.moodle_user_id} "
            f"course={self.moodle_course_id} lang={self.language} "
            f"msgs={self.message_count}>"
        )


class ChatMessage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Individual message in a chat session.

    Every assistant message stores:
    - retrieved_chunks: Qdrant results used for this response (citations + context threading)
    - suggestions: follow-up chips/buttons returned to the UI
    - visual_data: Chart.js-compatible data or Mermaid string (when render_hint=visual_*)
    - intent: what the user was trying to do
    - response_type: quality classification of the answer
    - confidence_score: 0.0-1.0 aggregate of RAG chunk scores
    """

    __tablename__ = "chat_messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[ChatMessageRole] = mapped_column(String(15), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # ── RAG context ───────────────────────────────────────────────────────────
    retrieved_chunks: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="[{content_item_id, chunk_index, text, score, title}] — citations"
    )
    rag_chunks_retrieved: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="How many Qdrant results were returned"
    )
    rag_chunks_used: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="How many chunks were included in the final prompt"
    )

    # ── Intelligence ──────────────────────────────────────────────────────────
    intent: Mapped[str | None] = mapped_column(
        String(30), nullable=True, index=True,
        comment="ChatIntent enum value for this message"
    )
    response_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True,
        comment="ChatResponseType enum value"
    )
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Aggregate RAG + answer confidence (0.0–1.0)"
    )

    # ── Rendering ─────────────────────────────────────────────────────────────
    render_hint: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="text|markdown|visual_chart|visual_mermaid"
    )
    visual_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Chart.js data object or {'mermaid': '...'} diagram string"
    )
    suggestions: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="[{id, type, label, action, payload}] — follow-up chips/buttons"
    )

    # ── Lineage ───────────────────────────────────────────────────────────────
    suggestion_clicked_id: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="suggestion.id from the previous response that triggered this message"
    )

    # ── Token usage for this message pair ────────────────────────────────────
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Model used (can vary per message if model routing is dynamic)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Relationships
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")

    def __repr__(self) -> str:
        return (
            f"<ChatMessage role={self.role} intent={self.intent} "
            f"type={self.response_type} tokens={self.completion_tokens}>"
        )
