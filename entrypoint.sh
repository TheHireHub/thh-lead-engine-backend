#!/bin/bash
set -e

# ---------------------------------------------------------------------------
# THH Lead Engine — container entrypoint.
#
# Responsibilities (in order):
#   1. Wait for MySQL to accept TCP connections (up to MYSQL_WAIT_TIMEOUT s).
#   2. Optionally apply Alembic migrations (gated by RUN_MIGRATIONS=1).
#   3. Hand off to the CMD (gunicorn, arq worker, etc.).
#
# Env knobs:
#   MYSQL_HOST              default: localhost
#   MYSQL_PORT              default: 3306
#   MYSQL_WAIT_TIMEOUT      default: 60     seconds before bailing
#   RUN_MIGRATIONS          default: 0      set to 1 to run "alembic upgrade head"
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
    echo "[entrypoint] running alembic upgrade head..."
    alembic upgrade head
    echo "[entrypoint] migrations done"
fi

exec "$@"
