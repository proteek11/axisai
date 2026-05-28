"""
Mail Settings API — admin CRUD for SMTP config + per-trigger email templates.

Routes (all require admin role):
  GET  /admin/settings/email          → return current email_config + email_triggers
  PUT  /admin/settings/email          → save email_config and/or email_triggers
  POST /admin/settings/email/test     → test SMTP connection (no email sent)
  POST /admin/settings/email/send-test → send a real test email to a given address
"""
from __future__ import annotations

from typing import Any, Optional

import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.auth import get_current_user_dep, require_role
from app.core.database import get_db
from app.services.email import send_email, test_smtp

router = APIRouter(tags=["Email Settings"])
log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class SmtpConfig(BaseModel):
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_name: str = "Axis AI"
    from_email: str = ""
    use_tls: bool = True
    use_ssl: bool = False


class TriggerConfig(BaseModel):
    enabled: bool = False
    subject: str = ""
    body: str = ""


class EmailSettings(BaseModel):
    email_config: SmtpConfig
    email_triggers: dict[str, TriggerConfig]


class EmailSettingsUpdate(BaseModel):
    email_config: Optional[SmtpConfig] = None
    email_triggers: Optional[dict[str, TriggerConfig]] = None


class TestConnectionRequest(BaseModel):
    email_config: SmtpConfig


class SendTestRequest(BaseModel):
    email_config: SmtpConfig
    to_email: str


class TestConnectionResponse(BaseModel):
    ok: bool
    error: Optional[str] = None


# Default trigger structure (used when DB row has no triggers yet)
DEFAULT_TRIGGERS: dict[str, dict] = {
    "welcome": {
        "enabled": False,
        "subject": "Welcome to Axis AI — your account is ready",
        "body": (
            "Hi {{full_name}},\n\n"
            "Your Axis AI account has been created.\n\n"
            "Login email: {{email}}\n"
            "Temporary password: {{password}}\n\n"
            "Sign in at: {{login_url}}\n\n"
            "Regards,\nThe Axis AI Team"
        ),
    },
    "space_shared": {
        "enabled": False,
        "subject": "A learning space has been shared with you: {{space_title}}",
        "body": (
            "Hi {{full_name}},\n\n"
            '{{shared_by}} has shared the learning space "{{space_title}}" with you.\n\n'
            "View it here: {{space_url}}\n\n"
            "Regards,\nThe Axis AI Team"
        ),
    },
    "team_added": {
        "enabled": False,
        "subject": "You have been added to the {{team_name}} team",
        "body": (
            "Hi {{full_name}},\n\n"
            'You have been added to the "{{team_name}}" team by {{added_by}}.\n\n'
            "Sign in at: {{login_url}} to access spaces shared with your team.\n\n"
            "Regards,\nThe Axis AI Team"
        ),
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: load / ensure platform settings row
# ─────────────────────────────────────────────────────────────────────────────

async def _get_email_settings(db: AsyncSession) -> tuple[dict, dict]:
    """Return (email_config dict, email_triggers dict) from axis_platform_settings."""
    row = (
        await db.execute(
            text("SELECT email_config, email_triggers FROM axis_platform_settings WHERE singleton_id = 1")
        )
    ).first()

    if not row:
        return {}, DEFAULT_TRIGGERS

    cfg: dict = row.email_config or {}
    triggers: dict = {**DEFAULT_TRIGGERS, **(row.email_triggers or {})}
    return cfg, triggers


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/settings/email
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/admin/settings/email",
    response_model=EmailSettings,
    dependencies=[Depends(require_role("admin"))],
)
async def get_email_settings(db: AsyncSession = Depends(get_db)) -> EmailSettings:
    """Return current SMTP config and per-trigger templates."""
    cfg, triggers = await _get_email_settings(db)

    # Mask password in response
    safe_cfg = {**cfg, "smtp_password": "••••••••" if cfg.get("smtp_password") else ""}

    trigger_models = {
        k: TriggerConfig(**{**DEFAULT_TRIGGERS.get(k, {}), **v})
        for k, v in triggers.items()
    }

    return EmailSettings(
        email_config=SmtpConfig(**{**SmtpConfig().model_dump(), **safe_cfg}),
        email_triggers=trigger_models,
    )


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/settings/email
# ─────────────────────────────────────────────────────────────────────────────

@router.put(
    "/admin/settings/email",
    response_model=EmailSettings,
    dependencies=[Depends(require_role("admin"))],
)
async def update_email_settings(
    req: EmailSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> EmailSettings:
    """Save SMTP config and/or trigger templates. Partial update — omit fields to skip."""
    current_cfg, current_triggers = await _get_email_settings(db)

    if req.email_config is not None:
        new_cfg = req.email_config.model_dump()
        # If password is the masked placeholder, keep the existing password
        if new_cfg.get("smtp_password") == "••••••••":
            new_cfg["smtp_password"] = current_cfg.get("smtp_password", "")
        current_cfg = {**current_cfg, **new_cfg}

    if req.email_triggers is not None:
        for trigger_key, trigger_val in req.email_triggers.items():
            current_triggers[trigger_key] = {
                **current_triggers.get(trigger_key, {}),
                **trigger_val.model_dump(),
            }

    await db.execute(
        text(
            "UPDATE axis_platform_settings "
            "SET email_config = :cfg::jsonb, email_triggers = :triggers::jsonb "
            "WHERE singleton_id = 1"
        ),
        {"cfg": json.dumps(current_cfg), "triggers": json.dumps(current_triggers)},
    )
    await db.commit()
    log.info("email_settings_updated")

    safe_cfg = {**current_cfg, "smtp_password": "••••••••" if current_cfg.get("smtp_password") else ""}
    trigger_models = {
        k: TriggerConfig(**{**DEFAULT_TRIGGERS.get(k, {}), **v})
        for k, v in current_triggers.items()
    }
    return EmailSettings(
        email_config=SmtpConfig(**{**SmtpConfig().model_dump(), **safe_cfg}),
        email_triggers=trigger_models,
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/settings/email/test
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/admin/settings/email/test",
    response_model=TestConnectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def test_email_connection(
    req: TestConnectionRequest,
) -> TestConnectionResponse:
    """Test SMTP connection using the provided config. No email is sent."""
    config = req.email_config.model_dump()
    # Don't use masked placeholder for testing
    if config.get("smtp_password") == "••••••••":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Save the settings first before testing (password is masked).",
        )

    error = await test_smtp(config)
    return TestConnectionResponse(ok=(error is None), error=error)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/settings/email/send-test
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/admin/settings/email/send-test",
    response_model=TestConnectionResponse,
    dependencies=[Depends(require_role("admin"))],
)
async def send_test_email(
    req: SendTestRequest,
    db: AsyncSession = Depends(get_db),
) -> TestConnectionResponse:
    """Send a real test email to verify delivery end-to-end."""
    config = req.email_config.model_dump()

    # Resolve real password if masked
    if config.get("smtp_password") == "••••••••":
        current_cfg, _ = await _get_email_settings(db)
        config["smtp_password"] = current_cfg.get("smtp_password", "")

    error = await test_smtp(config)
    if error:
        return TestConnectionResponse(ok=False, error=error)

    await send_email(
        to_email=req.to_email,
        to_name="",
        subject="Axis AI — SMTP test email",
        body=(
            "This is a test email from Axis AI.\n\n"
            "If you received this, your SMTP configuration is working correctly.\n\n"
            "— Axis AI Admin"
        ),
        config=config,
    )
    return TestConnectionResponse(ok=True)
