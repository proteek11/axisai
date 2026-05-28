"""
Health check endpoints.
/health  — basic liveness (is the process running?)
/health/ready — readiness (can we serve traffic? all dependencies up?)
"""
# FIX 2026-03-28: Removed ORJSONResponse usage.
# Error: FastAPIDeprecationWarning — ORJSONResponse is deprecated. FastAPI now
# serialises response data directly to JSON bytes via Pydantic, making a custom
# response class unnecessary and slower.
# Fix: Replaced ORJSONResponse return types and response_class decorators with
# plain dict returns. The /health/ready endpoint now uses a JSONResponse for the
# 503 case (non-200 status with a body), which is the standard FastAPI pattern.
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import get_db
from app.core.qdrant import health_check as qdrant_health
from app.core.redis import get_redis

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health() -> dict:
    """Liveness probe — if this returns 200, the process is alive."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "env": settings.env,
    }


@router.get("/health/ready")
async def readiness(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Readiness probe — checks all critical dependencies.
    Returns 200 if ready, 503 if any dependency is down.
    """
    checks: dict[str, dict] = {}
    all_ok = True

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    try:
        await db.execute(text("SELECT 1"))
        checks["postgres"] = {"status": "ok"}
    except Exception as e:
        checks["postgres"] = {"status": "error", "message": str(e)}
        all_ok = False

    # ── Redis ──────────────────────────────────────────────────────────────
    try:
        redis = await get_redis()
        await redis.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        checks["redis"] = {"status": "error", "message": str(e)}
        all_ok = False

    # ── Qdrant ────────────────────────────────────────────────────────────
    try:
        qdrant_info = await qdrant_health()
        checks["qdrant"] = {
            "status": "ok",
            "collections": len(qdrant_info.get("collections", [])),
        }
    except Exception as e:
        checks["qdrant"] = {"status": "error", "message": str(e)}
        all_ok = False

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_ok else "not_ready",
            "checks": checks,
        },
    )
