"""
033 — SCORM Integration.

New tables:
  scorm_packages  — metadata parsed from imsmanifest.xml (one per content_item)
  scorm_sessions  — per-learner per-attempt runtime state (cmi.* data)

Altered table:
  space_items — 3 new SCORM-specific columns:
    scorm_completion_trigger  (completion_only | pass_required)
    scorm_max_attempts        (NULL = unlimited)
    scorm_grade_aggregation   (highest | average | latest)

No changes to content_items — content_type='scorm' already exists in the enum.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── scorm_packages ─────────────────────────────────────────────────────────
    op.create_table(
        "scorm_packages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("scorm_version", sa.String(10), nullable=False),  # "1.2"|"2004_3"|"2004_4"
        sa.Column("entry_point", sa.String(500), nullable=False),   # relative path in package
        sa.Column("package_title", sa.String(255), nullable=True),
        sa.Column("sco_list", JSONB, nullable=True),                # SCO items from manifest
        sa.Column("manifest_data", JSONB, nullable=True),           # full parsed manifest
        sa.Column("file_count", sa.Integer, nullable=True),
        sa.Column("package_size_bytes", sa.BigInteger, nullable=True),
        sa.Column("passing_score", sa.Float, nullable=True),        # from manifest if present
        sa.Column("max_time_allowed", sa.String(50), nullable=True),# ISO 8601 duration
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_scorm_packages_content_item_id",
                    "scorm_packages", ["content_item_id"])

    # ── scorm_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        "scorm_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("content_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("space_id", UUID(as_uuid=True),
                  sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False, server_default="1"),
        # High-level status fields (mirrored from cmi_data on every commit)
        sa.Column("completion_status", sa.String(32),
                  nullable=False, server_default="not_attempted"),
        sa.Column("success_status", sa.String(32),
                  nullable=False, server_default="unknown"),
        sa.Column("score_raw", sa.Float, nullable=True),
        sa.Column("score_min", sa.Float, nullable=True),
        sa.Column("score_max", sa.Float, nullable=True),
        sa.Column("score_scaled", sa.Float, nullable=True),
        sa.Column("total_time_seconds", sa.Integer,
                  nullable=False, server_default="0"),
        # Resume data
        sa.Column("lesson_location", sa.String(255), nullable=True),
        sa.Column("suspend_data", sa.Text, nullable=True),
        sa.Column("cmi_data", JSONB, nullable=True),
        # Timestamps
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("content_item_id", "user_id", "space_id", "attempt_number",
                            name="uq_scorm_session_attempt"),
    )
    op.create_index("ix_scorm_sessions_content_item_id",
                    "scorm_sessions", ["content_item_id"])
    op.create_index("ix_scorm_sessions_user_id",
                    "scorm_sessions", ["user_id"])
    op.create_index("ix_scorm_sessions_space_id",
                    "scorm_sessions", ["space_id"])

    # ── space_items: 3 new SCORM columns ──────────────────────────────────────
    op.add_column("space_items", sa.Column(
        "scorm_completion_trigger", sa.String(32),
        nullable=False, server_default="completion_only",
        comment="completion_only | pass_required",
    ))
    op.add_column("space_items", sa.Column(
        "scorm_max_attempts", sa.Integer,
        nullable=True,
        comment="NULL = unlimited",
    ))
    op.add_column("space_items", sa.Column(
        "scorm_grade_aggregation", sa.String(16),
        nullable=False, server_default="highest",
        comment="highest | average | latest",
    ))


def downgrade() -> None:
    op.drop_column("space_items", "scorm_grade_aggregation")
    op.drop_column("space_items", "scorm_max_attempts")
    op.drop_column("space_items", "scorm_completion_trigger")
    op.drop_index("ix_scorm_sessions_space_id", table_name="scorm_sessions")
    op.drop_index("ix_scorm_sessions_user_id", table_name="scorm_sessions")
    op.drop_index("ix_scorm_sessions_content_item_id", table_name="scorm_sessions")
    op.drop_table("scorm_sessions")
    op.drop_index("ix_scorm_packages_content_item_id", table_name="scorm_packages")
    op.drop_table("scorm_packages")
