"""Add learner notes and bookmarks tables

Revision ID: 017
Revises: 016
"""
from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── learner_notes ──────────────────────────────────────────────────────
    op.create_table(
        "learner_notes",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("user_id",         sa.Integer,    nullable=False, index=True),
        sa.Column("content_item_id", sa.String(36), nullable=True,  index=True),
        sa.Column("space_id",        sa.String(36), nullable=True),
        sa.Column("body",            sa.Text,        nullable=False),
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at",      sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
    )

    # ── learner_bookmarks ──────────────────────────────────────────────────
    op.create_table(
        "learner_bookmarks",
        sa.Column("id",              sa.String(36), primary_key=True),
        sa.Column("user_id",         sa.Integer,    nullable=False, index=True),
        sa.Column("content_item_id", sa.String(36), nullable=True,  index=True),
        sa.Column("space_id",        sa.String(36), nullable=True),
        sa.Column("output_type",     sa.String(50), nullable=True),   # e.g. 'summary', 'quiz'
        sa.Column("label",           sa.String(255), nullable=True),  # custom label
        sa.Column("created_at",      sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("learner_bookmarks")
    op.drop_table("learner_notes")
