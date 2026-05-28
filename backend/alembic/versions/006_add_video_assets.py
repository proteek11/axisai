"""006_add_video_assets

Creates the video_assets table for the Asset Library (Step 9).

Assets are reusable tenant-scoped media files (character PNGs, logos,
music, background images, custom fonts) that renderers load by type.

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_assets",

        # ── Primary key ───────────────────────────────────────────────────────
        sa.Column("id", UUID(as_uuid=True), primary_key=True),

        # ── Tenant isolation ─────────────────────────────────────────────────
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # ── Asset identity ───────────────────────────────────────────────────
        sa.Column("name",            sa.String(255), nullable=False),
        sa.Column("asset_type",      sa.String(50),  nullable=False),
        sa.Column("url",             sa.Text,        nullable=False),
        sa.Column("mime_type",       sa.String(100), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger,  nullable=True),
        sa.Column("metadata",        JSONB,          nullable=False, server_default="{}"),
        sa.Column("is_active",       sa.Boolean,     nullable=False, server_default="true"),

        # ── Audit timestamps ─────────────────────────────────────────────────
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=True,
        ),
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    op.create_index("ix_video_assets_tenant_id",   "video_assets", ["tenant_id"])
    op.create_index("ix_video_assets_asset_type",  "video_assets", ["asset_type"])
    op.create_index("ix_video_assets_is_active",   "video_assets", ["is_active"])
    # Composite index for the most common renderer query:
    # SELECT * FROM video_assets WHERE tenant_id=? AND asset_type=? AND is_active=TRUE
    op.create_index(
        "ix_video_assets_tenant_type_active",
        "video_assets",
        ["tenant_id", "asset_type", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_assets_tenant_type_active", table_name="video_assets")
    op.drop_index("ix_video_assets_is_active",          table_name="video_assets")
    op.drop_index("ix_video_assets_asset_type",         table_name="video_assets")
    op.drop_index("ix_video_assets_tenant_id",          table_name="video_assets")
    op.drop_table("video_assets")
