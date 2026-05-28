"""
Live Class (Zoom) API — Phase 19B.

Endpoints:
  Spaces:
    GET  /spaces/{space_id}/live-classes          — list sessions for a space
    POST /spaces/{space_id}/live-classes          — schedule a new Zoom meeting

  Sessions:
    GET    /live-classes/{session_id}             — get session detail
    PATCH  /live-classes/{session_id}             — update title/time/toggles
    DELETE /live-classes/{session_id}             — cancel + delete from Zoom
    POST   /live-classes/{session_id}/import-now  — manually trigger recording + attendance import
    GET    /live-classes/{session_id}/attendance  — get participant list

  Admin:
    GET  /admin/zoom-config                       — get current Zoom config (secrets masked)
    POST /admin/zoom-config                       — save/update Zoom credentials (encrypted before storing)
    POST /admin/zoom-config/test                  — test credentials against Zoom API

  Webhook (public — no auth, HMAC-verified):
    POST /webhooks/zoom                           — Zoom event receiver
"""
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.live_class import LiveClassSession, LiveClassAttendance, LiveClassStatus
from app.models.user import AxisUser
from app.models.tenant import Tenant
from app.schemas.live_class import (
    ScheduleLiveClassRequest,
    UpdateLiveClassRequest,
    LiveClassSessionResponse,
    LiveClassListResponse,
    AttendanceRecord,
    ZoomConfigRequest,
    ZoomConfigResponse,
    ZoomTestResponse,
)
from .auth import get_current_user

log = structlog.get_logger(__name__)

router = APIRouter()
_bearer = HTTPBearer(auto_error=True)


# ── Space → Live Classes ──────────────────────────────────────────────────────

@router.get("/spaces/{space_id}/live-classes", response_model=LiveClassListResponse)
async def list_live_classes(
    space_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """List all live class sessions for a space (any authenticated user with space access)."""
    current: AxisUser = await get_current_user(credentials.credentials, db)

    from sqlalchemy.orm import noload
    r = await db.execute(
        select(LiveClassSession)
        .where(LiveClassSession.space_id == space_id)
        .order_by(LiveClassSession.scheduled_at.desc())
        .options(noload(LiveClassSession.attendance))  # prevent lazy-load MissingGreenlet
    )
    sessions = r.scalars().all()
    return LiveClassListResponse(sessions=sessions, total=len(sessions))


@router.post("/spaces/{space_id}/live-classes",
             response_model=LiveClassSessionResponse,
             status_code=status.HTTP_201_CREATED)
async def schedule_live_class(
    space_id: uuid.UUID,
    body: ScheduleLiveClassRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Schedule a new Zoom live class for a space.
    Creates the meeting in Zoom and stores session in DB.
    """
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    tenant_id = current.tenant_id

    from app.config import settings
    from app.services.zoom_service import zoom_service_from_config

    # Load tenant
    r = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = r.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Check Zoom is configured
    tenant_config = tenant.config or {}
    enc_key = settings.video_encryption_key or settings.secret_key

    try:
        zoom = zoom_service_from_config(tenant_config, enc_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Apply tenant defaults for any toggle not specified
    def _default(val, config_key: str, fallback: bool = True) -> bool:
        if val is not None:
            return val
        return tenant_config.get(config_key, fallback)

    auto_record = _default(body.auto_record, "zoom_default_auto_record", True)
    import_recording = _default(body.import_recording, "zoom_default_import_recording", True)
    import_attendance = _default(body.import_attendance, "zoom_default_import_attendance", True)
    generate_ai = _default(body.generate_ai_outputs, "zoom_default_generate_ai", True)

    # Create meeting in Zoom
    scheduled_iso = body.scheduled_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        zoom_meeting = await zoom.create_meeting(
            title=body.title,
            description=body.description or "",
            start_iso=scheduled_iso,
            duration_minutes=body.duration_minutes,
            auto_record=auto_record,
        )
    except Exception as e:
        log.error("zoom_create_meeting_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Zoom API error: {e}")

    # Persist session
    session = LiveClassSession(
        space_id=space_id,
        tenant_id=tenant_id,
        provider="zoom",
        external_meeting_id=str(zoom_meeting.get("id")),
        external_meeting_uuid=zoom_meeting.get("uuid"),
        title=body.title,
        description=body.description,
        scheduled_at=body.scheduled_at,
        duration_minutes=body.duration_minutes,
        join_url=zoom_meeting.get("join_url"),
        host_url=zoom_meeting.get("start_url"),
        password=zoom_meeting.get("password"),
        status=LiveClassStatus.SCHEDULED,
        auto_record=auto_record,
        import_recording=import_recording,
        import_attendance=import_attendance,
        generate_ai_outputs=generate_ai,
        notify_learners=body.notify_learners,
        created_by_user_id=current.id,
        created_by_email=current.email,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    # Notify learners
    if body.notify_learners:
        from app.tasks.live_class_tasks import notify_live_class
        notify_live_class.delay(str(session.id), "scheduled")

    log.info("live_class_scheduled",
             session_id=str(session.id),
             zoom_id=session.external_meeting_id,
             space_id=str(space_id))
    return session


# ── Session detail / update / cancel ─────────────────────────────────────────

@router.get("/live-classes/{session_id}", response_model=LiveClassSessionResponse)
async def get_live_class(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Get a single live class session."""
    current: AxisUser = await get_current_user(credentials.credentials, db)

    r = await db.execute(
        select(LiveClassSession).where(LiveClassSession.id == session_id)
    )
    session = r.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.patch("/live-classes/{session_id}", response_model=LiveClassSessionResponse)
async def update_live_class(
    session_id: uuid.UUID,
    body: UpdateLiveClassRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Update session title, time, or toggle fields. Syncs changes to Zoom."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    r = await db.execute(
        select(LiveClassSession).where(LiveClassSession.id == session_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Session not found")
    if cls.status == LiveClassStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cannot update a cancelled session")

    # Apply field updates
    changed_in_zoom: dict = {}
    if body.title is not None:
        cls.title = body.title
        changed_in_zoom["title"] = body.title
    if body.description is not None:
        cls.description = body.description
    if body.scheduled_at is not None:
        cls.scheduled_at = body.scheduled_at
        changed_in_zoom["scheduled_at"] = body.scheduled_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    if body.duration_minutes is not None:
        cls.duration_minutes = body.duration_minutes
        changed_in_zoom["duration_minutes"] = body.duration_minutes
    if body.import_recording is not None:
        cls.import_recording = body.import_recording
    if body.import_attendance is not None:
        cls.import_attendance = body.import_attendance
    if body.generate_ai_outputs is not None:
        cls.generate_ai_outputs = body.generate_ai_outputs
    if body.notify_learners is not None:
        cls.notify_learners = body.notify_learners

    # Sync to Zoom if meeting-level fields changed
    if changed_in_zoom and cls.external_meeting_id:
        try:
            from app.config import settings
            from app.services.zoom_service import zoom_service_from_config
            r2 = await db.execute(select(Tenant).where(Tenant.id == cls.tenant_id))
            tenant = r2.scalar_one_or_none()
            if tenant:
                enc_key = settings.video_encryption_key or settings.secret_key
                zoom = zoom_service_from_config(tenant.config or {}, enc_key)
                await zoom.update_meeting(
                    cls.external_meeting_id,
                    title=changed_in_zoom.get("title"),
                    scheduled_at=changed_in_zoom.get("scheduled_at"),
                    duration_minutes=changed_in_zoom.get("duration_minutes"),
                )
        except Exception as e:
            log.warning("zoom_update_meeting_failed",
                        session_id=str(session_id), error=str(e))

    await db.commit()
    await db.refresh(cls)

    # Notify learners of update
    if cls.notify_learners:
        from app.tasks.live_class_tasks import notify_live_class
        notify_live_class.delay(str(cls.id), "updated")

    return cls


@router.delete("/live-classes/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_live_class(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a live class — marks status=cancelled and deletes from Zoom."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    r = await db.execute(
        select(LiveClassSession).where(LiveClassSession.id == session_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Session not found")
    if cls.status in (LiveClassStatus.LIVE, LiveClassStatus.ENDED):
        raise HTTPException(status_code=409, detail="Cannot cancel a session that has already started or ended")

    # Delete from Zoom
    if cls.external_meeting_id:
        try:
            from app.config import settings
            from app.services.zoom_service import zoom_service_from_config
            r2 = await db.execute(select(Tenant).where(Tenant.id == cls.tenant_id))
            tenant = r2.scalar_one_or_none()
            if tenant:
                enc_key = settings.video_encryption_key or settings.secret_key
                zoom = zoom_service_from_config(tenant.config or {}, enc_key)
                await zoom.delete_meeting(cls.external_meeting_id)
        except Exception as e:
            log.warning("zoom_delete_meeting_failed",
                        session_id=str(session_id), error=str(e))

    cls.status = LiveClassStatus.CANCELLED
    await db.commit()

    # Notify learners of cancellation
    if cls.notify_learners:
        from app.tasks.live_class_tasks import notify_live_class
        notify_live_class.delay(str(cls.id), "cancelled")


@router.post("/live-classes/{session_id}/import-now", status_code=status.HTTP_202_ACCEPTED)
async def import_now(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger recording + attendance import for a session.
    Useful when webhook was missed or import failed.
    """
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    r = await db.execute(
        select(LiveClassSession).where(LiveClassSession.id == session_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.tasks.live_class_tasks import import_live_recording, import_attendance_report
    from datetime import datetime, timezone

    # Auto-mark as ended only if past scheduled end time (webhook missed)
    # If meeting is still in future, tasks will run but Zoom will return no data → session → failed (safe)
    if cls.status in (LiveClassStatus.SCHEDULED, LiveClassStatus.LIVE):
        from datetime import timedelta
        end_time = cls.scheduled_at + timedelta(minutes=(cls.duration_minutes or 60))
        if datetime.now(timezone.utc) > end_time:
            cls.status = LiveClassStatus.ENDED
            cls.actual_end_at = cls.actual_end_at or datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(cls)
            log.info("import_now_auto_ended", session_id=str(session_id))

    tasks_queued = []
    if cls.import_recording:
        import_live_recording.delay(str(session_id))
        tasks_queued.append("import_recording")
    if cls.import_attendance:
        import_attendance_report.delay(str(session_id))
        tasks_queued.append("import_attendance")

    return {"queued": tasks_queued, "session_id": str(session_id), "status": cls.status}


@router.get("/live-classes/{session_id}/attendance")
async def get_attendance(
    session_id: uuid.UUID,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Get the attendance list for a completed session."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role not in ("creator", "admin"):
        raise HTTPException(status_code=403, detail="Creator or admin access required")

    r = await db.execute(
        select(LiveClassSession).where(LiveClassSession.id == session_id)
    )
    cls = r.scalar_one_or_none()
    if not cls:
        raise HTTPException(status_code=404, detail="Session not found")

    r2 = await db.execute(
        select(LiveClassAttendance)
        .where(LiveClassAttendance.session_id == session_id)
        .order_by(LiveClassAttendance.joined_at)
    )
    records = r2.scalars().all()
    return {
        "session_id": str(session_id),
        "participant_count": cls.participant_count or len(records),
        "attendance": [AttendanceRecord.model_validate(rec) for rec in records],
    }


# ── Admin — Zoom config ───────────────────────────────────────────────────────

@router.get("/admin/zoom-config", response_model=ZoomConfigResponse)
async def get_zoom_config(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Get the current tenant Zoom configuration (secrets shown as boolean flags)."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant_id = current.tenant_id

    r = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = r.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    cfg = tenant.config or {}
    from app.config import settings

    base_url = str(settings.api_base_url).rstrip("/") if hasattr(settings, "api_base_url") else "https://axisai.edzlms.com"
    webhook_url = f"{base_url}/api/v1/webhooks/zoom"

    return ZoomConfigResponse(
        zoom_enabled=cfg.get("zoom_enabled", False),
        zoom_account_id=cfg.get("zoom_account_id", ""),
        zoom_client_id=cfg.get("zoom_client_id", ""),
        zoom_client_secret_set=bool(cfg.get("zoom_client_secret")),
        zoom_webhook_secret_set=bool(cfg.get("zoom_webhook_secret")),
        webhook_url=webhook_url,
        zoom_default_auto_record=cfg.get("zoom_default_auto_record", True),
        zoom_default_import_recording=cfg.get("zoom_default_import_recording", True),
        zoom_default_import_attendance=cfg.get("zoom_default_import_attendance", True),
        zoom_default_generate_ai=cfg.get("zoom_default_generate_ai", True),
    )


@router.post("/admin/zoom-config", response_model=ZoomConfigResponse)
async def save_zoom_config(
    body: ZoomConfigRequest,
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Save Zoom API credentials (secrets are Fernet-encrypted before storing)."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant_id = current.tenant_id

    r = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = r.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from app.config import settings
    from app.services.zoom_service import encrypt_secret

    enc_key = settings.video_encryption_key or settings.secret_key

    cfg = tenant.config or {}

    # Only update secrets if a new value was provided (not the <<KEEP_EXISTING>> placeholder)
    new_client_secret = body.zoom_client_secret
    new_webhook_secret = body.zoom_webhook_secret

    if new_client_secret and new_client_secret != "<<KEEP_EXISTING>>":
        cfg["zoom_client_secret"] = encrypt_secret(new_client_secret, enc_key)
    if new_webhook_secret and new_webhook_secret != "<<KEEP_EXISTING>>":
        cfg["zoom_webhook_secret"] = encrypt_secret(new_webhook_secret, enc_key)

    cfg.update({
        "zoom_enabled": body.zoom_enabled,
        "zoom_account_id": body.zoom_account_id,
        "zoom_client_id": body.zoom_client_id,
        "zoom_default_auto_record": body.zoom_default_auto_record,
        "zoom_default_import_recording": body.zoom_default_import_recording,
        "zoom_default_import_attendance": body.zoom_default_import_attendance,
        "zoom_default_generate_ai": body.zoom_default_generate_ai,
    })
    tenant.config = cfg

    # Mark config as modified (needed for JSONB mutation detection in SQLAlchemy)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(tenant, "config")

    await db.commit()

    log.info("zoom_config_saved", tenant_id=str(tenant_id))

    base_url = str(settings.api_base_url).rstrip("/") if hasattr(settings, "api_base_url") else "https://axisai.edzlms.com"
    webhook_url = f"{base_url}/api/v1/webhooks/zoom"

    return ZoomConfigResponse(
        zoom_enabled=body.zoom_enabled,
        zoom_account_id=body.zoom_account_id,
        zoom_client_id=body.zoom_client_id,
        zoom_client_secret_set=bool(cfg.get("zoom_client_secret")),
        zoom_webhook_secret_set=bool(cfg.get("zoom_webhook_secret")),
        webhook_url=webhook_url,
        zoom_default_auto_record=body.zoom_default_auto_record,
        zoom_default_import_recording=body.zoom_default_import_recording,
        zoom_default_import_attendance=body.zoom_default_import_attendance,
        zoom_default_generate_ai=body.zoom_default_generate_ai,
    )


@router.post("/admin/zoom-config/test", response_model=ZoomTestResponse)
async def test_zoom_config(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
    db: AsyncSession = Depends(get_db),
):
    """Test the stored Zoom credentials by calling GET /users/me."""
    current: AxisUser = await get_current_user(credentials.credentials, db)
    if current.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    tenant_id = current.tenant_id

    r = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = r.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from app.config import settings
    from app.services.zoom_service import zoom_service_from_config, ZoomAPIError

    enc_key = settings.video_encryption_key or settings.secret_key
    try:
        zoom = zoom_service_from_config(tenant.config or {}, enc_key)
        result = await zoom.test_connection()
        return ZoomTestResponse(**result)
    except ValueError as e:
        return ZoomTestResponse(ok=False, error=str(e))
    except ZoomAPIError as e:
        return ZoomTestResponse(ok=False, error=str(e))
    except Exception as e:
        return ZoomTestResponse(ok=False, error=f"Unexpected error: {e}")


# ── Zoom Webhook (public — HMAC-verified) ─────────────────────────────────────

@router.post("/webhooks/zoom", include_in_schema=False)
async def zoom_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_zm_signature: Optional[str] = Header(None),
    x_zm_request_timestamp: Optional[str] = Header(None),
):
    """
    Zoom webhook receiver.
    - Verifies HMAC-SHA256 signature before processing any event.
    - Handles URL validation challenge (sent when first registering the webhook).
    - Handles: meeting.ended, recording.completed
    """
    body_bytes = await request.body()
    body_json: dict = {}
    try:
        import json
        body_json = json.loads(body_bytes)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event = body_json.get("event", "")

    # ── Handle URL validation challenge (no signature needed for this) ─────────
    if event == "endpoint.url_validation":
        from app.services.zoom_service import handle_zoom_url_validation
        account_id = body_json.get("payload", {}).get("accountId") or body_json.get("account_id", "")
        webhook_secret = await _find_webhook_secret(account_id, db)
        if not webhook_secret:
            raise HTTPException(status_code=422, detail="No Zoom webhook secret configured")
        return handle_zoom_url_validation(body_json, webhook_secret)

    # ── All other events: verify signature ────────────────────────────────────
    if not x_zm_signature or not x_zm_request_timestamp:
        raise HTTPException(status_code=400, detail="Missing Zoom signature headers")

    # Identify tenant by account_id in the payload
    account_id = (
        body_json.get("payload", {}).get("account_id")
        or body_json.get("account_id", "")
    )
    webhook_secret = await _find_webhook_secret(account_id, db)
    if not webhook_secret:
        log.warning("zoom_webhook_no_secret", account_id=account_id)
        raise HTTPException(status_code=403, detail="Zoom not configured for this account")

    from app.services.zoom_service import verify_zoom_webhook
    if not verify_zoom_webhook(
        body_bytes=body_bytes,
        timestamp=x_zm_request_timestamp,
        signature=x_zm_signature,
        webhook_secret=webhook_secret,
    ):
        log.warning("zoom_webhook_invalid_signature", event=event)
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    # ── Dispatch events ───────────────────────────────────────────────────────
    log.info("zoom_webhook_received", event=event)

    if event == "meeting.ended":
        await _handle_meeting_ended(body_json, db)
    elif event == "recording.completed":
        await _handle_recording_completed(body_json, db)
    else:
        log.debug("zoom_webhook_unhandled_event", event=event)

    return {"ok": True}


# ── Webhook helpers ───────────────────────────────────────────────────────────

async def _find_webhook_secret(account_id: str, db: AsyncSession) -> Optional[str]:
    """
    Find the Zoom webhook secret for a given Zoom account_id.
    For multi-tenant: query tenant where config->zoom_account_id = account_id.
    Falls back to first tenant with Zoom enabled if account_id not provided.
    """
    from app.config import settings
    from app.services.zoom_service import get_zoom_webhook_secret

    enc_key = settings.video_encryption_key or settings.secret_key

    if account_id:
        from sqlalchemy import text
        r = await db.execute(
            text("SELECT config FROM tenants WHERE config->>'zoom_account_id' = :aid AND config->>'zoom_enabled' = 'true' LIMIT 1"),
            {"aid": account_id}
        )
        row = r.fetchone()
        if row and row[0]:
            try:
                return get_zoom_webhook_secret(row[0], enc_key)
            except Exception:
                return None

    # Fallback: first tenant with Zoom enabled
    from sqlalchemy import text
    r = await db.execute(
        text("SELECT config FROM tenants WHERE config->>'zoom_enabled' = 'true' AND config->>'zoom_webhook_secret' IS NOT NULL LIMIT 1")
    )
    row = r.fetchone()
    if row and row[0]:
        try:
            return get_zoom_webhook_secret(row[0], enc_key)
        except Exception:
            return None

    return None


async def _handle_meeting_ended(body: dict, db: AsyncSession) -> None:
    """
    meeting.ended webhook — update session status to ENDED and queue imports.
    """
    payload = body.get("payload", {})
    obj = payload.get("object", {})
    meeting_id = str(obj.get("id", ""))
    meeting_uuid = obj.get("uuid", "")

    if not meeting_id:
        return

    r = await db.execute(
        select(LiveClassSession).where(
            LiveClassSession.external_meeting_id == meeting_id
        )
    )
    cls = r.scalar_one_or_none()
    if not cls:
        log.warning("zoom_webhook_session_not_found", meeting_id=meeting_id)
        return

    from datetime import datetime, timezone
    cls.status = LiveClassStatus.ENDED
    if obj.get("start_time"):
        try:
            cls.actual_start_at = datetime.fromisoformat(
                obj["start_time"].replace("Z", "+00:00")
            )
        except Exception:
            pass
    cls.actual_end_at = datetime.now(timezone.utc)

    if meeting_uuid:
        cls.external_meeting_uuid = meeting_uuid

    await db.commit()

    from app.tasks.live_class_tasks import import_attendance_report
    if cls.import_attendance:
        import_attendance_report.delay(str(cls.id))

    log.info("zoom_meeting_ended_processed",
             session_id=str(cls.id), meeting_id=meeting_id)


async def _handle_recording_completed(body: dict, db: AsyncSession) -> None:
    """
    recording.completed webhook — recording is ready in Zoom cloud.
    Queue recording import task.
    """
    payload = body.get("payload", {})
    obj = payload.get("object", {})
    meeting_id = str(obj.get("id", ""))

    if not meeting_id:
        return

    r = await db.execute(
        select(LiveClassSession).where(
            LiveClassSession.external_meeting_id == meeting_id
        )
    )
    cls = r.scalar_one_or_none()
    if not cls:
        log.warning("zoom_recording_session_not_found", meeting_id=meeting_id)
        return

    if cls.import_recording:
        from app.tasks.live_class_tasks import import_live_recording
        import_live_recording.delay(str(cls.id))
        log.info("zoom_recording_import_queued",
                 session_id=str(cls.id), meeting_id=meeting_id)
