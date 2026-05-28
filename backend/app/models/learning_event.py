"""
UserLearningEvent — immutable event log for every user learning interaction.

Written automatically on every chat turn. Never updated. The raw material
for Phase 4 personalized learning plans.

Event types:
  SESSION_START      — new chat session created
  SESSION_END        — session explicitly ended
  ASKED              — user asked a general question
  ASKED_EXPLAIN      — user asked for explanation (intent=EXPLAIN_MORE)
  ASKED_VISUAL       — user requested visual/diagram (intent=SHOW_VISUAL)
  ASKED_QUIZ         — user requested quiz questions (intent=QUIZ_ME)
  SUGGESTION_CLICKED — user clicked a suggestion chip/button
  NO_CONTEXT         — question had no matching course content (knowledge gap signal)
  LOW_CONFIDENCE     — question answered with low confidence (weak coverage signal)

Phase 4 will aggregate these events to:
  - Identify weak topics (high ASKED_EXPLAIN + LOW_CONFIDENCE on same topic)
  - Identify preferred learning styles (frequent ASKED_VISUAL → visual learner)
  - Surface content gaps (NO_CONTEXT clusters → teacher should add material)
  - Generate personalized study plans
"""
import uuid
import enum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class LearningEventType(str, enum.Enum):
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    ASKED = "ASKED"
    ASKED_EXPLAIN = "ASKED_EXPLAIN"
    ASKED_VISUAL = "ASKED_VISUAL"
    ASKED_QUIZ = "ASKED_QUIZ"
    SUGGESTION_CLICKED = "SUGGESTION_CLICKED"
    NO_CONTEXT = "NO_CONTEXT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class UserLearningEvent(Base):
    """
    Immutable learning event record. Written once, never updated.
    """

    __tablename__ = "user_learning_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── User context ──────────────────────────────────────────────────────────
    moodle_user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    moodle_course_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    moodle_cmid: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── What happened ─────────────────────────────────────────────────────────
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True,
        comment="LearningEventType enum value"
    )

    # ── What it was about ─────────────────────────────────────────────────────
    topic_tags: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="['OSI model', 'network layers'] extracted by intent classifier"
    )
    content_item_ids: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="UUIDs of content items cited in the RAG response"
    )
    intent: Mapped[str | None] = mapped_column(String(30), nullable=True)
    response_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        comment="Proxy for how well the course covers this topic (0.0–1.0)"
    )

    # ── Linkage ───────────────────────────────────────────────────────────────
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    chat_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    # ── Flexible metadata ─────────────────────────────────────────────────────
    event_metadata: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Arbitrary extra context: suggestion_id clicked, quiz scores, etc."
    )

    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default="now()",
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<UserLearningEvent user={self.moodle_user_id} "
            f"type={self.event_type} course={self.moodle_course_id}>"
        )
