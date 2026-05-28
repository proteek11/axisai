"""Fix learner_notes and learner_bookmarks user_id column type: Integer -> Text (UUID stored as string)

Revision ID: 019
Revises: 018
"""
from alembic import op
import sqlalchemy as sa

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change user_id from Integer to Text so AxisUser UUID ids fit
    op.alter_column(
        "learner_notes", "user_id",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        postgresql_using="user_id::text",
        nullable=False,
    )
    op.alter_column(
        "learner_bookmarks", "user_id",
        existing_type=sa.Integer(),
        type_=sa.Text(),
        postgresql_using="user_id::text",
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "learner_notes", "user_id",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        postgresql_using="user_id::integer",
        nullable=False,
    )
    op.alter_column(
        "learner_bookmarks", "user_id",
        existing_type=sa.Text(),
        type_=sa.Integer(),
        postgresql_using="user_id::integer",
        nullable=False,
    )
