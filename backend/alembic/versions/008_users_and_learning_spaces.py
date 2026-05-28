"""008_users_and_learning_spaces

Adds standalone user auth (axis_users, refresh_tokens) and the
Learning Space concept (learning_spaces, space_items, space_access,
share_tokens) for the axis.edzlms.com Next.js frontend.

Revision ID: 008
Revises: 007
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── axis_users ────────────────────────────────────────────────────────────
    op.create_table(
        "axis_users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_axis_users_tenant", "axis_users", ["tenant_id"])
    op.create_index("idx_axis_users_email", "axis_users", ["email"])

    # ── refresh_tokens ────────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_refresh_tokens_user", "refresh_tokens", ["user_id"])

    # ── learning_spaces ───────────────────────────────────────────────────────
    op.create_table(
        "learning_spaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("creator_id", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_image_url", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_guest_accessible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("tags", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_spaces_tenant", "learning_spaces", ["tenant_id"])
    op.create_index("idx_spaces_creator", "learning_spaces", ["creator_id"])
    op.create_index("idx_spaces_slug", "learning_spaces", ["slug"])

    # ── space_items ───────────────────────────────────────────────────────────
    op.create_table(
        "space_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True),
                  sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("content_item_id", UUID(as_uuid=True),
                  sa.ForeignKey("content_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("title_override", sa.String(255), nullable=True),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("visible_outputs", JSONB(), nullable=False,
                  server_default=sa.text("'[\"summary\",\"glossary\",\"flashcards\",\"quiz\",\"infographic\"]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("space_id", "content_item_id", name="uq_space_content"),
    )
    op.create_index("idx_space_items_space", "space_items", ["space_id"])

    # ── space_access ──────────────────────────────────────────────────────────
    op.create_table(
        "space_access",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True),
                  sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("axis_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("space_id", "user_id", name="uq_space_user"),
    )

    # ── share_tokens ──────────────────────────────────────────────────────────
    op.create_table(
        "share_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("space_id", UUID(as_uuid=True),
                  sa.ForeignKey("learning_spaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_access", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_share_tokens_space", "share_tokens", ["space_id"])


def downgrade() -> None:
    op.drop_table("share_tokens")
    op.drop_table("space_access")
    op.drop_table("space_items")
    op.drop_table("learning_spaces")
    op.drop_table("refresh_tokens")
    op.drop_table("axis_users")
