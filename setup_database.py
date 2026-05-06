#!/usr/bin/env python3
"""
THH Lead Engine — self-contained database bootstrap.

Mirrors the role of `setup_database.py` in thh-backend: creates the database
if missing, then creates every table from `Base.metadata`. Safe to run
repeatedly (uses CREATE DATABASE IF NOT EXISTS + create_all which skips
existing tables).

Usage:
    python setup_database.py            # default: thh_lead_engine on localhost
    python setup_database.py --drop     # DROP all tables before recreating

Reads MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DB from .env.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

import pymysql
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("setup_database")


def ensure_database_exists() -> str:
    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "")
    db_name = os.getenv("MYSQL_DB", "thh_lead_engine")

    conn = pymysql.connect(
        host=host, port=port, user=user, password=password, charset="utf8mb4"
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        conn.commit()
        logger.info("database '%s' ready on %s:%s", db_name, host, port)
    finally:
        conn.close()
    return db_name


def import_all_models() -> None:
    """
    Import every services/<domain>/models.py module so SQLAlchemy registers
    the tables on `Base.metadata`. Adding a new service requires adding it
    here.
    """
    # noqa: F401 — imports are for side-effect registration on Base.metadata
    from services.admin_users import models as _admin_users  # noqa: F401
    from services.audit import models as _audit  # noqa: F401
    from services.call_logs import models as _call_logs  # noqa: F401
    from services.candidate_outreach import models as _candidate_outreach  # noqa: F401
    from services.campaigns import models as _campaigns  # noqa: F401
    from services.companies import models as _companies  # noqa: F401
    from services.email_replies import models as _email_replies  # noqa: F401
    from services.funnel_snapshots import models as _funnel  # noqa: F401
    from services.landing_pages import models as _landing  # noqa: F401
    from services.prospect_company_jobs import models as _jobs  # noqa: F401
    from services.prospect_notes import models as _notes  # noqa: F401
    from services.prospects import models as _prospects  # noqa: F401
    from services.signups import models as _signups  # noqa: F401
    from services.unsubscribes import models as _unsubs  # noqa: F401
    from services.webhooks import models as _webhooks  # noqa: F401


async def run(drop: bool) -> int:
    load_dotenv()
    ensure_database_exists()

    # Import models AFTER env is loaded — connection.py reads env on import.
    import_all_models()
    from database_connection.connection import Base, DATABASE_URL

    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        async with engine.begin() as conn:
            if drop:
                logger.warning("--drop set: dropping all tables")
                await conn.run_sync(Base.metadata.drop_all)
            logger.info("creating tables (%d total)", len(Base.metadata.tables))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("done.")
        return 0
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="THH Lead Engine DB bootstrap")
    parser.add_argument("--drop", action="store_true", help="drop all tables before creating")
    args = parser.parse_args()
    return asyncio.run(run(drop=args.drop))


if __name__ == "__main__":
    raise SystemExit(main())
