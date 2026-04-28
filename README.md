# THH Lead Engine — Backend

Outbound growth / prospect-conversion system for The HireHub.

**Stack**: FastAPI · SQLAlchemy 2.0 (async) · MySQL · ARQ · Redis · Alembic

**Schema source of truth**: [`docs/SCHEMA.md`](./docs/SCHEMA.md)

**Architecture rules**: see [CLAUDE.md](./CLAUDE.md).

## Quick start

```bash
# one-shot bootstrap (Git Bash / WSL / macOS / Linux)
./bootstrap.sh

# Windows cmd.exe
bootstrap.cmd
```

This creates `.venv`, installs deps, copies `env.example` → `.env`
(prompts you to edit it), creates the DB + tables, stamps Alembic, and
smoke-imports `app.py`. Re-run safely — every step is idempotent.

Then run the API:
```bash
source .venv/Scripts/activate    # or .venv/bin/activate on macOS/Linux
uvicorn app:app --reload --port 5050
```

Manual install (if you'd rather skip the script):
```bash
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
cp env.example .env       # then edit MySQL creds + REDIS_URL
python setup_database.py
uvicorn app:app --reload --port 5050
```

API docs: http://localhost:5050/docs

## Project structure

```
app.py                              ← FastAPI entrypoint
database_connection/connection.py   ← async engine + Base + get_db
services/<domain>/                  ← models · schemas · enums · crud · routes
workers/                            ← ARQ tasks (apollo, snapshot, heat, activation)
setup_database.py                   ← bootstrap DB + create_all
alembic/                            ← migrations
```

Each `services/<domain>/` is self-contained: domain models, Pydantic
schemas, TINYINT enum maps, async CRUD, FastAPI router. Route → CRUD
→ DB. No raw SQL. No DB calls outside CRUD.

## Domains (one folder each in `services/`)

| Domain | Tables | Schema doc |
|---|---|---|
| `admin_users` | admin_users | §7.1 |
| `companies` | companies | §7.2 |
| `prospects` | prospects + channels + stage_history + merge_log + merge_review_queue | §7.3-7.5, §7.19, §7.20 |
| `campaigns` | campaigns + campaign_prospects + campaign_events | §7.6-7.8 |
| `landing_pages` | landing_pages + variants + visits | §7.9-7.11 |
| `signups` | signups | §7.12 |
| `email_replies` | email_replies | §7.13 |
| `unsubscribes` | unsubscribes | §7.14 |
| `prospect_notes` | prospect_notes | §7.15 |
| `audit` | audit_log | §7.16 |
| `funnel_snapshots` | funnel_daily_snapshots | §7.17 |
| `webhooks` | webhook_deliveries | §7.18 |
| `prospect_company_jobs` | jobs + candidates + history + boards | §7.21-7.24 |
| `call_logs` | call_logs | §7.25 |

## Five touch points with thh-backend (§9)

1. Promote prospect to THH lead (manual button)
2. Pre-import dedupe check (Apollo sync)
3. Send OTP (landing-page signup)
4. Verify OTP (landing-page signup)
5. Activation status sync (daily worker)

## Migrations (Alembic)

```bash
alembic revision --autogenerate -m "add foo_column"
alembic upgrade head
alembic downgrade -1
```

## Workers

```bash
arq workers.settings.WorkerSettings
```

Tasks (stubs, fill in as you implement):
- `apollo_sync` (every 6h)
- `funnel_snapshot` (daily)
- `heat_recalc` (hourly)
- `activation_sync` (daily, calls thh-backend §9.5)
