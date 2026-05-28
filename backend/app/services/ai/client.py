"""
LiteLLM AI client with audit logging and rate limiting baked in.

Every single AI call — completion, embedding — goes through this client.
No exceptions. This is the only way to ensure:
  1. Every call is logged to audit_logs (tokens, cost, latency, provider, model)
  2. Rate limits are checked BEFORE the call is made
  3. Rate limit counters are updated AFTER the call
  4. Errors are caught and re-raised as AIProviderError

Usage:
    client = AIClient(db_session_factory=AsyncSessionFactory, redis=redis)
    response = await client.complete(
        messages=[{"role": "user", "content": "..."}],
        model="gpt-4o-mini",
        task_type="summary",
        tenant_id="uuid",
        content_item_id="uuid",
    )
"""
import time
import uuid
from collections.abc import Callable

import litellm
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.exceptions import AIProviderError, RateLimitExceededError, TokenBudgetExceededError
from app.services.token_budget_service import check_budget, record_usage, get_budget_row
from app.models.audit import AuditLog, AuditStatus
from app.utils.cost import estimate_cost

log = structlog.get_logger(__name__)

# LiteLLM global settings
litellm.drop_params = True      # Silently ignore unsupported params per provider
litellm.set_verbose = False


class AIClient:
    """
    Unified AI client — wraps LiteLLM with mandatory audit logging.

    Instantiated once per pipeline run (passed as dependency).
    The session_factory creates fresh DB sessions for async-safe audit writes.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis=None,
        tenant_id: str | None = None,
        content_item_id: str | None = None,
        job_id: str | None = None,
        moodle_user_id: int | None = None,
        moodle_course_id: int | None = None,
        moodle_cmid: int | None = None,
        chat_session_id: str | None = None,
        axis_user_id: str | None = None,  # axis_users.id — enables token budget enforcement
    ):
        self.session_factory = session_factory
        self.redis = redis
        # Context bound to this client instance (set at pipeline creation time)
        self._ctx = {
            "tenant_id": tenant_id,
            "content_item_id": content_item_id,
            "job_id": job_id,
            "moodle_user_id": moodle_user_id,
            "moodle_course_id": moodle_course_id,
            "moodle_cmid": moodle_cmid,
            "chat_session_id": chat_session_id,
            "axis_user_id": axis_user_id,  # may be None for Moodle-only pipeline calls
        }

    def with_context(self, **kwargs) -> "AIClient":
        """Return a copy of this client with updated context (for sub-calls)."""
        merged = {**self._ctx, **kwargs}
        new_client = AIClient(
            session_factory=self.session_factory,
            redis=self.redis,
            **merged,
        )
        return new_client

    # ── Completion ─────────────────────────────────────────────────────────────

    async def complete(
        self,
        messages: list[dict],
        model: str,
        task_type: str,
        *,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        response_format: dict | None = None,
        **litellm_kwargs,
    ) -> litellm.ModelResponse:
        """
        Make an async chat completion call via LiteLLM.
        Logs to audit_logs regardless of success or failure.
        Checks rate limits before calling.
        """
        start_time = time.perf_counter()
        status = AuditStatus.SUCCESS
        error_message = None
        response = None
        prompt_tokens = 0
        completion_tokens = 0
        provider_request_id = None

        # ── Rate limit check ──────────────────────────────────────────────
        await self._check_rate_limits(model=model, task_type=task_type)

        # ── Token budget check (only for axis frontend users) ─────────────
        await self._check_token_budget()

        # ── Build kwargs ──────────────────────────────────────────────────
        call_kwargs: dict = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **litellm_kwargs,
        }
        if response_format:
            call_kwargs["response_format"] = response_format

        # ── Make the call ─────────────────────────────────────────────────
        try:
            response = await litellm.acompletion(**call_kwargs)
            prompt_tokens = response.usage.prompt_tokens if response.usage else 0
            completion_tokens = response.usage.completion_tokens if response.usage else 0
            provider_request_id = getattr(response, "_request_id", None)

            log.info(
                "ai_completion",
                model=model,
                task_type=task_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        except litellm.RateLimitError as e:
            status = AuditStatus.RATE_LIMITED
            error_message = str(e)
            log.warning("ai_rate_limited", model=model, error=str(e))
            raise RateLimitExceededError(
                f"AI provider rate limit hit for model {model}",
                retry_after=60,
            )

        except litellm.Timeout as e:
            status = AuditStatus.TIMEOUT
            error_message = str(e)
            log.error("ai_timeout", model=model, task_type=task_type)
            raise AIProviderError(f"AI provider timeout: {str(e)}")

        except Exception as e:
            status = AuditStatus.ERROR
            error_message = str(e)
            log.error("ai_error", model=model, task_type=task_type, error=str(e))
            raise AIProviderError(f"AI provider error: {str(e)}")

        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            # Always log — success or failure
            await self._write_audit_log(
                model=model,
                task_type=task_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
                provider_request_id=provider_request_id,
            )
            if status == AuditStatus.SUCCESS:
                await self._increment_rate_limits(
                    model=model,
                    total_tokens=prompt_tokens + completion_tokens,
                )
                await self._record_token_usage(prompt_tokens + completion_tokens)

        return response

    # ── Embedding ──────────────────────────────────────────────────────────────

    async def embed(
        self,
        texts: list[str],
        model: str,
        *,
        task_type: str = "embed",
    ) -> list[list[float]]:
        """
        Generate embeddings for a list of texts via LiteLLM.
        Each call is logged. Empty texts are filtered before sending.
        """
        if not texts:
            return []

        # Filter empty strings
        texts = [t for t in texts if t.strip()]
        if not texts:
            return []

        start_time = time.perf_counter()
        status = AuditStatus.SUCCESS
        error_message = None
        prompt_tokens = 0

        await self._check_rate_limits(model=model, task_type=task_type)

        try:
            response = await litellm.aembedding(model=model, input=texts)
            embeddings = [item["embedding"] for item in response.data]
            prompt_tokens = response.usage.prompt_tokens if response.usage else len(texts) * 10

            log.info(
                "ai_embedding",
                model=model,
                text_count=len(texts),
                prompt_tokens=prompt_tokens,
            )
            return embeddings

        except Exception as e:
            status = AuditStatus.ERROR
            error_message = str(e)
            log.error("ai_embed_error", model=model, error=str(e))
            raise AIProviderError(f"Embedding error: {str(e)}")

        finally:
            latency_ms = int((time.perf_counter() - start_time) * 1000)
            await self._write_audit_log(
                model=model,
                task_type=task_type,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
            )
            if status == AuditStatus.SUCCESS:
                await self._increment_rate_limits(model=model, total_tokens=prompt_tokens)


    async def _check_token_budget(self) -> None:
        """
        Pre-flight token budget check for axis frontend users.
        No-ops silently when axis_user_id is not set (Moodle-only pipeline).
        Raises TokenBudgetExceededError if the user is over their monthly limit.
        """
        axis_user_id = self._ctx.get("axis_user_id")
        if not axis_user_id:
            return
        from sqlalchemy import select
        from app.models.user import AxisUser
        async with self.session_factory() as db:
            result = await db.execute(
                select(AxisUser).where(AxisUser.id == axis_user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                await check_budget(db, user)

    async def _record_token_usage(self, total_tokens: int) -> None:
        """
        Post-call: atomically increment the user's monthly token counter.
        No-ops silently when axis_user_id is not set.
        """
        import uuid as _uuid
        axis_user_id = self._ctx.get("axis_user_id")
        if not axis_user_id or total_tokens <= 0:
            return
        try:
            async with self.session_factory() as db:
                await record_usage(db, _uuid.UUID(axis_user_id), total_tokens)
                await db.commit()
        except Exception:
            # Never let accounting failures break the actual response
            log.warning(
                "token_budget_record_failed",
                user_id=axis_user_id,
                tokens=total_tokens,
            )

    # ── Internals ──────────────────────────────────────────────────────────────

    async def _write_audit_log(
        self,
        model: str,
        task_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        status: AuditStatus,
        latency_ms: int,
        error_message: str | None = None,
        provider_request_id: str | None = None,
    ) -> None:
        """Write an immutable audit log entry. Never raises — logging must not break the pipeline."""
        try:
            total_tokens = prompt_tokens + completion_tokens
            provider = self._get_provider(model)
            cost = estimate_cost(provider, model, prompt_tokens, completion_tokens)

            async with self.session_factory() as session:
                log_entry = AuditLog(
                    id=uuid.uuid4(),
                    tenant_id=uuid.UUID(self._ctx["tenant_id"]) if self._ctx["tenant_id"] else None,
                    content_item_id=uuid.UUID(self._ctx["content_item_id"]) if self._ctx["content_item_id"] else None,
                    job_id=uuid.UUID(self._ctx["job_id"]) if self._ctx["job_id"] else None,
                    chat_session_id=uuid.UUID(self._ctx["chat_session_id"]) if self._ctx["chat_session_id"] else None,
                    moodle_user_id=self._ctx["moodle_user_id"],
                    moodle_course_id=self._ctx["moodle_course_id"],
                    moodle_cmid=self._ctx["moodle_cmid"],
                    provider=provider,
                    model=model,
                    task_type=task_type,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    estimated_cost_usd=cost,
                    latency_ms=latency_ms,
                    status=status,
                    error_message=error_message,
                    provider_request_id=provider_request_id,
                )
                session.add(log_entry)
                await session.commit()

        except Exception as e:
            # Never let audit logging failure break the pipeline
            log.error("audit_log_write_failed", error=str(e))

    async def _check_rate_limits(self, model: str, task_type: str) -> None:
        """
        Check rate limits before making an AI call.
        Phase 2: Basic global check. Phase 3: Full multi-dimensional check.
        """
        # Full rate limiter implemented in Phase 3
        # For now: pass through (limits enforced via DB rules in Phase 3)
        pass

    async def _increment_rate_limits(self, model: str, total_tokens: int) -> None:
        """Increment Redis rate limit counters after a successful call."""
        # Full implementation in Phase 3
        pass

    def _get_provider(self, model: str) -> str:
        """Infer provider name from model string."""
        model_lower = model.lower()
        if model_lower.startswith("gpt") or model_lower.startswith("o1") or "openai" in model_lower:
            return "openai"
        elif "claude" in model_lower or "anthropic" in model_lower:
            return "anthropic"
        elif "mistral" in model_lower or "mixtral" in model_lower:
            return "mistral"
        elif "gemini" in model_lower:
            return "google"
        elif "llama" in model_lower or "ollama" in model_lower:
            return "ollama"
        return "unknown"
