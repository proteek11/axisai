"""010_axis_platform_settings

Single-row table that stores platform-wide feature flags for the
axis.edzlms.com frontend. Separate from the Moodle-tenant feature flags
in the `tenants` table.

Only one row will ever exist (enforced by the `singleton_id` primary key
being a fixed constant 1). Admin can GET/PUT via
GET  /api/v1/admin/features
PUT  /api/v1/admin/features

Revision ID: 010
Revises: 009
"""
from alembic import op
import sqlalchemy as sa

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "axis_platform_settings",
        sa.Column(
            "singleton_id",
            sa.Integer,
            primary_key=True,
            comment="Always 1 — enforces single-row semantics",
        ),
        # AI output feature flags
        sa.Column("feature_summary",     sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_quiz",        sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_flashcards",  sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_glossary",    sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_faq",         sa.Boolean, nullable=False, server_default="false"),
        sa.Column("feature_infographic", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_mindmap",     sa.Boolean, nullable=False, server_default="false"),
        sa.Column("feature_objectives",  sa.Boolean, nullable=False, server_default="false"),
        sa.Column("feature_blooms",      sa.Boolean, nullable=False, server_default="false"),
        sa.Column("feature_chat",        sa.Boolean, nullable=False, server_default="true"),
        sa.Column("feature_kb_chat",     sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed the single row
    op.execute("""
        INSERT INTO axis_platform_settings (singleton_id)
        VALUES (1)
        ON CONFLICT (singleton_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("axis_platform_settings")
