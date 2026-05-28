"""025 — Assessments: assessments table + assessment_attempts table

Revision ID: 025
Revises: 024
Create Date: 2026-05-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop tables if they exist from a failed previous run (idempotent)
    op.execute("DROP TABLE IF EXISTS assessment_attempts CASCADE")
    op.execute("DROP TABLE IF EXISTS assessments CASCADE")

    # ── assessments ───────────────────────────────────────────────────────────
    op.create_table(
        "assessments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "space_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "creator_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Display
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        # Selected question IDs from quiz_questions (ordered list)
        sa.Column("question_ids", JSONB, nullable=False, server_default="[]"),
        # Config
        sa.Column("time_limit_minutes", sa.Integer, nullable=True),   # NULL = no limit
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("pass_pct", sa.Float, nullable=False, server_default="70"),
        sa.Column("shuffle_questions", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("shuffle_options", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("show_answers_after", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_published", sa.Boolean, nullable=False, server_default="false"),
        # Content item link (assessment appears as a SpaceItem)
        sa.Column(
            "content_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_assessments_space_id ON assessments (space_id)")

    # ── assessment_attempts ───────────────────────────────────────────────────
    op.create_table(
        "assessment_attempts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "assessment_id",
            UUID(as_uuid=True),
            sa.ForeignKey("assessments.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        # Answers: [{ question_id, selected_option_index, is_correct }]
        sa.Column("answers", JSONB, nullable=False, server_default="[]"),
        sa.Column("score_pct", sa.Float, nullable=True),   # NULL until submitted
        sa.Column("passed", sa.Boolean, nullable=True),
        sa.Column("total_questions", sa.Integer, nullable=True),
        sa.Column("correct_count", sa.Integer, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_taken_seconds", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_assessment_attempts_assessment_user",
        "assessment_attempts",
        ["assessment_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_table("assessment_attempts")
    op.drop_table("assessments")
