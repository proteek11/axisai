"""011_axis_chat_columns

Add axis-native chat support to chat_sessions:

  • axis_user_id    — FK to axis_users.id (NULL for Moodle-plugin sessions)
  • content_item_id — FK to content_items.id (NULL when session is course-wide)
  • Make moodle_user_id nullable so axis sessions don't need a fake int

Moodle plugin sessions:  axis_user_id=NULL,  moodle_user_id=<int>
Axis frontend sessions:  axis_user_id=<uuid>, moodle_user_id=NULL

Revision ID: 011
Revises: 010
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add axis_user_id column (nullable FK → axis_users)
    op.add_column(
        "chat_sessions",
        sa.Column(
            "axis_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=True,
            comment="Set for axis frontend sessions; NULL for Moodle-plugin sessions",
        ),
    )
    # Explicit index — index=True inside add_column is silently ignored by Alembic
    op.create_index(
        "ix_chat_sessions_axis_user_id",
        "chat_sessions",
        ["axis_user_id"],
    )

    # 2. Add content_item_id column (nullable FK → content_items)
    op.add_column(
        "chat_sessions",
        sa.Column(
            "content_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="SET NULL"),
            nullable=True,
            comment="Scopes RAG to a single content item; NULL = whole course",
        ),
    )
    # Explicit index
    op.create_index(
        "ix_chat_sessions_content_item_id",
        "chat_sessions",
        ["content_item_id"],
    )

    # 3. Make moodle_user_id nullable (axis sessions have no Moodle user)
    op.alter_column(
        "chat_sessions",
        "moodle_user_id",
        existing_type=sa.Integer,
        nullable=True,
    )

    # 4. Composite index for fast axis session lookup
    op.create_index(
        "ix_chat_sessions_axis_user_content",
        "chat_sessions",
        ["axis_user_id", "content_item_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_sessions_axis_user_content", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_content_item_id", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_axis_user_id", table_name="chat_sessions")
    op.alter_column(
        "chat_sessions",
        "moodle_user_id",
        existing_type=sa.Integer,
        nullable=False,
    )
    op.drop_column("chat_sessions", "content_item_id")
    op.drop_column("chat_sessions", "axis_user_id")
