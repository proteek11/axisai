"""
Celery tasks for Live Class (Zoom) integration.

Tasks:
  import_live_recording    — Download MP4 → run AI pipeline → create content_item
  import_attendance_report — Fetch Zoom participant list → save to live_class_attendance
  notify_live_class        — Email + in-app notification to space learners
  poll_pending_sessions    — Beat task: poll Zoom for sessions whose webhook was missed

All async logic follows the same pattern as process_content.py:
  create a fresh engine+session inside asyncio.run() to avoid event-loop mismatch.
"""
import asyncio
import os
import tempfile
import uuid
from datetime import datetime, timezone

from celery import shared_task
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# ── Shared engine factory (fresh per task) ────────────────────────────────────

def _make_session_factory():
    """Create a fresh async engine + session factory for this task's event loop.
    Uses NullPool to avoid greenlet/event-loop conflicts in Celery tasks.
    """
    from sqlalchemy.ext.asyncio import (
        create_async_engine, async_sessionmaker, AsyncSession
    )
    from sqlalchemy.pool import NullPool
    from app.config import settings

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,  # No pooling — fresh connection per task, avoids asyncpg greenlet errors
    )
    return async_sessionmaker(
        engine, class_=AsyncSession,
        expire_on_commit=False, autocommit=False, autoflush=False,
    ), engine


# ── Task 1: Import live recording ─────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.tasks.live_class_tasks.import_live_recording",
    max_retries=3,
    default_retry_delay=120,
    acks_late=True,
)
def import_live_recording(self, session_id: str) -> dict:
    """
    Download the Zoom cloud recording MP4 and run it through the AI pipeline.
    Creates a content_item in the space with type 'video' and runs
    summary + quiz + flashcards outputs (if generate_ai_outputs=True).
    """
    async def _run():
        session_factory, engine = _make_session_factory()
        try:
            return await _do_import_recording(session_id, session_factory)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"import_live_recording failed session={session_id}: {exc}")
        raise self.retry(exc=exc)


async def _do_import_recording(session_id: str, session_factory) -> dict:
    from sqlalchemy import select, update
    from app.models.live_class import LiveClassSession, LiveClassStatus
    from app.models.tenant import Tenant
    from app.config import settings
    from app.services.zoom_service import zoom_service_from_config, decrypt_secret

    async with session_factory() as db:
        # 1. Load session
        r = await db.execute(
            select(LiveClassSession).where(LiveClassSession.id == uuid.UUID(session_id))
        )
        cls = r.scalar_one_or_none()
        if not cls:
            logger.error(f"import_live_recording: session {session_id} not found")
            return {"error": "session not found"}

        if not cls.import_recording:
            logger.info(f"import_recording=False, skipping", session_id=session_id)
            return {"skipped": "import_recording disabled"}

        # 2. Load tenant config
        r2 = await db.execute(select(Tenant).where(Tenant.id == cls.tenant_id))
        tenant = r2.scalar_one_or_none()
        if not tenant:
            return {"error": "tenant not found"}

        enc_key = settings.video_encryption_key or settings.secret_key

        try:
            zoom = zoom_service_from_config(tenant.config, enc_key)
        except ValueError as e:
            await _mark_failed(db, cls, str(e))
            return {"error": str(e)}

        # 3. Get recording from Zoom (retry a few times — may not be ready immediately)
        meeting_uuid = cls.external_meeting_uuid or cls.external_meeting_id
        if not meeting_uuid:
            await _mark_failed(db, cls, "No meeting UUID/ID to fetch recording")
            return {"error": "no meeting uuid"}

        recording_data = await zoom.get_recording(meeting_uuid)
        if not recording_data:
            await _mark_failed(db, cls, "Recording not available in Zoom")
            return {"error": "recording not available"}

        # Find the MP4 file (Zoom returns multiple file types)
        mp4_file = None
        access_token = await zoom._get_token()
        for f in recording_data.get("recording_files", []):
            if f.get("file_type") == "MP4" and f.get("status") == "completed":
                mp4_file = f
                break

        if not mp4_file:
            await _mark_failed(db, cls, "No completed MP4 recording found")
            return {"error": "no mp4 file"}

        # 4. Download MP4 to local storage
        recording_dir = os.path.join(settings.upload_dir, "live_recordings")
        os.makedirs(recording_dir, exist_ok=True)
        local_path = os.path.join(recording_dir, f"{session_id}.mp4")

        download_url = mp4_file.get("download_url")
        await zoom.download_recording_mp4(download_url, access_token, local_path)
        duration_sec = mp4_file.get("recording_end") and mp4_file.get("recording_start") and None  # calculated below

        # 5. Create a ContentItem for the recording
        from app.models.content import ContentItem, ContentType, ContentStatus
        import hashlib

        file_hash = hashlib.sha256(f"zoom_recording_{session_id}".encode()).hexdigest()
        content_item = ContentItem(
            tenant_id=cls.tenant_id,
            content_type=ContentType.VIDEO,
            title=f"[Recording] {cls.title}",
            source_url=local_path,          # local path — extractor reads from disk
            content_hash=file_hash,
            status=ContentStatus.QUEUED,
        )
        db.add(content_item)
        await db.flush()  # get content_item.id

        # 6. Link recording to session
        cls.content_item_id = content_item.id
        cls.recording_local_path = local_path
        cls.status = LiveClassStatus.IMPORTED

        await db.commit()
        await db.refresh(cls)

        # 7. Queue AI pipeline if enabled
        if cls.generate_ai_outputs:
            from app.models.job import ProcessingJob, JobType, JobStatus
            from app.tasks.process_content import run_pipeline

            job = ProcessingJob(
                tenant_id=cls.tenant_id,
                content_item_id=content_item.id,
                job_type=JobType.FULL_PIPELINE,
                status=JobStatus.QUEUED,
                config={"tasks": ["summary", "quiz", "flashcards", "glossary"]},
            )
            db.add(job)
            await db.commit()
            await db.refresh(job)

            run_pipeline.delay(
                job_id=str(job.id),
                content_item_id=str(content_item.id),
                tenant_id=str(cls.tenant_id),
                job_config={"tasks": ["summary", "quiz", "flashcards", "glossary"]},
            )
            logger.info(f"AI pipeline queued for recording", job_id=str(job.id))

        # 8. Link content_item to space
        from app.models.space import SpaceItem
        space_item = SpaceItem(
            space_id=cls.space_id,
            content_item_id=content_item.id,
            title=f"[Recording] {cls.title}",
            position=9999,  # append at end
        )
        db.add(space_item)
        await db.commit()

        logger.info(f"Recording imported", session_id=session_id,
                    content_item_id=str(content_item.id))

        # Notify learners that recording is ready (queued after this returns)
        if cls.notify_learners:
            notify_live_class.delay(session_id, "recording_ready")

        return {"ok": True, "content_item_id": str(content_item.id)}


async def _mark_failed(db, cls, error: str):
    from app.models.live_class import LiveClassStatus
    cls.status = LiveClassStatus.FAILED
    cls.import_error = error
    await db.commit()


# ── Task 2: Import attendance report ─────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.tasks.live_class_tasks.import_attendance_report",
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def import_attendance_report(self, session_id: str) -> dict:
    """Fetch Zoom participant report and save to live_class_attendance."""
    async def _run():
        session_factory, engine = _make_session_factory()
        try:
            return await _do_import_attendance(session_id, session_factory)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"import_attendance_report failed session={session_id}: {exc}")
        raise self.retry(exc=exc)


async def _do_import_attendance(session_id: str, session_factory) -> dict:
    from sqlalchemy import select, delete as sa_delete
    from app.models.live_class import LiveClassSession, LiveClassAttendance
    from app.models.tenant import Tenant
    from app.config import settings
    from app.services.zoom_service import zoom_service_from_config

    async with session_factory() as db:
        r = await db.execute(
            select(LiveClassSession).where(LiveClassSession.id == uuid.UUID(session_id))
        )
        cls = r.scalar_one_or_none()
        if not cls or not cls.import_attendance:
            return {"skipped": "no session or import_attendance=False"}

        r2 = await db.execute(select(Tenant).where(Tenant.id == cls.tenant_id))
        tenant = r2.scalar_one_or_none()
        if not tenant:
            return {"error": "tenant not found"}

        enc_key = settings.video_encryption_key or settings.secret_key

        try:
            zoom = zoom_service_from_config(tenant.config, enc_key)
        except ValueError as e:
            return {"error": str(e)}

        meeting_id = cls.external_meeting_id
        if not meeting_id:
            return {"error": "no meeting_id"}

        participants = await zoom.get_participants(meeting_id)

        # Delete any old attendance records first (idempotent)
        await db.execute(
            sa_delete(LiveClassAttendance).where(
                LiveClassAttendance.session_id == cls.id
            )
        )

        # Insert fresh records
        for p in participants:
            def _parse_dt(s):
                if not s:
                    return None
                try:
                    return datetime.fromisoformat(s.replace("Z", "+00:00"))
                except Exception:
                    return None

            row = LiveClassAttendance(
                session_id=cls.id,
                participant_id=p.get("id"),
                user_id=p.get("user_id"),
                user_email=p.get("user_email"),
                user_name=p.get("name"),
                joined_at=_parse_dt(p.get("join_time")),
                left_at=_parse_dt(p.get("leave_time")),
                duration_seconds=p.get("duration"),
                attentiveness_score=p.get("attentiveness_score"),
                raw_data=p,
            )
            db.add(row)

        cls.participant_count = len(participants)
        await db.commit()

        logger.info(f"Attendance imported", session_id=session_id, count=len(participants))
        return {"ok": True, "participants": len(participants)}


# ── Task 3: Notify learners ───────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="app.tasks.live_class_tasks.notify_live_class",
    max_retries=2,
    default_retry_delay=30,
)
def notify_live_class(self, session_id: str, event: str) -> dict:
    """
    Send email + in-app notification to all space learners.
    event: 'scheduled' | 'updated' | 'cancelled' | 'recording_ready'
    """
    async def _run():
        session_factory, engine = _make_session_factory()
        try:
            return await _do_notify(session_id, event, session_factory)
        finally:
            await engine.dispose()

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"notify_live_class failed: {exc}")
        raise self.retry(exc=exc)


async def _do_notify(session_id: str, event: str, session_factory) -> dict:
    from sqlalchemy import select
    from app.models.live_class import LiveClassSession
    from app.models.space import LearningSpace, SpaceAccess
    from app.models.user import AxisUser
    from app.services.email import send_email
    from app.config import settings

    async with session_factory() as db:
        r = await db.execute(
            select(LiveClassSession).where(LiveClassSession.id == uuid.UUID(session_id))
        )
        cls = r.scalar_one_or_none()
        if not cls or not cls.notify_learners:
            return {"skipped": True}

        # Get all learners with access to this space
        r2 = await db.execute(
            select(AxisUser).join(
                SpaceAccess, SpaceAccess.user_id == AxisUser.id
            ).where(SpaceAccess.space_id == cls.space_id)
        )
        learners = r2.scalars().all()

        if not learners:
            return {"ok": True, "sent": 0}

        # Build email content per event
        if event == "scheduled":
            subject = f"📅 Live Class Scheduled: {cls.title}"
            body_lines = [
                f"A live class has been scheduled in your learning space.",
                f"",
                f"Title: {cls.title}",
                f"When: {cls.scheduled_at.strftime('%d %b %Y, %H:%M')} UTC",
                f"Duration: {cls.duration_minutes} minutes",
                f"",
                f"Join link: {cls.join_url or 'Will be available soon'}",
                f"Password: {cls.password or 'None'}",
            ]
        elif event == "cancelled":
            subject = f"❌ Live Class Cancelled: {cls.title}"
            body_lines = [
                f"The live class '{cls.title}' scheduled for "
                f"{cls.scheduled_at.strftime('%d %b %Y, %H:%M')} UTC has been cancelled.",
            ]
        elif event == "recording_ready":
            subject = f"🎥 Recording Ready: {cls.title}"
            body_lines = [
                f"The recording for '{cls.title}' is now available in your learning space.",
                f"AI-generated summary, quiz, and flashcards have been created from the recording.",
                f"",
                f"Log in to your learning space to access it.",
            ]
        else:
            subject = f"📣 Live Class Update: {cls.title}"
            body_lines = [f"Your live class '{cls.title}' has been updated."]

        body = "\n".join(body_lines)

        # Read SMTP config from DB
        smtp_config = None
        try:
            from sqlalchemy import text
            r3 = await db.execute(text(
                "SELECT config FROM platform_settings WHERE key='email' LIMIT 1"
            ))
            row = r3.fetchone()
            if row:
                smtp_config = row[0]
        except Exception:
            pass

        sent = 0
        for learner in learners:
            try:
                if smtp_config and smtp_config.get("smtp_host"):
                    await send_email(
                        to_email=learner.email,
                        to_name=learner.full_name or learner.email,
                        subject=subject,
                        body=body,
                        config=smtp_config,
                    )
                    sent += 1
            except Exception as e:
                logger.warning(f"notify_live_class email failed to {learner.email}: {e}")

        logger.info(f"Live class notifications sent",
                    session_id=session_id, event=event, sent=sent)
        return {"ok": True, "sent": sent}


# ── Task 4: Poll pending sessions (beat — fallback if webhook missed) ─────────

@shared_task(name="app.tasks.live_class_tasks.poll_pending_sessions")
def poll_pending_sessions() -> dict:
    """
    Beat task: check for sessions that ended >30 min ago but are still status='ended'
    (webhook may have been missed). Triggers import tasks for them.
    Runs every 15 minutes via beat schedule.
    """
    async def _run():
        session_factory, engine = _make_session_factory()
        try:
            return await _do_poll(session_factory)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


async def _do_poll(session_factory) -> dict:
    from sqlalchemy import select
    from datetime import timedelta
    from app.models.live_class import LiveClassSession, LiveClassStatus

    async with session_factory() as db:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        r = await db.execute(
            select(LiveClassSession).where(
                LiveClassSession.status == LiveClassStatus.ENDED,
                LiveClassSession.updated_at < cutoff,
            )
        )
        stale = r.scalars().all()

        triggered = 0
        for cls in stale:
            logger.info(f"Polling missed webhook for session", session_id=str(cls.id))
            if cls.import_recording:
                import_live_recording.delay(str(cls.id))
            if cls.import_attendance:
                import_attendance_report.delay(str(cls.id))
            triggered += 1

        return {"checked": len(stale), "triggered": triggered}
