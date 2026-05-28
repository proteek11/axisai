"""
032 — Live Class (Zoom) integration.

New tables:
  live_class_sessions  — one row per scheduled Zoom meeting, linked to a space
  live_class_attendance — one row per participant per session

No changes to existing tables. Zoom credentials are stored in tenant.config JSONB
(no migration needed — JSONB is schema-less).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── live_class_sessions ───────────────────────────────────────────────────
    op.create_table(
        "live_class_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True), sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="zoom"),  # 'zoom' | 'google_meet'
        # External IDs from the provider
        sa.Column("external_meeting_id", sa.String(255), nullable=True),   # Zoom meeting ID (numeric as string)
        sa.Column("external_meeting_uuid", sa.String(512), nullable=True), # Zoom meeting UUID (used for recording lookup)
        # Content
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer, nullable=False, server_default="60"),
        # URLs
        sa.Column("join_url", sa.Text, nullable=True),   # Participant join link
        sa.Column("host_url", sa.Text, nullable=True),   # Creator start link (Zoom only)
        sa.Column("password", sa.String(255), nullable=True),  # Meeting passcode
        # State machine: scheduled → live → ended → imported | cancelled
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        # Config toggles (per-class overrides)
        sa.Column("auto_record", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("import_recording", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("import_attendance", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("generate_ai_outputs", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notify_learners", sa.Boolean, nullable=False, server_default="true"),
        # Post-class — set after import completes
        sa.Column("content_item_id", UUID(as_uuid=True), sa.ForeignKey("content_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recording_local_path", sa.Text, nullable=True),  # Downloaded MP4 path on server
        sa.Column("recording_duration_seconds", sa.Integer, nullable=True),
        sa.Column("actual_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("participant_count", sa.Integer, nullable=True),
        # Error tracking
        sa.Column("import_error", sa.Text, nullable=True),
        # Who created it
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),  # axis_user.id
        sa.Column("created_by_email", sa.String(512), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_live_class_sessions_space_id", "live_class_sessions", ["space_id"])
    op.create_index("ix_live_class_sessions_tenant_id", "live_class_sessions", ["tenant_id"])
    op.create_index("ix_live_class_sessions_status", "live_class_sessions", ["status"])
    op.create_index("ix_live_class_sessions_scheduled_at", "live_class_sessions", ["scheduled_at"])
    op.create_index("ix_live_class_sessions_ext_id", "live_class_sessions", ["external_meeting_id"])

    # ── live_class_attendance ─────────────────────────────────────────────────
    op.create_table(
        "live_class_attendance",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("live_class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("participant_id", sa.String(255), nullable=True),  # Zoom participant_id
        sa.Column("user_id", sa.String(255), nullable=True),         # Zoom user_id (if registered)
        sa.Column("user_email", sa.String(512), nullable=True),
        sa.Column("user_name", sa.String(512), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("attentiveness_score", sa.Float, nullable=True),   # Zoom attention tracking (0–100)
        sa.Column("raw_data", JSONB, nullable=True),                  # Full Zoom participant object
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("ix_live_class_attendance_session_id", "live_class_attendance", ["session_id"])
    op.create_index("ix_live_class_attendance_user_email", "live_class_attendance", ["user_email"])


def downgrade() -> None:
    op.drop_table("live_class_attendance")
    op.drop_table("live_class_sessions")
