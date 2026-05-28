"""027_ic_feature_and_ai_provider

Add feature_interactive_content flag to axis_platform_settings so admins
can enable / disable the Interactive Content module for all users.

Also adds ai_provider, ai_model, and ai_model_fast so the admin can
switch between AI backends (OpenAI / Anthropic / Gemini / Mistral)
from the dashboard without touching code.

Revision ID: 027
Revises: 026
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── IC feature toggle ─────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE axis_platform_settings "
        "DROP COLUMN IF EXISTS feature_interactive_content"
    )
    op.add_column(
        "axis_platform_settings",
        sa.Column(
            "feature_interactive_content",
            sa.Boolean,
            nullable=False,
            server_default=sa.true(),
            comment="Enable/disable the Interactive Content module globally",
        ),
    )

    # ── AI provider & model selection ────────────────────────────────────────
    for col, default in [
        ("ai_provider",    "openai"),
        ("ai_model",       "gpt-4o"),
        ("ai_model_fast",  "gpt-4o-mini"),
    ]:
        op.execute(
            f"ALTER TABLE axis_platform_settings DROP COLUMN IF EXISTS {col}"
        )
        op.add_column(
            "axis_platform_settings",
            sa.Column(
                col,
                sa.String(120),
                nullable=False,
                server_default=default,
                comment=f"LiteLLM model string for {col}",
            ),
        )


def downgrade() -> None:
    for col in [
        "feature_interactive_content",
        "ai_provider",
        "ai_model",
        "ai_model_fast",
    ]:
        op.drop_column("axis_platform_settings", col)
