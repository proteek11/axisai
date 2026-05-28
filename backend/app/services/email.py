"""
Email service — sends transactional emails via SMTP.

Uses Python's built-in smtplib + email.mime (no extra dependencies).
All sends are fire-and-forget: run in a thread-pool executor so the API
response is never delayed by SMTP round-trips. Failures are logged but
never propagate back to the caller.

Usage:
    from app.services.email import send_email, send_trigger_email

    # Low-level
    await send_email(
        to_email="user@example.com",
        to_name="Alice",
        subject="Hello",
        body="Plain-text body",
        config={...smtp config dict...},
    )

    # High-level (reads config + template from DB, renders vars, fires if enabled)
    await send_trigger_email(
        db=db,
        trigger="welcome",
        to_email="user@example.com",
        to_name="Alice",
        variables={"full_name": "Alice", "email": "user@example.com", ...},
    )
"""
from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = structlog.get_logger(__name__)


def _smtp_send(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    use_tls: bool,
    use_ssl: bool,
    from_name: str,
    from_email: str,
    to_email: str,
    to_name: str,
    subject: str,
    body: str,
) -> None:
    """Synchronous SMTP send — called via run_in_executor."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    msg.attach(MIMEText(body, "plain", "utf-8"))
    html_body = "<html><body>" + body.replace("\n", "<br>") + "</body></html>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())


async def send_email(
    *,
    to_email: str,
    to_name: str = "",
    subject: str,
    body: str,
    config: dict[str, Any],
) -> None:
    """
    Fire-and-forget email send. Never raises — all errors are logged.
    config keys: smtp_host, smtp_port, smtp_user, smtp_password,
                 from_name, from_email, use_tls, use_ssl
    """
    smtp_host = config.get("smtp_host", "")
    from_email = config.get("from_email", "")

    if not smtp_host or not from_email:
        log.warning("email_skipped", reason="smtp_host or from_email not configured")
        return

    fn = partial(
        _smtp_send,
        smtp_host=smtp_host,
        smtp_port=int(config.get("smtp_port", 587)),
        smtp_user=config.get("smtp_user", ""),
        smtp_password=config.get("smtp_password", ""),
        use_tls=bool(config.get("use_tls", True)),
        use_ssl=bool(config.get("use_ssl", False)),
        from_name=config.get("from_name", "Axis AI"),
        from_email=from_email,
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        body=body,
    )

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, fn)
        log.info("email_sent", to=to_email, subject=subject)
    except Exception as exc:
        log.error("email_send_failed", to=to_email, subject=subject, error=str(exc))


async def send_trigger_email(
    *,
    db: AsyncSession,
    trigger: str,
    to_email: str,
    to_name: str = "",
    variables: dict[str, str],
) -> None:
    """
    Read email config + trigger template from axis_platform_settings,
    render {{variable}} placeholders, and send if trigger is enabled.

    trigger: one of "welcome" | "space_shared" | "team_added"
    """
    try:
        row = (
            await db.execute(
                text(
                    "SELECT email_config, email_triggers "
                    "FROM axis_platform_settings WHERE singleton_id = 1"
                )
            )
        ).first()
    except Exception:
        return  # columns not yet migrated — safe no-op

    if not row:
        return

    email_config: dict = row.email_config or {}
    email_triggers: dict = row.email_triggers or {}

    trigger_cfg = email_triggers.get(trigger, {})
    if not trigger_cfg.get("enabled", False):
        return

    subject_tmpl: str = trigger_cfg.get("subject", "")
    body_tmpl: str = trigger_cfg.get("body", "")

    for key, val in variables.items():
        ph = "{{" + key + "}}"
        subject_tmpl = subject_tmpl.replace(ph, str(val))
        body_tmpl = body_tmpl.replace(ph, str(val))

    await send_email(
        to_email=to_email,
        to_name=to_name,
        subject=subject_tmpl,
        body=body_tmpl,
        config=email_config,
    )


async def test_smtp(config: dict[str, Any]) -> str | None:
    """
    Attempt an SMTP connection. Returns None on success, error string on failure.
    """
    smtp_host = config.get("smtp_host", "")
    from_email = config.get("from_email", "")

    if not smtp_host or not from_email:
        return "smtp_host and from_email are required"

    def _connect() -> None:
        if config.get("use_ssl"):
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_host, int(config.get("smtp_port", 465)), context=ctx) as s:
                if config.get("smtp_user"):
                    s.login(config["smtp_user"], config.get("smtp_password", ""))
        else:
            with smtplib.SMTP(smtp_host, int(config.get("smtp_port", 587))) as s:
                if config.get("use_tls"):
                    s.starttls()
                if config.get("smtp_user"):
                    s.login(config["smtp_user"], config.get("smtp_password", ""))

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _connect)
        return None
    except Exception as exc:
        return str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Public: send_otp_email — password-reset OTP (no db arg required)
# ─────────────────────────────────────────────────────────────────────────────

async def send_otp_email(
    to_email: str,
    otp: str,
    *,
    site_name: str = "Axis AI",
    primary_color: str = "#1447e6",
) -> None:
    """
    Send a password-reset OTP email. Reads SMTP config from axis_platform_settings.
    Opens its own DB session so no db arg is needed at the call site.
    Silently no-ops if SMTP is not configured — never raises.
    """
    try:
        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT email_config FROM axis_platform_settings "
                        "WHERE singleton_id = 1"
                    )
                )
            ).first()

        email_config: dict[str, Any] = (row.email_config or {}) if row else {}

        subject = f"Your {site_name} password reset code"
        body = (
            f"Hi,\n\n"
            f"Your one-time password reset code for {site_name} is:\n\n"
            f"    {otp}\n\n"
            f"This code expires in 10 minutes. If you did not request a reset, "
            f"please ignore this email.\n\n"
            f"— The {site_name} Team"
        )

        await send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            config=email_config,
        )
    except Exception as exc:
        log.error("otp_email_failed", to=to_email, error=str(exc))


# ─────────────────────────────────────────────────────────────────────────────
# Certificate email — sends congratulations + PDF attachment
# ─────────────────────────────────────────────────────────────────────────────

def _smtp_send_with_attachment(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    use_tls: bool,
    use_ssl: bool,
    from_name: str,
    from_email: str,
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    body_html: str,
    attachment_bytes: bytes,
    attachment_filename: str,
) -> None:
    """Synchronous SMTP send with a binary attachment — called via run_in_executor."""
    from email.mime.base import MIMEBase
    from email import encoders

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>" if from_name else from_email
    msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

    # Text + HTML alternatives as a nested multipart/alternative
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(body_text, "plain", "utf-8"))
    alt.attach(MIMEText(body_html, "html", "utf-8"))
    msg.attach(alt)

    # PDF attachment
    part = MIMEBase("application", "pdf")
    part.set_payload(attachment_bytes)
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", "attachment", filename=attachment_filename)
    msg.attach(part)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_host, smtp_port, context=context) as server:
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())
    else:
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            if use_tls:
                server.starttls()
            if smtp_user:
                server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to_email], msg.as_string())


async def send_certificate_email(
    *,
    to_email: str,
    to_name: str,
    space_title: str,
    pdf_bytes: bytes,
    pdf_filename: str,
    site_name: str = "Axis AI",
    site_url: str = "https://axis.edzlms.com",
) -> None:
    """
    Fire-and-forget: send a certificate congratulations email with the PDF attached.
    Reads SMTP config from axis_platform_settings.
    Silently no-ops if SMTP is not configured — never raises.
    """
    try:
        from app.core.database import AsyncSessionFactory

        async with AsyncSessionFactory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT email_config FROM axis_platform_settings "
                        "WHERE singleton_id = 1"
                    )
                )
            ).first()

        email_config: dict[str, Any] = (row.email_config or {}) if row else {}
        smtp_host = email_config.get("smtp_host", "")
        from_email = email_config.get("from_email", "")

        if not smtp_host or not from_email:
            log.warning("certificate_email_skipped", reason="SMTP not configured", to=to_email)
            return

        subject = f'🎉 Your certificate for "{space_title}" is ready!'
        body_text = (
            f"Hi {to_name},\n\n"
            f"Congratulations! You have successfully completed \"{space_title}\".\n\n"
            f"Your certificate of completion is attached to this email as a PDF.\n\n"
            f"You can also download it anytime from {site_url}.\n\n"
            f"— The {site_name} Team"
        )
        body_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:560px;margin:40px auto;color:#0c090c">
  <div style="background:#1447e6;padding:32px 40px;border-radius:12px 12px 0 0">
    <h1 style="color:#fff;margin:0;font-size:22px">🎉 Congratulations, {to_name}!</h1>
  </div>
  <div style="border:1px solid #e7e4e7;border-top:none;padding:32px 40px;border-radius:0 0 12px 12px">
    <p style="font-size:16px;line-height:1.6">
      You have successfully completed <strong>{space_title}</strong>.
    </p>
    <p style="font-size:15px;line-height:1.6;color:#79697b">
      Your certificate of completion is attached to this email as a PDF.
      You can also download it anytime from your learning dashboard.
    </p>
    <div style="margin:28px 0">
      <a href="{site_url}" style="background:#1447e6;color:#fff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px">
        Go to {site_name}
      </a>
    </div>
    <p style="font-size:12px;color:#b4b2a9;margin-top:32px">
      © {site_name} · {site_url}
    </p>
  </div>
</body>
</html>"""

        fn = partial(
            _smtp_send_with_attachment,
            smtp_host=smtp_host,
            smtp_port=int(email_config.get("smtp_port", 587)),
            smtp_user=email_config.get("smtp_user", ""),
            smtp_password=email_config.get("smtp_password", ""),
            use_tls=bool(email_config.get("smtp_use_tls", True)),
            use_ssl=bool(email_config.get("smtp_use_ssl", False)),
            from_name=email_config.get("smtp_from_name", site_name),
            from_email=from_email,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachment_bytes=pdf_bytes,
            attachment_filename=pdf_filename,
        )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, fn)
        log.info("certificate_email_sent", to=to_email, space=space_title)

    except Exception as exc:
        log.error("certificate_email_failed", to=to_email, error=str(exc))
