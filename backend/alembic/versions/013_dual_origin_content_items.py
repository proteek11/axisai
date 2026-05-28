"""013_dual_origin_content_items

Make ContentItem origin-agnostic so both the Moodle plugin and the
standalone Next.js frontend can create content items.

Changes:
  • Add  origin       VARCHAR(10) NOT NULL DEFAULT 'moodle'
  • Add  space_id     UUID NULL FK → learning_spaces (standalone "course")
  • Add  asset_id     UUID NULL       (standalone "cmid" — unique per upload)
  • Make moodle_course_id  nullable  (was NOT NULL)
  • Make moodle_cmid       nullable  (was NOT NULL)
  • Drop hard   UNIQUE(tenant_id, moodle_cmid)           constraint
  • Add partial UNIQUE(tenant_id, moodle_cmid) WHERE moodle_cmid IS NOT NULL
  • Add partial UNIQUE(tenant_id, asset_id)    WHERE asset_id IS NOT NULL
  • Add  VIDEO_UPLOAD to content_type allowed values (was missing)

Moodle path: origin='moodle', moodle_course_id set, moodle_cmid set,
             space_id=NULL, asset_id=NULL   — ZERO breaking changes.

Standalone path: origin='space', space_id set, asset_id set (UUID),
                 moodle_course_id=NULL, moodle_cmid=NULL.

Revision ID: 013
Revises: 012
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Add origin discriminator ───────────────────────────────────────────
    op.add_column(
        "content_items",
        sa.Column(
            "origin",
            sa.String(10),
            nullable=False,
            server_default="moodle",
            comment="'moodle' = Moodle plugin; 'space' = standalone frontend",
        ),
    )

    # ── 2. Add standalone identity columns ────────────────────────────────────
    op.add_column(
        "content_items",
        sa.Column(
            "space_id",
            UUID(as_uuid=True),
            sa.ForeignKey("learning_spaces.id", ondelete="SET NULL"),
            nullable=True,
            comment="LearningSpace for space-origin content (replaces moodle_course_id)",
        ),
    )
    op.add_column(
        "content_items",
        sa.Column(
            "asset_id",
            UUID(as_uuid=True),
            nullable=True,
            comment="Unique upload UUID for space-origin content (replaces moodle_cmid)",
        ),
    )

    # ── 3. Create indexes for new columns ─────────────────────────────────────
    op.create_index("ix_content_items_origin",   "content_items", ["origin"])
    op.create_index("ix_content_items_space_id",  "content_items", ["space_id"])
    op.create_index("ix_content_items_asset_id",  "content_items", ["asset_id"])

    # ── 4. Make moodle_course_id + moodle_cmid nullable ───────────────────────
    op.alter_column("content_items", "moodle_course_id", nullable=True)
    op.alter_column("content_items", "moodle_cmid",       nullable=True)

    # ── 5. Drop old hard unique constraint ────────────────────────────────────
    op.drop_constraint("uq_tenant_cmid", "content_items", type_="unique")

    # ── 6. Add partial unique indexes (PostgreSQL-specific) ───────────────────
    # Moodle dedup: one cmid per tenant (only when cmid is not null)
    op.execute(
        """
        CREATE UNIQUE INDEX uix_tenant_moodle_cmid
        ON content_items (tenant_id, moodle_cmid)
        WHERE moodle_cmid IS NOT NULL
        """
    )
    # Standalone dedup: one asset_id per tenant (only when asset_id is not null)
    op.execute(
        """
        CREATE UNIQUE INDEX uix_tenant_asset_id
        ON content_items (tenant_id, asset_id)
        WHERE asset_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # ── Reverse partial indexes ───────────────────────────────────────────────
    op.execute("DROP INDEX IF EXISTS uix_tenant_asset_id")
    op.execute("DROP INDEX IF EXISTS uix_tenant_moodle_cmid")

    # ── Restore hard unique constraint ────────────────────────────────────────
    # NOTE: downgrade will fail if any rows have NULL moodle_cmid.
    # Clean those rows first if needed.
    op.create_unique_constraint("uq_tenant_cmid", "content_items", ["tenant_id", "moodle_cmid"])

    # ── Make moodle columns NOT NULL again ────────────────────────────────────
    op.alter_column("content_items", "moodle_cmid",       nullable=False)
    op.alter_column("content_items", "moodle_course_id",  nullable=False)

    # ── Drop indexes ──────────────────────────────────────────────────────────
    op.drop_index("ix_content_items_asset_id",  table_name="content_items")
    op.drop_index("ix_content_items_space_id",  table_name="content_items")
    op.drop_index("ix_content_items_origin",    table_name="content_items")

    # ── Drop columns ──────────────────────────────────────────────────────────
    op.drop_column("content_items", "asset_id")
    op.drop_column("content_items", "space_id")
    op.drop_column("content_items", "origin")
