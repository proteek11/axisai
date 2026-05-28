"""
QuizAttempt and FlashcardReview — learner engagement tracking models.

Each attempt/review is an immutable event written when:
  - A learner answers a quiz question (correct or not)
  - A learner marks a flashcard as 'known' or 'unknown'

Used by the learner detail report endpoint to show depth of engagement
beyond chat sessions: scores, accuracy, study patterns.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .base import Base


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    axis_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_index: Mapped[int] = mapped_column(Integer, nullable=False)
    correct_index: Mapped[int] = mapped_column(Integer, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    bloom_level: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    attempted_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class FlashcardReview(Base):
    __tablename__ = "flashcard_reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    space_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("learning_spaces.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    content_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    axis_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("axis_users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    card_index: Mapped[int] = mapped_column(Integer, nullable=False)
    front_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    known: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewed_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
