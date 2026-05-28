"""Fix user_notifications.user_id type: INTEGER → VARCHAR(36) to match UUID users

Revision ID: 030
Revises: 029
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # user_id was incorrectly created as INTEGER in migration 018.
    # Users have UUID primary keys (stored as VARCHAR/TEXT), so this column
    # must match. We wipe existing rows (they're all broken anyway) and retype.
    op.execute("DELETE FROM user_notifications")
    op.execute(
        "ALTER TABLE user_notifications ALTER COLUMN user_id TYPE VARCHAR(36)"
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_notifications")
    op.execute(
        "ALTER TABLE user_notifications ALTER COLUMN user_id TYPE INTEGER USING 0"
    )
