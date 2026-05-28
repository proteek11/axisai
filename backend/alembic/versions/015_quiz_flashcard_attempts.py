"""quiz_attempts and flashcard_reviews tables

Revision ID: 015
Revises: 014
Create Date: 2026-05-10

Two new tables for tracking learner quiz attempts and flashcard review sessions.
Used by the learner detail report to show per-content engagement depth.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── quiz_attempts ─────────────────────────────────────────────────────────
    op.create_table(
        "quiz_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True), sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content_item_id", UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("axis_user_id", UUID(as_uuid=True), sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("question_index", sa.Integer, nullable=False),
        sa.Column("question_text", sa.Text, nullable=True),
        sa.Column("selected_index", sa.Integer, nullable=False),
        sa.Column("correct_index", sa.Integer, nullable=False),
        sa.Column("is_correct", sa.Boolean, nullable=False),
        sa.Column("bloom_level", sa.String(30), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
    )

    # ── flashcard_reviews ─────────────────────────────────────────────────────
    op.create_table(
        "flashcard_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True), sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("content_item_id", UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("axis_user_id", UUID(as_uuid=True), sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("card_index", sa.Integer, nullable=False),
        sa.Column("front_text", sa.Text, nullable=True),
        sa.Column("known", sa.Boolean, nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
    )


def downgrade() -> None:
    op.drop_table("flashcard_reviews")
    op.drop_table("quiz_attempts")
