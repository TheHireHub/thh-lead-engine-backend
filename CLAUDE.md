# THH Lead Engine — Backend Instructions

This is the **outbound growth / prospect-conversion** system. Separate
database, separate app, separate domain from `thh-backend`. Talks to
`thh-backend` over exactly five HTTP endpoints (Schema doc §9).

The single source of truth for schema and architecture is
[`docs/SCHEMA.md`](./docs/SCHEMA.md). Every section reference below
(`§3`, `§7.21`, `Arch-29`, etc.) maps into that doc.

## graphify knowledge graph (use this FIRST)

This repo ships with a knowledge graph at `graphify-out/` that maps every
backend route, handler, CRUD function, service, and model.

**Before answering any architecture, "where does X live", or "how does Y work"
question, check the graph. It is faster and more complete than grep.**

### Entry points

- `graphify-out/GRAPH_REPORT.md` — god nodes, community labels, executive summary
- `graphify-out/wiki/index.md` — agent-crawlable markdown articles, one per community
- `graphify-out/graph.html` — interactive browser visualization
- `graphify-out/graph.json` — raw graph (576 nodes · 1173 edges · 66 communities)

### Regenerating

After code changes run `/graphify /Users/lakshayjain/thh/thh-lead-engine-backend --update`
(AST re-extraction, no LLM cost for code-only changes).

## Stack

- **FastAPI** + **SQLAlchemy 2.0 (async)** + **MySQL** (aiomysql)
- **ARQ** (Redis-backed async task queue) for background jobs
- **Alembic** for migrations
- **Pydantic v2** for request/response validation

## Repo layout

```
thh-lead-engine-backend/
├── app.py                          ← FastAPI entrypoint, registers all routers
├── database_connection/
│   └── connection.py               ← async engine, Base, get_db dependency
├── services/                       ← one folder per domain
│   ├── common/                     ← shared envelope + cross-service enums (§6)
│   ├── admin_users/                ← §7.1
│   ├── companies/                  ← §7.2
│   ├── prospects/                  ← §7.3-7.5, §7.19, §7.20
│   ├── campaigns/                  ← §7.6-7.8
│   ├── landing_pages/              ← §7.9-7.11
│   ├── signups/                    ← §7.12
│   ├── email_replies/              ← §7.13
│   ├── unsubscribes/               ← §7.14
│   ├── prospect_notes/             ← §7.15
│   ├── audit/                      ← §7.16
│   ├── funnel_snapshots/           ← §7.17
│   ├── webhooks/                   ← §7.18
│   ├── prospect_company_jobs/      ← §7.21-7.24
│   └── call_logs/                  ← §7.25
├── workers/
│   ├── settings.py                 ← ARQ WorkerSettings
│   └── tasks/                      ← apollo_sync, funnel_snapshot, heat_recalc, activation_sync
├── alembic/                        ← migrations
├── setup_database.py               ← bootstraps DB + Base.metadata.create_all
├── requirements.txt
├── env.example
├── Dockerfile + docker-compose.yml + entrypoint.sh
└── CLAUDE.md  (this file)
```

Each `services/<domain>/` follows the same shape:

| File         | Purpose |
|--------------|---------|
| `models.py`  | SQLAlchemy 2.0 declarative models. **Only** subclasses `Base`. |
| `schemas.py` | Pydantic v2 request/response models. |
| `enums.py`   | TINYINT int↔label maps (re-exported from `services.common.enums`). |
| `crud.py`    | Async CRUD methods (the **only** layer with `AsyncSession`). |
| `routes.py`  | FastAPI `APIRouter` — orchestrates CRUD + services + integrations. |

Add a new service ⇒ create the folder, then register its router in `app.py`
and import its models in `setup_database.py::import_all_models()`.

## Architecture rules (Routes / CRUD / Services — adapted from thh-backend)

These are **authoritative** and supersede any conflicting guidance:

### Routes (`services/<domain>/routes.py`)

- Single entrypoint per HTTP request. All frontend / API requests must flow
  through routes.
- Validates input via Pydantic, authenticates / authorises, orchestrates.
- Calls **CRUD** for DB and **service helpers / integrations** for heavy work.
- Returns the standard envelope `{success, message, data, error}` (use
  `services.common.envelope.ok` / `fail`).
- **Routes MUST NOT** import `AsyncSession` to query the DB directly, run
  raw SQL, call external APIs inline, or contain business logic.

### CRUD (`services/<domain>/crud.py`)

- The **only** layer that takes an `AsyncSession`. Use the FastAPI `get_db`
  dependency in routes and pass the session through.
- Static methods on a CRUD class. Returns SQLAlchemy model instances or
  Pydantic dicts — never raw cursor rows.
- Handles its own transactions: commit on success, rollback on error
  (`get_db` auto-rolls back on uncaught exceptions).
- May import other CRUDs only when there is a true compositional reason
  (e.g. `call_logs.crud.CallLogCRUD.record` writes both a `call_logs`
  row and an `audit_log` row in the same transaction).

### Services / integrations (helper modules)

- DB-agnostic. Take data as arguments, never call CRUD or `AsyncSession`.
- Examples: `services/email_replies/classifier.py` (rule + LLM reply
  classification), `services/integrations/thh_backend.py` (HTTP wrapper
  for the five touch points), `services/integrations/calendly.py`,
  `services/integrations/apollo.py`.

### Workers (`workers/tasks/*.py`)

- ARQ task functions. Same orchestration rights as routes — they may call
  CRUD + services + integrations.
- Use `arq.cron` in `WorkerSettings.cron_jobs` to schedule.

## Enum policy (Arch-29)

**Every enumerated column is `TINYINT UNSIGNED NOT NULL`, never MySQL
`ENUM`.** The single source of truth is `services/common/enums.py` (§6).
Adding a new value = `INSERT` not `ALTER TABLE`.

Service-level `enums.py` files re-export only the maps they need plus
their `_REVERSE` companion. Routes attach `_label` fields to responses by
calling `get_label(MAP, int_value)`.

## Soft delete (Arch-19)

Every business entity has `deleted_at TIMESTAMP NULL`. Filter `deleted_at
IS NULL` in CRUD reads. Hard delete only via a future GDPR-erase
endpoint.

## Auth (Arch-23)

JWT in **httpOnly + Secure + SameSite=Lax** cookie. Never localStorage.
The auth implementation is deferred — for now route handlers take
`*_user_id` as a query param TODO; replace with a `current_user`
dependency once auth lands.

## THH integration touch points (§9 — exactly five)

| # | Direction | Purpose | Where |
|---|-----------|---------|-------|
| 1 | lead → thh | Promote prospect to a real THH lead | manual button on prospect detail |
| 2 | lead → thh | Pre-import dedupe check | `apollo_sync` worker |
| 3 | lead → thh | Send OTP for landing-page signup | `signups` route on form submit |
| 4 | lead → thh | Verify OTP | `signups` route after OTP entry |
| 5 | lead → thh | Activation status (jobs + applicants per converted prospect) | `activation_sync` worker, daily |

Outside these five calls, the systems do not talk. Lead engine survives
THH downtime.

## Running locally

```bash
# 1. install
python -m venv .venv && source .venv/Scripts/activate    # Windows: .\.venv\Scripts\activate
pip install -r requirements.txt

# 2. configure
cp env.example .env
# edit .env with MySQL creds + REDIS_URL + THH_BACKEND_BASE_URL

# 3. create the DB and tables
python setup_database.py

# 4. run the API
uvicorn app:app --reload --port 5050

# 5. run the worker (separate shell)
arq workers.settings.WorkerSettings
```

Alembic for schema changes after the first run:
```bash
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Pending user input (§14 — track here, fix as you go)

- **P3**: Posting Helper data source — local on `prospect_company_jobs`
  child tables OR live pull from thh-backend. Currently neither is
  implemented; the model has the shape but the route and child tables
  for the full message_formatter field set don't exist yet.
- **P5**: 3xRNR auto-marker mechanism — `call_logs.crud` writes the
  audit row, but doesn't yet move the prospect to a stage or set a
  milestone column. Decide which.
- **P4**: Cold → Curious auto-promotion on landing page visit insert.
  Not wired yet.
