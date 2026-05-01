#!/bin/bash
set -e

# ---------------------------------------------------------------------------
# THH Lead Engine — container entrypoint.
#
# Responsibilities (in order):
#   1. Wait for MySQL to accept TCP connections (up to MYSQL_WAIT_TIMEOUT s).
#   2. Optionally bootstrap / migrate the schema (gated by RUN_MIGRATIONS=1):
#        - Fresh DB (admin_users table missing)  → setup_database.py
#                                                  + alembic stamp head
#        - Existing DB                           → alembic upgrade head
#      Reason: alembic baseline 08085eaf24de is intentionally empty; the
#      authoritative initial schema lives in `Base.metadata` and is created
#      by `setup_database.py`. Running `alembic upgrade head` against a
#      fresh DB therefore tries to ALTER tables that do not yet exist.
#   3. Hand off to the CMD (gunicorn, arq worker, etc.).
#
# Env knobs:
#   MYSQL_HOST              default: localhost
#   MYSQL_PORT              default: 3306
#   MYSQL_WAIT_TIMEOUT      default: 60     seconds before bailing
#   RUN_MIGRATIONS          default: 0      set to 1 to run schema bootstrap/upgrade
# ---------------------------------------------------------------------------

host="${MYSQL_HOST:-localhost}"
port="${MYSQL_PORT:-3306}"
timeout="${MYSQL_WAIT_TIMEOUT:-60}"

echo "[entrypoint] waiting for MySQL at ${host}:${port} (timeout ${timeout}s)..."
i=0
while ! (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; do
    i=$((i + 1))
    if [ "$i" -ge "$timeout" ]; then
        echo "[entrypoint] ERROR: MySQL not reachable at ${host}:${port} after ${timeout}s"
        exit 1
    fi
    sleep 1
done
echo "[entrypoint] MySQL up after ${i}s"

if [ "${RUN_MIGRATIONS:-0}" = "1" ]; then
    echo "[entrypoint] probing schema state..."
    has_admin_users=$(python - <<'PY'
import os, sys
import pymysql
try:
    conn = pymysql.connect(
        host=os.environ.get("MYSQL_HOST", "localhost"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"],
        charset="utf8mb4",
    )
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES LIKE 'admin_users'")
        print("1" if cur.fetchone() else "0")
    conn.close()
except Exception as exc:
    print(f"[entrypoint] schema probe failed: {exc}", file=sys.stderr)
    print("0")
PY
)

    if [ "$has_admin_users" = "1" ]; then
        echo "[entrypoint] existing schema detected — running alembic upgrade head"
        alembic upgrade head
    else
        echo "[entrypoint] fresh DB detected — creating tables from Base.metadata"
        # Skip setup_database.py because it tries CREATE DATABASE which a
        # least-privilege managed-MySQL user can't run. The database itself
        # is provisioned by Coolify / the DBA; we only own the tables.
        python - <<'PY'
import asyncio
from setup_database import import_all_models
import_all_models()
from database_connection.connection import Base, DATABASE_URL
from sqlalchemy.ext.asyncio import create_async_engine

async def run():
    engine = create_async_engine(DATABASE_URL, echo=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()

asyncio.run(run())
PY
        echo "[entrypoint] stamping alembic at head"
        alembic stamp head
    fi
    echo "[entrypoint] schema ready"
fi

exec "$@"
