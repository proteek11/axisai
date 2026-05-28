"""Assessment models — Phase 15.

Assessment: a creator-configured test that draws questions from the
quiz_questions pool and appears as a ContentItem in a LearningSpace.

AssessmentAttempt: one learner attempt at an Assessment.
"""
from __future__ import annotations

import uuid
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    space_id = Column(
        UUID(as_uuid=True),
        ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    creator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Display
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Selected question IDs (ordered list of UUIDs as strings)
    question_ids = Column(JSONB, nullable=False, default=list)

    # Config
    time_limit_minutes = Column(Integer, nullable=True)   # NULL = no time limit
    max_attempts = Column(Integer, nullable=False, default=1)
    pass_pct = Column(Float, nullable=False, default=70.0)
    shuffle_questions = Column(Boolean, nullable=False, default=True)
    shuffle_options = Column(Boolean, nullable=False, default=True)
    show_answers_after = Column(Boolean, nullable=False, default=True)
    is_published = Column(Boolean, nullable=False, default=False)

    # Content item link — assessment is surfaced as a SpaceItem of type 'assessment'
    content_item_id = Column(
        UUID(as_uuid=True),
        ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    attempts = relationship(
        "AssessmentAttempt", back_populates="assessment", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Assessment id={self.id} title={self.title!r} published={self.is_published}>"


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assessment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False, default=1)

    # answers: [{ question_id, selected_option_index, is_correct }]
    answers = Column(JSONB, nullable=False, default=list)

    score_pct = Column(Float, nullable=True)     # NULL until submitted
    passed = Column(Boolean, nullable=True)
    total_questions = Column(Integer, nullable=True)
    correct_count = Column(Integer, nullable=True)

    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)

    # Relationships
    assessment = relationship("Assessment", back_populates="attempts")

    def __repr__(self) -> str:
        return (
            f"<AssessmentAttempt id={self.id} "
            f"attempt={self.attempt_number} score={self.score_pct}>"
        )
