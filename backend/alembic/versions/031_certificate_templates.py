"""031 — Certificate templates + space certificate configs

Revision ID: 031
Revises: 030
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Certificate templates (admin-managed) ───────────────────────────
    op.create_table(
        "certificate_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type_tag", sa.String(64), nullable=False,
                  server_default="completion"),    # completion/participation/achievement/custom
        sa.Column("layout_style", sa.String(64), nullable=False,
                  server_default="classic"),       # classic/modern/minimal/branded
        sa.Column("title_text", sa.String(512), nullable=False,
                  server_default="Certificate of Completion"),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("logo_path", sa.Text, nullable=True),
        sa.Column("signature_name", sa.String(255), nullable=True),
        sa.Column("signature_title", sa.String(255), nullable=True),
        sa.Column("signature_path", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ── 2. Space certificate configs (creator-placed per space) ────────────
    op.create_table(
        "space_certificate_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True),
                  sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("template_id", UUID(as_uuid=True),
                  sa.ForeignKey("certificate_templates.id", ondelete="SET NULL"),
                  nullable=True),
        # trigger_type: all_items | percentage | assessment | manual
        sa.Column("trigger_type", sa.String(64), nullable=False,
                  server_default="all_items"),
        # trigger_value: {"percentage": 80} or {"assessment_id": "uuid"} etc.
        sa.Column("trigger_value", JSONB, nullable=False, server_default="{}"),
        sa.Column("custom_title", sa.String(512), nullable=True),
        sa.Column("custom_message", sa.Text, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
    )

    # ── 3. Add config_id to space_certificates (nullable, backward compat) ─
    op.add_column(
        "space_certificates",
        sa.Column("config_id", UUID(as_uuid=True),
                  sa.ForeignKey("space_certificate_configs.id", ondelete="SET NULL"),
                  nullable=True),
    )
    op.create_index("ix_space_certificates_config_id",
                    "space_certificates", ["config_id"])


def downgrade() -> None:
    op.drop_index("ix_space_certificates_config_id", table_name="space_certificates")
    op.drop_column("space_certificates", "config_id")
    op.drop_table("space_certificate_configs")
    op.drop_table("certificate_templates")
