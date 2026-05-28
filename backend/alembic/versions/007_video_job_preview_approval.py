"""007_video_job_preview_approval

Adds the preview_url column to video_jobs (Step 10 — preview/approval flow).

New status values (DRAFT, PREVIEW_PENDING, PREVIEW_READY, APPROVED) are stored
as strings in the existing String(20) status column — no column change needed.
The longest new value "preview_pending" is 15 chars, well within the 20-char limit.

Revision ID: 007
Revises: 006
"""
from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add preview_url to video_jobs
    op.add_column(
        "video_jobs",
        sa.Column("preview_url", sa.Text, nullable=True),
    )

    # Widen status column from 20 → 25 to comfortably fit "preview_pending" (15)
    # and leave headroom for future status strings.
    # NOTE: VARCHAR widening is non-blocking in PostgreSQL (no table rewrite).
    op.alter_column(
        "video_jobs",
        "status",
        type_=sa.String(25),
        existing_type=sa.String(20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.drop_column("video_jobs", "preview_url")
    op.alter_column(
        "video_jobs",
        "status",
        type_=sa.String(20),
        existing_type=sa.String(25),
        existing_nullable=False,
    )
