"""
axis-ai FastAPI application entry point.

Startup sequence:
  1. Configure logging
  2. Connect to PostgreSQL (verify pool)
  3. Connect to Redis
  4. Connect to Qdrant + initialize collections
  5. Register routers, middleware, exception handlers

Any frontend (Moodle PHP plugin, Next.js, mobile) calls the same API.
Auth is via API key (Bearer token). All responses are JSON.
"""
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# FIX 2026-03-28: ORJSONResponse removed as default_response_class.
# Error: FastAPIDeprecationWarning — ORJSONResponse is deprecated as a default
# response class. FastAPI now serialises Pydantic models directly to JSON bytes,
# which is faster and requires no custom response class.
# Fix: Removed the import and default_response_class=ORJSONResponse from app
# instantiation. Explicit ORJSONResponse usages in individual endpoints are
# handled separately in their own files.

from app.api.v1.router import v1_router
from app.config import settings
from app.core.database import AsyncSessionFactory
from app.core.exceptions import register_exception_handlers
from app.core.qdrant import close_qdrant, initialize_collections
from app.core.redis import close_redis, get_redis
from app.utils.logging import configure_logging

log = structlog.get_logger("axis_ai.startup")


# FIX 2026-03-28: Master tenant seeding added.
# Error: asyncpg.exceptions.ForeignKeyViolationError — insert on "content_items"
# violates FK constraint "content_items_tenant_id_fkey". Key
# (tenant_id)=(00000000-0000-0000-0000-000000000000) not present in "tenants".
# Reason: _get_master_tenant() in security.py builds a synthetic in-memory
# Tenant object with a hardcoded UUID but never persists it. Any write that
# uses the master tenant as the FK owner fails because Postgres can't find
# that UUID in the tenants table.
# Fix: Added ensure_master_tenant() which upserts the master tenant row on
# startup (idempotent). The master key path is intentionally for dev/admin
# use only; in production, real tenant rows with real API keys should be used.
async def ensure_master_tenant() -> None:
    """
    Upsert the master tenant row so the master API key can create DB records.
    Idempotent — safe to call on every startup.
    """
    from sqlalchemy import select
    from app.models.tenant import Tenant

    master_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(Tenant).where(Tenant.id == master_id)
        )
        if result.scalar_one_or_none() is None:
            master_tenant = Tenant(
                id=master_id,
                name="master",
                moodle_url="internal",
                is_active=True,
                config={},
            )
            session.add(master_tenant)
            await session.commit()
            log.info("master_tenant_created")
        else:
            log.info("master_tenant_exists")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup and shutdown logic.
    FastAPI lifespan replaces the old @app.on_event("startup") pattern.
    """
    # ── STARTUP ───────────────────────────────────────────────────────────────
    configure_logging()
    log.info("axis_ai_starting", version=settings.app_version, env=settings.env)

    # Seed master tenant (see ensure_master_tenant docstring above)
    try:
        await ensure_master_tenant()
    except Exception as e:
        log.error("master_tenant_seed_failed", error=str(e))
        raise

    # Verify Redis connection
    try:
        redis = await get_redis()
        await redis.ping()
        log.info("redis_connected")
    except Exception as e:
        log.error("redis_connection_failed", error=str(e))
        raise

    # Initialize Qdrant collections (idempotent)
    try:
        await initialize_collections()
        log.info("qdrant_collections_initialized")
    except Exception as e:
        log.error("qdrant_init_failed", error=str(e))
        raise

    # Ensure upload directory exists
    import os
    os.makedirs(settings.upload_dir, exist_ok=True)
    if settings.video_enabled and settings.video_storage == "local":
        os.makedirs(settings.video_output_dir, exist_ok=True)

    # ── AI API key check (warn, don't block startup) ───────────────────────
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not openai_key and not anthropic_key:
        log.warning(
            "no_ai_api_key_configured",
            message="Neither OPENAI_API_KEY nor ANTHROPIC_API_KEY is set. "
                    "AI output generation (summary, quiz, flashcards, etc.) will FAIL. "
                    "Add the key to .env and restart axis-ai-worker.",
        )
    elif openai_key:
        log.info("ai_key_present", provider="openai", key_prefix=openai_key[:8] + "...")
    else:
        log.info("ai_key_present", provider="anthropic", key_prefix=anthropic_key[:8] + "...")

    log.info("axis_ai_ready", host="0.0.0.0", port=8000)

    yield  # ← Application runs here

    # ── SHUTDOWN ──────────────────────────────────────────────────────────────
    log.info("axis_ai_shutting_down")
    await close_redis()
    await close_qdrant()
    log.info("axis_ai_stopped")


# ── App instance ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="axis-ai",
    description=(
        "AI content intelligence engine for Moodle LMS. "
        "Processes course content (PDF, video, SCORM, H5P) and returns "
        "summaries, flashcards, quizzes, mindmaps, transcripts, and more."
    ),
    version=settings.app_version,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
    openapi_url="/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────────

# CORS — allow configured Moodle origins and any Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Processing-Time", "Retry-After"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """
    Attach a unique request ID to every request.
    Binds structlog context vars so all log lines in this request include request_id.
    Also measures and logs request duration.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    start_time = time.perf_counter()

    # Bind to structlog context (automatically included in all log lines)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Processing-Time"] = f"{duration_ms}ms"

    log.info(
        "http_request",
        status_code=response.status_code,
        duration_ms=duration_ms,
    )

    return response


# ── Exception handlers ─────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(v1_router)

# LTI 1.3 public endpoints (mounted at app root — no /api/v1 prefix)
from app.api.v1.lti import public_router as lti_public_router
app.include_router(lti_public_router)

# ── Video output static files (local storage only) ───────────────────────────
import os as _os
if settings.video_enabled and settings.video_storage == "local":
    _os.makedirs(settings.video_output_dir, exist_ok=True)
    app.mount(
        "/video-outputs",
        StaticFiles(directory=settings.video_output_dir),
        name="video_outputs",
    )


# ── Root redirect ─────────────────────────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root():
    return {"service": "axis-ai", "version": settings.app_version, "docs": "/docs"}
