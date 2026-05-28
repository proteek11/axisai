"""
Celery application — task queue for all background processing.

Queue strategy:
- default:  Standard processing jobs (full pipeline, generate outputs)
- priority: High-priority jobs (single output regeneration, chat pre-fetch)
- beat:     Scheduled maintenance tasks (cleanup, usage rollup)
"""
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready, worker_shutdown
from kombu import Exchange, Queue

from app.config import settings

# ── App ───────────────────────────────────────────────────────────────────────
celery_app = Celery(
    "axis_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "app.tasks.process_content",
        "app.tasks.generate_outputs",
        "app.tasks.process_kb",
        "app.tasks.maintenance",
        "app.tasks.render_video",
        "app.tasks.preview_video",
        "app.tasks.live_class_tasks",
        "app.tasks.skills_tasks",
    ],
)

# ── Configuration ─────────────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task behavior
    task_track_started=True,
    task_acks_late=True,         # Ack after completion, not before (safer)
    worker_prefetch_multiplier=1, # One task at a time per worker slot (long tasks)
    task_reject_on_worker_lost=True,  # Re-queue if worker dies

    # Result TTL
    result_expires=86400 * 3,    # Keep results for 3 days

    # Retry policy
    task_max_retries=3,
    task_default_retry_delay=60, # 60s between retries

    # Queues
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("priority", Exchange("priority"), routing_key="priority"),
        Queue("beat", Exchange("beat"), routing_key="beat"),
        Queue("video", Exchange("video"), routing_key="video"),
    ),
    task_default_queue="default",
    task_routes={
        "app.tasks.process_content.*": {"queue": "default"},
        "app.tasks.generate_outputs.*": {"queue": "default"},
        "app.tasks.process_kb.*": {"queue": "default"},
        "app.tasks.maintenance.*": {"queue": "beat"},
        "app.tasks.render_video.*": {"queue": "video"},
        "app.tasks.preview_video.*": {"queue": "video"},
        "app.tasks.live_class_tasks.*": {"queue": "default"},
        "app.tasks.skills_tasks.*": {"queue": "default"},
    },

    # Beat schedule (maintenance tasks)
    beat_schedule={
        "cleanup-stale-jobs": {
            "task": "app.tasks.maintenance.cleanup_stale_jobs",
            "schedule": 3600.0,  # Every hour
        },
        "aggregate-token-usage": {
            "task": "app.tasks.maintenance.aggregate_token_usage",
            "schedule": 300.0,   # Every 5 minutes
        },
        # Token budget: reset on 1st of each month at 00:05 server time
        "reset-monthly-token-budgets": {
            "task": "app.tasks.budget_tasks.reset_monthly_token_budgets",
            "schedule": crontab(day_of_month="1", hour=0, minute=5),
        },
        # Token budget: daily high-usage warning at 09:00 server time
        "warn-high-token-usage": {
            "task": "app.tasks.budget_tasks.warn_high_usage_users",
            "schedule": crontab(hour=9, minute=0),
        },
        # Phase 19B — Live Classes: poll for sessions with missed webhooks every 15 min
        "poll-pending-live-sessions": {
            "task": "app.tasks.live_class_tasks.poll_pending_sessions",
            "schedule": crontab(minute="*/15"),
        },
    },
)


@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """Log when worker is ready."""
    import structlog
    log = structlog.get_logger()
    log.info("axis_ai_worker_ready", queues=list(sender.app.amqp.queues.keys()) if hasattr(sender, "app") else ["unknown"])


@worker_shutdown.connect
def on_worker_shutdown(sender, **kwargs):
    """Cleanup on worker shutdown."""
    import structlog
    log = structlog.get_logger()
    log.info("axis_ai_worker_shutdown")
