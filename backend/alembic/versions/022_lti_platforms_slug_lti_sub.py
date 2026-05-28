"""LTI 1.3: lti_platforms table + users.lti_sub

Revision ID: 022
Revises: 021
Create Date: 2026-05-11

Notes:
- learning_spaces.slug already exists (globally unique) — no change needed.
  LTI lookup uses (tenant_id, slug) which works fine with the existing constraint.
- axis_users.lti_sub is new — stores "<issuer>::<sub>" for JIT-provisioned LTI users.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── lti_platforms ─────────────────────────────────────────────────────────
    op.create_table(
        "lti_platforms",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        # issuer = Moodle site URL, used as LTI Platform ID in JWT iss claim
        sa.Column("issuer", sa.String(512), nullable=False),
        # client_id assigned by Moodle when the tool is registered
        sa.Column("client_id", sa.String(255), nullable=False),
        # Moodle OIDC endpoints
        sa.Column("auth_login_url", sa.String(512), nullable=False),
        sa.Column("auth_token_url", sa.String(512), nullable=False),
        sa.Column("key_set_url", sa.String(512), nullable=False),
        # List of allowed deployment_id strings from Moodle (usually ["1"])
        sa.Column(
            "deployment_ids",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_unique_constraint(
        "uq_lti_platforms_issuer_client_id",
        "lti_platforms",
        ["issuer", "client_id"],
    )
    op.create_index("ix_lti_platforms_tenant_id", "lti_platforms", ["tenant_id"])

    # ── axis_users.lti_sub ────────────────────────────────────────────────────
    # Stores "<issuer>::<sub>" — namespaced so users from different Moodle
    # installs never collide even if Moodle reuses numeric user IDs.
    op.add_column(
        "axis_users",
        sa.Column("lti_sub", sa.String(512), nullable=True),
    )
    op.create_index(
        "ix_axis_users_lti_sub",
        "axis_users",
        ["lti_sub"],
        postgresql_where=sa.text("lti_sub IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_axis_users_lti_sub", table_name="axis_users")
    op.drop_column("axis_users", "lti_sub")

    op.drop_index("ix_lti_platforms_tenant_id", table_name="lti_platforms")
    op.drop_constraint("uq_lti_platforms_issuer_client_id", "lti_platforms")
    op.drop_table("lti_platforms")
