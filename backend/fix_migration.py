#!/usr/bin/env python3
"""
fix_migration.py — Run from inside axis-ai/ with the venv active.

Drops the half-created assessment tables, resets alembic to revision 024,
then runs upgrade head to cleanly apply 025 + 026.

Usage:
    cd /home/axisai/axisai-backend/axis-ai
    source .venv/bin/activate
    python fix_migration.py
"""

import asyncio
import os
import re
import subprocess
import sys
from pathlib import Path


def load_env(env_path: str = ".env") -> dict[str, str]:
    """Parse .env file into a dict (no external deps needed)."""
    env: dict[str, str] = {}
    p = Path(env_path)
    if not p.exists():
        print(f"[warn] {env_path} not found — using environment variables only")
        return env
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        # Strip optional surrounding quotes
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


def asyncpg_url(database_url: str) -> str:
    """Convert SQLAlchemy asyncpg URL to plain asyncpg DSN."""
    return re.sub(r"^postgresql\+asyncpg://", "postgresql://", database_url)


async def drop_tables(dsn: str) -> None:
    try:
        import asyncpg
    except ImportError:
        print("[error] asyncpg not found — is the venv active?")
        sys.exit(1)

    print(f"[db] Connecting to {re.sub(r':([^:@]+)@', ':***@', dsn)}")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DROP TABLE IF EXISTS assessment_attempts CASCADE;")
        print("[db] Dropped assessment_attempts (if existed)")
        await conn.execute("DROP TABLE IF EXISTS assessments CASCADE;")
        print("[db] Dropped assessments (if existed)")
    finally:
        await conn.close()


def run(cmd: list[str]) -> None:
    print(f"[run] {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"[error] Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main() -> None:
    # Load .env
    env_vars = load_env(".env")
    database_url = (
        env_vars.get("DATABASE_URL")
        or env_vars.get("database_url")
        or os.environ.get("DATABASE_URL")
        or "postgresql+asyncpg://axis:axisdev@localhost:5432/axis_ai"
    )
    print(f"[cfg] DATABASE_URL prefix: {database_url[:40]}…")

    dsn = asyncpg_url(database_url)

    # Step 1: Drop broken tables
    print("\n=== Step 1: Drop half-created tables ===")
    asyncio.run(drop_tables(dsn))

    # Step 2: Stamp alembic back to 024
    print("\n=== Step 2: Reset alembic version to 024 ===")
    run(["alembic", "stamp", "024"])

    # Step 3: Run migrations
    print("\n=== Step 3: Run alembic upgrade head ===")
    run(["alembic", "upgrade", "head"])

    # Step 4: Show current revision
    print("\n=== Step 4: Verify ===")
    run(["alembic", "current"])

    print("\n✓ Done — restart services:")
    print("  sudo systemctl restart axis-ai axis-ai-worker axis-ai-beat")


if __name__ == "__main__":
    main()
