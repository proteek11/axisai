"""
AI Output models:
- AIOutput: Generic container for summary, flashcards, glossary, mindmap, objectives, blooms
- QuizQuestion: Structured table for questions (queryable by bloom, difficulty, etc.)
"""
import uuid
import enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OutputType(str, enum.Enum):
    SUMMARY = "summary"
    FLASHCARDS = "flashcards"
    GLOSSARY = "glossary"
    MINDMAP = "mindmap"
    OBJECTIVES = "objectives"
    BLOOMS = "blooms"
    QUIZ = "quiz"
    TRANSLATION = "translation"
    CONTENT_INTELLIGENCE = "content_intelligence"
    CHAPTERS = "chapters"
    FAQ = "faq"
    INFOGRAPHIC = "infographic"
    DISCUSSION_PROMPTS = "discussion_prompts"


class OutputStatus(str, enum.Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"   # Prompt version A → when v B is generated, A becomes superseded


class QuestionType(str, enum.Enum):
    MULTICHOICE = "multichoice"
    TRUEFALSE = "truefalse"
    SHORTANSWER = "shortanswer"
    ESSAY = "essay"
    MATCHING = "matching"


class AIOutput(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Stores AI-generated outputs for a content item.

    Prompt versioning (Option A): when a new version is generated for the same
    content_item + output_type + language, the old row is marked SUPERSEDED.
    Both rows are kept for quality comparison and regression analysis.

    The payload JSONB structure varies by output_type:
    - summary:     { "text": "...", "bullet_points": [...] }
    - flashcards:  { "cards": [{"front": "...", "back": "..."}] }
    - glossary:    { "terms": [{"term": "...", "definition": "..."}] }
    - mindmap:     { "root": {"title": "...", "children": [...]} }
    - objectives:  { "objectives": ["...", "..."] }
    - blooms:      { "levels": {"remember": [...], "understand": [...], ...} }
    - quiz:        { "questions": [...] }  (also broken out into quiz_questions table)
    - translation: { "language": "fr", "text": "...", "source_type": "transcript" }
    """

    __tablename__ = "ai_outputs"

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("processing_jobs.id", ondelete="SET NULL"),
        nullable=True,
    )

    output_type: Mapped[OutputType] = mapped_column(String(30), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    status: Mapped[OutputStatus] = mapped_column(
        String(20), default=OutputStatus.ACTIVE, nullable=False, index=True
    )

    # The actual output
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Generation provenance
    provider: Mapped[str | None] = mapped_column(String(30), nullable=True)
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Quality tracking
    quality_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Teacher edit fields ───────────────────────────────────────────────────
    # When a teacher edits the output (e.g. summary text), we store their
    # version here rather than overwriting payload. This preserves the original
    # AI output for quality analysis while serving the teacher's version to learners.
    edited_content: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Teacher-edited override of payload. Served instead of payload when set."
    )
    is_teacher_edited: Mapped[bool] = mapped_column(
        Boolean, default=False,
        comment="True once teacher has saved any edit"
    )
    last_edited_by: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="moodle_user_id of the last teacher to edit this output"
    )
    last_edited_at: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Timestamp of most recent teacher edit"
    )

    # Relationships
    content_item: Mapped["ContentItem"] = relationship(  # noqa: F821
        "ContentItem", back_populates="ai_outputs"
    )

    def __repr__(self) -> str:
        return (
            f"<AIOutput {self.output_type} "
            f"lang={self.language} v={self.prompt_version} "
            f"status={self.status}>"
        )


class QuizQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """
    Structured question storage — queryable by bloom, difficulty, topic, etc.
    Every question also lives in axis_question_intelligence Qdrant collection
    for semantic similarity search and deduplication.

    moodle_question_id / moodle_draft_id are set when the question is pushed
    back to Moodle. They are NULL until then — our system generates first,
    Moodle receives later.
    """

    __tablename__ = "quiz_questions"

    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_output_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_outputs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Moodle references (set after push to Moodle)
    moodle_question_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    moodle_draft_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Question content
    question_type: Mapped[QuestionType] = mapped_column(
        String(20), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list | None] = mapped_column(
        JSONB, nullable=True,
        comment="[{text, is_correct, feedback}] for multichoice/matching"
    )
    correct_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Classification
    topic_primary: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    topic_secondary: Mapped[str | None] = mapped_column(String(255), nullable=True)
    blooms_level: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    difficulty_label: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cognitive_skill: Mapped[str | None] = mapped_column(String(100), nullable=True)
    learning_objective: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source traceability — which chunks generated this question
    source_chunks: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # Generation provenance
    model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Quality tracking
    quality_auto_rated: Mapped[bool] = mapped_column(Boolean, default=False)
    quality_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Pool management fields ────────────────────────────────────────────────
    # generated | manual  (manual = teacher added directly via management screen)
    source: Mapped[str] = mapped_column(String(20), default="generated", nullable=False)
    # 1 = initial generation, 2 = first regenerate pass, etc.
    generation_batch: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # moodle_user_id — set only when source='manual'
    manually_added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # ID in axis_question_intelligence Qdrant collection — used for semantic dedup on regenerate
    qdrant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Relationships
    content_item: Mapped["ContentItem"] = relationship(  # noqa: F821
        "ContentItem", back_populates="quiz_questions"
    )

    def __repr__(self) -> str:
        return (
            f"<QuizQuestion {self.question_type} "
            f"blooms={self.blooms_level} diff={self.difficulty_label}>"
        )
