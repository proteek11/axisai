#!/usr/bin/env python3
"""
backfill_cert_emails.py — one-shot migration script.

Updates cert_data JSONB for existing SpaceCertificate rows that have
an empty / missing learner_email field, pulling the email from axis_users.

Usage (from axis-ai/ with venv active):
    python scripts/backfill_cert_emails.py

Dry-run (no writes):
    python scripts/backfill_cert_emails.py --dry-run
"""
import asyncio
import sys
import argparse

async def main(dry_run: bool) -> None:
    import os
    from pathlib import Path
    import json

    # Load env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import text

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("❌ DATABASE_URL not set")
        sys.exit(1)

    engine = create_async_engine(db_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # Find certs where learner_email is missing or empty
        rows = (await db.execute(text("""
            SELECT sc.id, sc.user_id, sc.cert_data, u.email
            FROM space_certificates sc
            JOIN axis_users u ON u.id = sc.user_id
            WHERE (sc.cert_data->>'learner_email') IS NULL
               OR (sc.cert_data->>'learner_email') = ''
        """))).fetchall()

        print(f"Found {len(rows)} certificate(s) missing learner_email")

        if dry_run:
            for row in rows:
                print(f"  would update cert {row.id}: email → {row.email}")
            print("Dry-run complete — no changes written")
            return

        updated = 0
        for row in rows:
            cert_data = dict(row.cert_data or {})
            cert_data["learner_email"] = row.email or ""
            await db.execute(text("""
                UPDATE space_certificates
                SET cert_data = :data::jsonb
                WHERE id = :id
            """), {"data": json.dumps(cert_data), "id": str(row.id)})
            updated += 1

        await db.commit()
        print(f"✅ Updated {updated} certificate(s) with learner_email")

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args()
    asyncio.run(main(args.dry_run))
