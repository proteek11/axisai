"""024_email_settings

Add email_config and email_triggers JSONB columns to axis_platform_settings.

email_config  — SMTP connection settings (host, port, user, pass, TLS, from)
email_triggers — per-trigger enable flag + subject + body template

Revision ID: 024
Revises: 023
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

# Default SMTP config (all empty — admin must fill before emails send)
DEFAULT_EMAIL_CONFIG = """{
    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "from_name": "Axis AI",
    "from_email": "",
    "use_tls": true,
    "use_ssl": false
}"""

# Default templates with {{variable}} placeholders
DEFAULT_EMAIL_TRIGGERS = """{
    "welcome": {
        "enabled": false,
        "subject": "Welcome to Axis AI — your account is ready",
        "body": "Hi {{full_name}},\\n\\nYour Axis AI account has been created.\\n\\nLogin email: {{email}}\\nTemporary password: {{password}}\\n\\nSign in at: {{login_url}}\\n\\nIf you have any questions, contact your administrator.\\n\\nRegards,\\nThe Axis AI Team"
    },
    "space_shared": {
        "enabled": false,
        "subject": "A learning space has been shared with you: {{space_title}}",
        "body": "Hi {{full_name}},\\n\\n{{shared_by}} has shared the learning space \\"{{space_title}}\\" with you.\\n\\nView it here: {{space_url}}\\n\\nRegards,\\nThe Axis AI Team"
    },
    "team_added": {
        "enabled": false,
        "subject": "You have been added to the {{team_name}} team",
        "body": "Hi {{full_name}},\\n\\nYou have been added to the \\"{{team_name}}\\" team by {{added_by}}.\\n\\nSign in at: {{login_url}} to access all spaces shared with your team.\\n\\nRegards,\\nThe Axis AI Team"
    }
}"""


def upgrade() -> None:
    op.add_column(
        "axis_platform_settings",
        sa.Column(
            "email_config",
            JSONB,
            nullable=False,
            server_default=DEFAULT_EMAIL_CONFIG,
            comment="SMTP connection settings",
        ),
    )
    op.add_column(
        "axis_platform_settings",
        sa.Column(
            "email_triggers",
            JSONB,
            nullable=False,
            server_default=DEFAULT_EMAIL_TRIGGERS,
            comment="Per-trigger email enable flag + subject + body template",
        ),
    )


def downgrade() -> None:
    op.drop_column("axis_platform_settings", "email_triggers")
    op.drop_column("axis_platform_settings", "email_config")
