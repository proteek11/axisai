"""Phase 14 — Interactive content: interactions column + interaction_responses table.

Revision ID: 023
Revises: 022
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add interactions JSONB column to content_items
    #    Stores the list of MCQ / T-F / Callout interaction objects at specific timestamps.
    op.add_column(
        "content_items",
        sa.Column(
            "interactions",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
    )

    # 2. Create interaction_responses table
    op.create_table(
        "interaction_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "content_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Zero-based index into the content_items.interactions array
        sa.Column("interaction_index", sa.Integer(), nullable=False),
        # The answer the learner submitted (option letter A/B/C/D, "true"/"false", etc.)
        sa.Column("selected_answer", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        # Seconds from when the overlay appeared to when they submitted
        sa.Column("time_taken_seconds", sa.Integer(), nullable=True),
        sa.Column(
            "answered_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for fast lookups
    op.create_index(
        "ix_interaction_responses_content_item_id",
        "interaction_responses",
        ["content_item_id"],
    )
    op.create_index(
        "ix_interaction_responses_user_id",
        "interaction_responses",
        ["user_id"],
    )
    op.create_index(
        "ix_interaction_responses_content_user",
        "interaction_responses",
        ["content_item_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_interaction_responses_content_user", "interaction_responses")
    op.drop_index("ix_interaction_responses_user_id", "interaction_responses")
    op.drop_index("ix_interaction_responses_content_item_id", "interaction_responses")
    op.drop_table("interaction_responses")
    op.drop_column("content_items", "interactions")
