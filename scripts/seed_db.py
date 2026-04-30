#!/usr/bin/env python
"""Seed the database with a dev organisation and starter prompts.

Usage:
    python scripts/seed_db.py
    python scripts/seed_db.py --dry-run
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "apps" / "api"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from sqlalchemy import text

from db.session import AsyncSessionLocal

DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEV_ORG_NAME = "Vikas Dev Org"
DEV_ORG_SLUG = "vikas-dev"


async def seed_org(dry_run: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            text("SELECT id FROM organizations WHERE id = :id"),
            {"id": DEV_ORG_ID},
        )
        if row.fetchone():
            print(f"  SKIP  organizations — dev org {DEV_ORG_ID!r} already exists")
            return

        if dry_run:
            print(f"  DRY   organizations — would insert dev org {DEV_ORG_ID!r}")
            return

        await db.execute(
            text(
                "INSERT INTO organizations (id, name, slug, settings, created_at, updated_at) "
                "VALUES (:id, :name, :slug, '{}', now(), now())"
            ),
            {"id": DEV_ORG_ID, "name": DEV_ORG_NAME, "slug": DEV_ORG_SLUG},
        )
        await db.commit()
        print(f"  SEED  organizations — inserted dev org {DEV_ORG_ID!r} ({DEV_ORG_NAME!r})")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("Dry run — no changes will be made.\n")
    asyncio.run(seed_org(dry_run=dry_run))
    print("Done.")
