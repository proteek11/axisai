"""028 — LXP Catalogue: is_public, experience_mode, creator_id on content_items;
user_content_progress table; completion_criterion on learning_spaces.

Revision ID: 028
Revises: 027
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── content_items — new LXP columns ─────────────────────────────────
    op.add_column(
        "content_items",
        sa.Column(
            "is_public",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="True = visible to all creators in the tenant. False = own content only.",
        ),
    )
    op.add_column(
        "content_items",
        sa.Column(
            "experience_mode",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'standard'"),
            comment="'standard' = AI output tabs. 'interactive' = embedded interactions.",
        ),
    )
    op.add_column(
        "content_items",
        sa.Column(
            "creator_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="SET NULL"),
            nullable=True,
            comment="AxisUser who created this content (for library-origin items).",
        ),
    )

    # ── learning_spaces — completion criterion ───────────────────────────
    op.add_column(
        "learning_spaces",
        sa.Column(
            "completion_criterion",
            JSONB(),
            nullable=True,
            server_default=sa.text("NULL"),
            comment=(
                "JSON: {"
                '"mode": "all_required"|"pass_assessments"|"percentage",'
                '"pct_threshold": 80'
                "}"
            ),
        ),
    )

    # ── user_content_progress — content-level completion tracking ────────
    op.create_table(
        "user_content_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "progress_pct",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "completion_data",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="Extra data: time_spent_seconds, last_position, etc.",
        ),
        sa.UniqueConstraint("user_id", "content_item_id", name="uq_user_content_progress"),
    )
    op.create_index(
        "ix_user_content_progress_user_id",
        "user_content_progress",
        ["user_id"],
    )
    op.create_index(
        "ix_user_content_progress_content_item_id",
        "user_content_progress",
        ["content_item_id"],
    )
    # creator_id index on content_items (ORM has index=True but add_column won't auto-create it)
    op.create_index("ix_content_items_creator_id", "content_items", ["creator_id"])


def downgrade() -> None:
    op.drop_index("ix_content_items_creator_id", "content_items")
    op.drop_table("user_content_progress")
    op.drop_column("learning_spaces", "completion_criterion")
    op.drop_column("content_items", "creator_id")
    op.drop_column("content_items", "experience_mode")
    op.drop_column("content_items", "is_public")
