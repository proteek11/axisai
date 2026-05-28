#!/usr/bin/env python3
"""
Seed a development tenant and API key into the database.

Usage (from project root):
    python scripts/seed_tenant.py
    python scripts/seed_tenant.py --name "My School" --url "https://moodle.example.com"
    python scripts/seed_tenant.py --reset   # Delete and recreate

The script prints the raw API key — copy it to your .env as AXIS_API_KEY or
pass it in the Authorization header:
    Authorization: Bearer axai_<key>

Run AFTER `docker compose up -d` and `alembic upgrade head`.
"""
import argparse
import asyncio
import sys
import os

# Make sure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, delete

from app.config import settings
from app.core.database import AsyncSessionFactory
from app.core.security import generate_api_key, hash_api_key
from app.models.tenant import ApiKey, Tenant


async def seed(
    tenant_name: str,
    moodle_url: str,
    key_name: str,
    reset: bool,
) -> None:
    async with AsyncSessionFactory() as db:
        # ── Handle reset ──────────────────────────────────────────────────
        if reset:
            result = await db.execute(
                select(Tenant).where(Tenant.moodle_url == moodle_url)
            )
            existing = result.scalar_one_or_none()
            if existing:
                await db.execute(
                    delete(ApiKey).where(ApiKey.tenant_id == existing.id)
                )
                await db.execute(
                    delete(Tenant).where(Tenant.id == existing.id)
                )
                await db.flush()
                print(f"[reset] Deleted existing tenant: {existing.name}")

        # ── Check for existing tenant ─────────────────────────────────────
        result = await db.execute(
            select(Tenant).where(Tenant.moodle_url == moodle_url)
        )
        tenant = result.scalar_one_or_none()

        if tenant:
            print(f"[exists] Tenant already exists: {tenant.name} ({tenant.id})")
        else:
            import uuid
            tenant = Tenant(
                id=uuid.uuid4(),
                name=tenant_name,
                moodle_url=moodle_url,
                is_active=True,
                config={
                    "max_file_size_mb": 50,
                    "allowed_content_types": [
                        "pdf", "youtube", "vimeo", "peertube",
                        "html_page", "zoom", "assignment"
                    ],
                    "default_tasks": ["summary", "flashcards", "quiz", "glossary"],
                },
            )
            db.add(tenant)
            await db.flush()
            print(f"[created] Tenant: {tenant.name} ({tenant.id})")

        # ── Generate API key ──────────────────────────────────────────────
        raw_key, key_hash = generate_api_key()

        # Check if a key with this name already exists
        result = await db.execute(
            select(ApiKey).where(
                ApiKey.tenant_id == tenant.id,
                ApiKey.name == key_name,
            )
        )
        existing_key = result.scalar_one_or_none()

        if existing_key and not reset:
            print(f"[exists] API key '{key_name}' already exists for this tenant.")
            print("         Use --reset to regenerate it.")
            await db.commit()
            return

        import uuid
        api_key = ApiKey(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name=key_name,
            key_hash=key_hash,
            scopes=["ingest", "content", "jobs", "chat"],
            is_active=True,
        )
        db.add(api_key)
        await db.commit()

        print()
        print("=" * 60)
        print("  DEV TENANT READY")
        print("=" * 60)
        print(f"  Tenant name : {tenant.name}")
        print(f"  Tenant ID   : {tenant.id}")
        print(f"  Moodle URL  : {tenant.moodle_url}")
        print(f"  Key name    : {key_name}")
        print(f"  Key ID      : {api_key.id}")
        print()
        print(f"  RAW API KEY (save this — shown only once!):")
        print(f"  {raw_key}")
        print()
        print("  Add to your .env:")
        print(f"  AXIS_DEV_API_KEY={raw_key}")
        print()
        print("  Use in requests:")
        print(f"  Authorization: Bearer {raw_key}")
        print("=" * 60)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a dev tenant and API key")
    parser.add_argument(
        "--name",
        default="Dev School",
        help="Tenant display name (default: 'Dev School')",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="Moodle URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--key-name",
        default="dev-key",
        help="API key label (default: 'dev-key')",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the tenant + key",
    )
    args = parser.parse_args()

    asyncio.run(
        seed(
            tenant_name=args.name,
            moodle_url=args.url,
            key_name=args.key_name,
            reset=args.reset,
        )
    )


if __name__ == "__main__":
    main()
