"""026_upload_limits

Add max_upload_size_mb to axis_platform_settings so the admin can control
the maximum file size for all uploads (PDF, TXT, IC video, KB files) from
the admin dashboard without touching the server .env or restarting services.

Default: 100 MB (matches the existing config.py default).
Nginx hard cap remains 500 MB and is never touched by this migration.

Revision ID: 026
Revises: 025
"""
from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop column if it exists from a failed previous run (idempotent)
    op.execute(
        "ALTER TABLE axis_platform_settings DROP COLUMN IF EXISTS max_upload_size_mb"
    )
    op.add_column(
        "axis_platform_settings",
        sa.Column(
            "max_upload_size_mb",
            sa.Integer,
            nullable=False,
            server_default="100",
            comment="Maximum file upload size in MB enforced across all upload endpoints",
        ),
    )


def downgrade() -> None:
    op.drop_column("axis_platform_settings", "max_upload_size_mb")
