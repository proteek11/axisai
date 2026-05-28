"""029 — PF-02 Completion Certificates + PF-05 PDF Annotations.

- space_certificates: issued when a learner completes all items in a space
- pdf_annotations: learner highlights/notes on Interactive PDF content
- Add content_type values: interactive_pdf, interactive_slides (String col, no enum migration)
- Add slide_assets JSONB column to content_items for PPTX slide image paths

Revision ID: 029
Revises: 028
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. space_certificates ─────────────────────────────────────────────
    op.create_table(
        "space_certificates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "space_id", UUID(as_uuid=True),
            sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        # Store the rendered PDF bytes as base64 OR a filesystem path
        sa.Column("pdf_path", sa.Text(), nullable=True),
        # Snapshot of learner name, space title, completion date at issuance time
        sa.Column("cert_data", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_index("ix_space_certs_user_space", "space_certificates", ["user_id", "space_id"], unique=True)
    op.create_index("ix_space_certs_space", "space_certificates", ["space_id"])

    # ── 2. pdf_annotations ───────────────────────────────────────────────
    op.create_table(
        "pdf_annotations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id", UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "content_item_id", UUID(as_uuid=True),
            sa.ForeignKey("content_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_num", sa.Integer(), nullable=False),
        # type: 'highlight' | 'note' | 'underline'
        sa.Column("annotation_type", sa.String(20), nullable=False, server_default="highlight"),
        # Selected text or note content
        sa.Column("content", sa.Text(), nullable=False),
        # PDF text-layer position: {x, y, width, height, quad_points: [...]}
        sa.Column("position_data", JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("color", sa.String(7), server_default="#FFF176", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=True),
    )
    op.create_index("ix_pdf_annotations_content_user", "pdf_annotations", ["content_item_id", "user_id"])
    op.create_index("ix_pdf_annotations_user", "pdf_annotations", ["user_id"])

    # ── 3. slide_assets column on content_items ───────────────────────────
    # Stores list of {index, path, thumbnail_path} for converted PPTX slides
    op.add_column(
        "content_items",
        sa.Column("slide_assets", JSONB, server_default=sa.text("'[]'::jsonb"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("content_items", "slide_assets")
    op.drop_index("ix_pdf_annotations_user", "pdf_annotations")
    op.drop_index("ix_pdf_annotations_content_user", "pdf_annotations")
    op.drop_table("pdf_annotations")
    op.drop_index("ix_space_certs_space", "space_certificates")
    op.drop_index("ix_space_certs_user_space", "space_certificates")
    op.drop_table("space_certificates")
