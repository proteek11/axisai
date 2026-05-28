"""009_token_budgets

Adds per-user token budget tracking and role-level budget defaults.
Admins can override any user's monthly token limit. The AIClient
enforces the limit before every generation call.

Tables:
  - token_budget_defaults  — monthly_limit per role (admin/creator/learner)
  - user_token_budgets     — per-user limit + running monthly usage counter

Revision ID: 009
Revises: 008
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── token_budget_defaults ────────────────────────────────────────────────
    # One row per role; admin can update monthly_limit via API.
    op.create_table(
        "token_budget_defaults",
        sa.Column("role", sa.String(20), primary_key=True),
        sa.Column(
            "monthly_token_limit",
            sa.Integer,
            nullable=False,
            comment="Default monthly token limit for this role",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Seed defaults: admin 2M, creator 500k, learner 100k tokens/month
    op.execute("""
        INSERT INTO token_budget_defaults (role, monthly_token_limit)
        VALUES
            ('admin',   2000000),
            ('creator',  500000),
            ('learner',  100000)
        ON CONFLICT (role) DO NOTHING
    """)

    # ── user_token_budgets ───────────────────────────────────────────────────
    # One row per user. Created lazily on first AI generation, or eagerly by
    # admin override. monthly_token_limit = NULL means "use role default".
    op.create_table(
        "user_token_budgets",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("axis_users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "monthly_token_limit",
            sa.Integer,
            nullable=True,
            comment="NULL = use role default from token_budget_defaults",
        ),
        sa.Column(
            "tokens_used_this_month",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "override_reason",
            sa.Text,
            nullable=True,
            comment="Admin note explaining why this user has a custom limit",
        ),
        sa.Column(
            "override_set_by",
            UUID(as_uuid=True),
            nullable=True,
            comment="axis_users.id of the admin who set the override",
        ),
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

    op.create_index(
        "ix_user_token_budgets_user_id",
        "user_token_budgets",
        ["user_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_token_budgets_user_id", table_name="user_token_budgets")
    op.drop_table("user_token_budgets")
    op.drop_table("token_budget_defaults")
