#!/usr/bin/env bash
# THH Lead Engine Backend — first-time bootstrap.
#
# Usage:  ./bootstrap.sh
#
# What it does:
#   1. Checks Python version (>= 3.12)
#   2. Creates .venv if missing and activates it
#   3. Installs requirements
#   4. Creates .env from env.example if missing (and prompts you to edit it)
#   5. Verifies MySQL is reachable with the .env credentials
#   6. Runs setup_database.py to create the DB + tables
#   7. Stamps Alembic at the head so future migrations work
#   8. Smoke-imports app.py to catch wiring bugs
#
# Re-run safely — every step is idempotent.

set -euo pipefail
cd "$(dirname "$0")"

color() { printf "\033[1;%sm%s\033[0m\n" "$1" "$2"; }
ok()   { color 32 "✓ $*"; }
warn() { color 33 "! $*"; }
die()  { color 31 "✗ $*"; exit 1; }
step() { color 36 "▸ $*"; }

# ----------------------------------------------------------------- 1. Python
step "checking python"
PY=${PYTHON:-python}
if ! command -v "$PY" >/dev/null 2>&1; then
  die "python not found on PATH (set \$PYTHON to override)"
fi
PY_VER=$("$PY" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')
PY_MAJ=${PY_VER%.*}
PY_MIN=${PY_VER#*.}
if [ "$PY_MAJ" -lt 3 ] || { [ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 11 ]; }; then
  die "python 3.11+ required, found $PY_VER"
fi
ok "python $PY_VER"

# ----------------------------------------------------------------- 2. venv
step "creating .venv (if missing)"
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv
  ok ".venv created"
else
  ok ".venv already exists"
fi

# Activate (handles Git Bash on Windows + POSIX shells)
if [ -f ".venv/Scripts/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
else
  die "could not find venv activator"
fi
ok "venv activated"

# ----------------------------------------------------------------- 3. deps
step "installing requirements (this may take a minute)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt
ok "dependencies installed"

# ----------------------------------------------------------------- 4. .env
step "checking .env"
if [ ! -f ".env" ]; then
  cp env.example .env
  warn ".env created from env.example — edit it now with real MySQL creds + secrets"
  warn "press ENTER once you've edited .env, or Ctrl+C to abort"
  read -r _
else
  ok ".env exists"
fi

# Source the env so subsequent steps see MYSQL_* etc.
set -a
# shellcheck disable=SC1091
source .env
set +a

# ----------------------------------------------------------------- 5. MySQL ping
step "verifying MySQL reachable at ${MYSQL_HOST:-localhost}:${MYSQL_PORT:-3306}"
python - <<'PY'
import os, sys
import pymysql
try:
    conn = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        connect_timeout=5,
    )
    conn.close()
except Exception as exc:
    print(f"MySQL connect failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
ok "MySQL reachable"

# ----------------------------------------------------------------- 6. setup DB
step "running setup_database.py (creates DB + tables)"
python setup_database.py
ok "schema applied"

# ----------------------------------------------------------------- 7. Alembic stamp
step "stamping Alembic at head"
if [ ! -d "alembic/versions" ] || [ -z "$(ls -A alembic/versions 2>/dev/null | grep -v .gitkeep || true)" ]; then
  warn "no Alembic revisions yet — generating an initial baseline"
  alembic revision --autogenerate -m "baseline" || warn "autogenerate skipped (likely no diff)"
fi
alembic stamp head
ok "Alembic ready"

# ----------------------------------------------------------------- 8. smoke import
step "smoke-importing app.py"
python -c "import app; print(f'  registered {len(app.app.routes)} routes')"
ok "app.py imports cleanly"

# -----------------------------------------------------------------------
echo
ok "Bootstrap complete."
cat <<'EOF'

Next steps:
  Activate the venv:
    source .venv/Scripts/activate    # Windows (Git Bash)
    source .venv/bin/activate        # macOS / Linux

  Run the API:
    uvicorn app:app --reload --port 5050

  Run the worker (separate shell):
    arq workers.settings.WorkerSettings

  Open the docs:
    http://localhost:5050/docs

EOF
