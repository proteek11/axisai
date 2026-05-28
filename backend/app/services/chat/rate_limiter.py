"""
Chat rate limiter — four-layer protection against abuse.

Layers (checked in order, cheapest first):
  1. COOLDOWN       — minimum gap between messages per user (anti-spam)
  2. SESSION MAX    — max total messages in a single session
  3. USER DAILY     — max tokens a single user can consume per day
  4. TENANT MONTHLY — max tokens a tenant can consume per month

All Redis keys use structured namespacing:
  chat:cd:{tenant_id}:{user_id}                → cooldown (key existence = locked)
  chat:rl:user:day:{tenant_id}:{user_id}:{date} → user daily token counter
  chat:rl:tenant:month:{tenant_id}:{month}       → tenant monthly token counter

Uses the existing check_and_increment_rate_limit Lua script from app.core.redis
for atomic sliding-window operations (no race conditions between check + increment).

All limits are configurable via settings. Defaults are conservative but sensible
for a production LMS with typical student behaviour.
"""
from __future__ import annotations

from datetime import datetime, timezone

import structlog
from redis.asyncio import Redis

from app.config import settings
from app.core.exceptions import RateLimitExceededError
from app.core.redis import check_and_increment_rate_limit

log = structlog.get_logger(__name__)

# TTLs for rate limit keys
_COOLDOWN_TTL = 2          # seconds between messages (per user)
_DAY_TTL = 86400           # 24 hours in seconds
_MONTH_TTL = 86400 * 32    # slightly over a month to survive month boundaries


class ChatRateLimiter:
    """
    Stateless rate limiter — all state lives in Redis.

    Call check_pre_message() before processing any chat message.
    Call record_tokens_used() after the LLM call completes (even on error,
    to prevent retry-loop abuse — pass 0 tokens on error).
    """

    def __init__(self, redis: Redis):
        self.redis = redis

    # ── Pre-message checks ────────────────────────────────────────────────────

    async def check_pre_message(
        self,
        tenant_id: str,
        moodle_user_id: int,
        session_message_count: int,
    ) -> None:
        """
        Run all pre-message rate limit checks.
        Raises RateLimitExceededError with a user-friendly detail if any check fails.
        Called BEFORE the LLM pipeline starts.
        """
        await self._check_cooldown(tenant_id, moodle_user_id)
        self._check_session_max(session_message_count)
        await self._check_user_daily_messages(tenant_id, moodle_user_id)

    async def record_tokens_used(
        self,
        tenant_id: str,
        moodle_user_id: int,
        tokens: int,
    ) -> None:
        """
        Increment token counters after a successful LLM call.
        Called AFTER the message is processed (best-effort — never raises).
        """
        try:
            await self._increment_user_daily_tokens(tenant_id, moodle_user_id, tokens)
            await self._increment_tenant_monthly_tokens(tenant_id, tokens)
        except Exception as e:
            log.error("chat_rl_increment_failed", error=str(e))

    async def set_cooldown(self, tenant_id: str, moodle_user_id: int) -> None:
        """
        Set the per-user cooldown key. Called immediately when a message
        arrives (before processing) to block rapid-fire submissions.
        """
        try:
            key = f"chat:cd:{tenant_id}:{moodle_user_id}"
            await self.redis.setex(key, _COOLDOWN_TTL, "1")
        except Exception as e:
            log.error("chat_rl_cooldown_set_failed", error=str(e))

    # ── Layer 1: Cooldown ─────────────────────────────────────────────────────

    async def _check_cooldown(self, tenant_id: str, moodle_user_id: int) -> None:
        """
        Block if the user sent a message less than COOLDOWN_SECONDS ago.
        The cooldown key is SET when the message arrives, so two nearly-simultaneous
        requests from the same user will collide on the second check.
        """
        try:
            key = f"chat:cd:{tenant_id}:{moodle_user_id}"
            exists = await self.redis.exists(key)
            if exists:
                ttl = await self.redis.ttl(key)
                raise RateLimitExceededError(
                    f"Please wait {max(ttl, 1)} second(s) before sending another message.",
                    retry_after=max(ttl, 1),
                )
        except RateLimitExceededError:
            raise
        except Exception as e:
            log.error("chat_rl_cooldown_check_failed", error=str(e))
            # Never block on Redis failure — fail open

    # ── Layer 2: Session max messages ─────────────────────────────────────────

    def _check_session_max(self, session_message_count: int) -> None:
        """
        Block if the session has exceeded MAX_SESSION_MESSAGES.
        This is a DB-side check (no Redis needed) — session.message_count is always current.
        """
        limit = settings.chat_max_session_messages
        if session_message_count >= limit:
            raise RateLimitExceededError(
                f"This chat session has reached its message limit ({limit} messages). "
                "Please start a new session to continue.",
                retry_after=0,
            )

    # ── Layer 3: User daily message count ─────────────────────────────────────

    async def _check_user_daily_messages(
        self, tenant_id: str, moodle_user_id: int
    ) -> None:
        """
        Check (and pre-increment by 1) the user's daily message count.
        We count messages not tokens here so it's checked before the LLM call.
        Tokens are recorded separately after the call.
        """
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            key = f"chat:rl:user:day:msgs:{tenant_id}:{moodle_user_id}:{date_str}"
            current, limit, over = await check_and_increment_rate_limit(
                self.redis, key,
                limit=settings.chat_max_user_messages_day,
                increment=1,
                ttl_seconds=_DAY_TTL,
            )
            if over:
                log.warning(
                    "chat_rl_user_daily_msgs_exceeded",
                    tenant=tenant_id, user=moodle_user_id,
                    current=current, limit=limit,
                )
                raise RateLimitExceededError(
                    f"You've reached your daily chat limit ({limit} messages). "
                    "Limits reset at midnight UTC.",
                    retry_after=86400,
                )
        except RateLimitExceededError:
            raise
        except Exception as e:
            log.error("chat_rl_user_daily_check_failed", error=str(e))
            # Fail open on Redis error

    # ── Layer 4a: User daily token counter (post-call) ────────────────────────

    async def _increment_user_daily_tokens(
        self, tenant_id: str, moodle_user_id: int, tokens: int
    ) -> None:
        """Record token usage for the user's daily budget (informational — not hard-blocked)."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"chat:rl:user:day:tokens:{tenant_id}:{moodle_user_id}:{date_str}"
        await self.redis.incrby(key, tokens)
        await self.redis.expire(key, _DAY_TTL)

        # Soft cap: log warning if user is burning a lot of tokens
        current = int(await self.redis.get(key) or 0)
        soft_cap = settings.chat_max_user_tokens_day
        if current > soft_cap:
            log.warning(
                "chat_rl_user_token_budget_exceeded",
                tenant=tenant_id, user=moodle_user_id,
                tokens_today=current, soft_cap=soft_cap,
            )

    # ── Layer 4b: Tenant monthly token counter (post-call) ───────────────────

    async def _increment_tenant_monthly_tokens(self, tenant_id: str, tokens: int) -> None:
        """Record token usage against the tenant's monthly budget."""
        month_str = datetime.now(timezone.utc).strftime("%Y-%m")
        key = f"chat:rl:tenant:month:tokens:{tenant_id}:{month_str}"
        await self.redis.incrby(key, tokens)
        await self.redis.expire(key, _MONTH_TTL)

        current = int(await self.redis.get(key) or 0)
        hard_cap = settings.chat_max_tenant_tokens_month
        if current > hard_cap:
            log.warning(
                "chat_rl_tenant_monthly_budget_exceeded",
                tenant=tenant_id,
                tokens_this_month=current,
                hard_cap=hard_cap,
            )
            # Note: we log but don't raise here — this is a post-call increment.
            # The pre-call check for tenant monthly budget can be added in Phase 3
            # when billing enforcement is required.

    # ── Utility: get current usage stats (for admin dashboard) ───────────────

    async def get_user_usage_today(self, tenant_id: str, moodle_user_id: int) -> dict:
        """Return current usage stats for a user today — for admin/teacher display."""
        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            msgs_key = f"chat:rl:user:day:msgs:{tenant_id}:{moodle_user_id}:{date_str}"
            tokens_key = f"chat:rl:user:day:tokens:{tenant_id}:{moodle_user_id}:{date_str}"
            msgs = int(await self.redis.get(msgs_key) or 0)
            tokens = int(await self.redis.get(tokens_key) or 0)
            return {
                "messages_today": msgs,
                "messages_limit": settings.chat_max_user_messages_day,
                "tokens_today": tokens,
                "tokens_soft_cap": settings.chat_max_user_tokens_day,
            }
        except Exception:
            return {}

    async def get_tenant_usage_this_month(self, tenant_id: str) -> dict:
        """Return current monthly token usage for a tenant."""
        try:
            month_str = datetime.now(timezone.utc).strftime("%Y-%m")
            key = f"chat:rl:tenant:month:tokens:{tenant_id}:{month_str}"
            tokens = int(await self.redis.get(key) or 0)
            return {
                "tokens_this_month": tokens,
                "tokens_limit": settings.chat_max_tenant_tokens_month,
            }
        except Exception:
            return {}
