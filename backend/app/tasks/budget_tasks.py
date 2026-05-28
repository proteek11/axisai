"""
Celery tasks for token budget management.

reset_monthly_token_budgets
    Scheduled by Celery Beat to run at 00:05 on the 1st of each month.
    Zeroes tokens_used_this_month for every user in user_token_budgets.
    The 5-minute offset avoids midnight contention with other scheduled tasks.

warn_high_usage_users
    Scheduled to run daily. Logs (and in future could email) users who have
    consumed > 80% of their monthly token budget — gives admins early warning
    before users hit the wall mid-month.
"""
import asyncio
import logging

import structlog
from celery import shared_task

log = structlog.get_logger(__name__)


@shared_task(
    name="app.tasks.budget_tasks.reset_monthly_token_budgets",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def reset_monthly_token_budgets(self):
    """
    Monthly reset: set tokens_used_this_month = 0 for all users.
    Scheduled for 00:05 on day 1 of every month (see celery_app.py beat_schedule).
    """
    async def _run():
        from app.core.database import AsyncSessionLocal
        from app.services.token_budget_service import reset_all_monthly_usage
        async with AsyncSessionLocal() as db:
            count = await reset_all_monthly_usage(db)
        return count

    try:
        count = asyncio.get_event_loop().run_until_complete(_run())
        log.info("monthly_token_budget_reset_complete", users_reset=count)
        return {"status": "ok", "users_reset": count}
    except Exception as exc:
        log.error("monthly_token_budget_reset_failed", error=str(exc))
        raise self.retry(exc=exc)


@shared_task(
    name="app.tasks.budget_tasks.warn_high_usage_users",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
)
def warn_high_usage_users(self):
    """
    Daily check: log users at > 80% of their monthly budget.
    Future: trigger email notification via SendGrid/SES.
    """
    async def _run():
        from sqlalchemy import select
        from app.core.database import AsyncSessionLocal
        from app.models.user import AxisUser
        from app.services.token_budget_service import get_budget_status

        warnings = []
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(AxisUser).where(AxisUser.is_active == True))
            users = result.scalars().all()
            for user in users:
                try:
                    status = await get_budget_status(db, user)
                    if status.pct_used >= 0.80:
                        warnings.append({
                            "user_id": str(user.id),
                            "email": user.email,
                            "used": status.used,
                            "limit": status.limit,
                            "pct_used": round(status.pct_used * 100, 1),
                        })
                except Exception:
                    pass
        return warnings

    try:
        warnings = asyncio.get_event_loop().run_until_complete(_run())
        if warnings:
            log.warning(
                "token_budget_high_usage_users",
                count=len(warnings),
                users=[w["email"] for w in warnings],
            )
        else:
            log.info("token_budget_daily_check_ok", high_usage_count=0)
        return {"status": "ok", "high_usage_count": len(warnings), "users": warnings}
    except Exception as exc:
        log.error("token_budget_warn_task_failed", error=str(exc))
        raise self.retry(exc=exc)
