"""005_add_video_jobs

Creates the video_jobs table for the video creation pipeline
(local_edzaxisvideo Moodle plugin → axis-ai FastAPI).

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_jobs",
        # ── Primary key ───────────────────────────────────────────────────────
        sa.Column("id", UUID(as_uuid=True), primary_key=True),

        # ── Tenant isolation ─────────────────────────────────────────────────
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # ── Job description ──────────────────────────────────────────────────
        # moodle_job_id = integer PK from local_edzaxisvideo_jobs
        sa.Column("moodle_job_id",   sa.Integer(),     nullable=False),
        sa.Column("video_type",      sa.String(50),    nullable=False),
        sa.Column("title",           sa.Text(),        nullable=False),
        sa.Column("script",          sa.Text(),        nullable=True),
        sa.Column("language",        sa.String(10),    nullable=False, server_default="en"),

        # Full settings payload from Moodle (includes _resolved_assets URLs)
        sa.Column("settings",        JSONB(),          nullable=False, server_default="{}"),
        # Providers actually used — logged for audit / billing
        sa.Column("provider_used",   JSONB(),          nullable=True),

        # ── Status ───────────────────────────────────────────────────────────
        # queued | processing | done | failed
        sa.Column("status",       sa.String(20),  nullable=False, server_default="queued"),
        sa.Column("progress",     sa.Integer(),   nullable=False, server_default="0"),
        sa.Column("progress_msg", sa.String(255), nullable=True),

        # ── Output ───────────────────────────────────────────────────────────
        sa.Column("output_url",       sa.Text(),       nullable=True),
        sa.Column("thumbnail_url",    sa.Text(),       nullable=True),
        sa.Column("duration_sec",     sa.Integer(),    nullable=True),
        sa.Column("file_size_bytes",  sa.BigInteger(), nullable=True),

        # ── Error ────────────────────────────────────────────────────────────
        sa.Column("error_message",  sa.Text(), nullable=True),
        sa.Column("callback_url",   sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),

        # ── Timing ───────────────────────────────────────────────────────────
        sa.Column("started_at",   sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at",   sa.DateTime(timezone=True),
                  onupdate=sa.func.now(), nullable=True),
    )

    # ── Unique constraint — one active record per (tenant, moodle job) ────────
    op.create_unique_constraint(
        "uq_video_jobs_tenant_moodle",
        "video_jobs",
        ["tenant_id", "moodle_job_id"],
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_video_jobs_tenant_id",    "video_jobs", ["tenant_id"])
    op.create_index("ix_video_jobs_moodle_job_id","video_jobs", ["moodle_job_id"])
    op.create_index("ix_video_jobs_status",       "video_jobs", ["status"])
    op.create_index("ix_video_jobs_video_type",   "video_jobs", ["video_type"])
    op.create_index("ix_video_jobs_celery_task_id","video_jobs", ["celery_task_id"])


def downgrade() -> None:
    op.drop_index("ix_video_jobs_celery_task_id", table_name="video_jobs")
    op.drop_index("ix_video_jobs_video_type",     table_name="video_jobs")
    op.drop_index("ix_video_jobs_status",         table_name="video_jobs")
    op.drop_index("ix_video_jobs_moodle_job_id",  table_name="video_jobs")
    op.drop_index("ix_video_jobs_tenant_id",      table_name="video_jobs")
    op.drop_constraint("uq_video_jobs_tenant_moodle", "video_jobs", type_="unique")
    op.drop_table("video_jobs")
