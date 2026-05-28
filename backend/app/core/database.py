"""
Async SQLAlchemy engine and session factory.
Uses connection pooling suitable for production load.
"""
from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_pre_ping=True,  # Verify connections before use (handles DB restarts)
    pool_recycle=1800,   # Recycle connections every 30 min to prevent stale state
)

# ── Pool reset event: ensure asyncpg connections are fully clean on return ────
# Fixes: "cannot use Connection.transaction() in a manually started transaction"
# which occurs when an endpoint calls db.commit() explicitly (double-commit with
# get_db), leaving asyncpg's internal _top_xact in a dirty state on the pooled
# connection. The synchronous reset event force-clears _top_xact before the
# connection is returned to the pool.
@event.listens_for(engine.sync_engine, "reset")
def _reset_on_return(dbapi_connection, connection_record, reset_state):
    """Ensure every connection returned to pool has clean transaction state."""
    if reset_state.terminate_only:
        return
    try:
        raw = getattr(dbapi_connection, "_connection", None)
        if raw is not None and getattr(raw, "_top_xact", None) is not None:
            raw._top_xact = None
    except Exception:
        pass  # Best-effort — pool will discard the connection anyway

# ── Session factory ────────────────────────────────────────────────────────────
AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit (async-safe)
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an async DB session, commits on success,
    rolls back on exception, always closes.

    Usage:
        async def my_endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """Create all tables (dev/test only — use Alembic for production)."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_all_tables() -> None:
    """Drop all tables (test teardown only)."""
    from app.models import Base
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
