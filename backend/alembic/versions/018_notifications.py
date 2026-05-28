"""Add user_notifications table

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("id",         sa.String(36), primary_key=True),
        sa.Column("user_id",    sa.Integer,    nullable=False, index=True),
        sa.Column("title",      sa.String(255), nullable=False),
        sa.Column("body",       sa.Text,        nullable=True),
        sa.Column("link",       sa.String(512), nullable=True),
        sa.Column("notif_type", sa.String(50),  nullable=True),   # e.g. 'space_shared', 'job_done'
        sa.Column("is_read",    sa.Boolean,     nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.text("NOW()")),
    )


def downgrade() -> None:
    op.drop_table("user_notifications")
