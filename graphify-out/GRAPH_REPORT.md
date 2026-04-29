# Graph Report - /Users/lakshayjain/thh/thh-lead-engine-backend  (2026-04-29)

## Corpus Check
- Corpus is ~28,456 words - fits in a single context window. You may not need a graph.

## Summary
- 576 nodes · 1173 edges · 66 communities detected
- Extraction: 62% EXTRACTED · 38% INFERRED · 0% AMBIGUOUS · INFERRED: 446 edges (avg confidence: 0.63)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Models and Schemas|Models and Schemas]]
- [[_COMMUNITY_CRUD Method Surface|CRUD Method Surface]]
- [[_COMMUNITY_Routes and Docstrings|Routes and Docstrings]]
- [[_COMMUNITY_ORM Base and CRUD Classes|ORM Base and CRUD Classes]]
- [[_COMMUNITY_Auth Layer (JWT + Cookie)|Auth Layer (JWT + Cookie)]]
- [[_COMMUNITY_Audit and Call Logs|Audit and Call Logs]]
- [[_COMMUNITY_Auth Helper Functions|Auth Helper Functions]]
- [[_COMMUNITY_Landing Pages CRUD|Landing Pages CRUD]]
- [[_COMMUNITY_Cross-Cutting Concerns|Cross-Cutting Concerns]]
- [[_COMMUNITY_Jobs and Candidates CRUD|Jobs and Candidates CRUD]]
- [[_COMMUNITY_Enum Helpers|Enum Helpers]]
- [[_COMMUNITY_Worker Tasks (ARQ)|Worker Tasks (ARQ)]]
- [[_COMMUNITY_DB Bootstrap|DB Bootstrap]]
- [[_COMMUNITY_Audit Listing|Audit Listing]]
- [[_COMMUNITY_Unsubscribe Service|Unsubscribe Service]]
- [[_COMMUNITY_Architecture Documentation|Architecture Documentation]]
- [[_COMMUNITY_Job Distribution and At-Risk|Job Distribution and At-Risk]]
- [[_COMMUNITY_Alembic Migration Env|Alembic Migration Env]]
- [[_COMMUNITY_Response Envelope|Response Envelope]]
- [[_COMMUNITY_Initial Schema Migration|Initial Schema Migration]]
- [[_COMMUNITY_Admin Users Listing|Admin Users Listing]]
- [[_COMMUNITY_Signup OTP TODO|Signup OTP TODO]]
- [[_COMMUNITY_Webhook Definitions|Webhook Definitions]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]
- [[_COMMUNITY_Module Init|Module Init]]

## God Nodes (most connected - your core abstractions)
1. `FastAPI routes for companies (Schema doc §7.2).` - 70 edges
2. `ok()` - 56 edges
3. `_serialize()` - 46 edges
4. `Async CRUD for companies.` - 40 edges
5. `Base` - 36 edges
6. `create()` - 33 edges
7. `get_by_id()` - 27 edges
8. `record()` - 23 edges
9. `SQLAlchemy model for `companies` (Schema doc §7.2).` - 15 edges
10. `Pydantic schemas for companies.` - 14 edges

## Surprising Connections (you probably didn't know these)
- `Arch-19 Soft Delete Policy` --rationale_for--> `AdminUser model`  [INFERRED]
  CLAUDE.md → services/admin_users/models.py
- `unhandled_exception_handler()` --semantically_similar_to--> `services.common.envelope.ok / fail`  [INFERRED] [semantically similar]
  /Users/lakshayjain/thh/thh-lead-engine-backend/app.py → services/common/envelope.py
- `alembic _sync_url (pymysql for migrations)` --semantically_similar_to--> `_build_database_url()`  [INFERRED] [semantically similar]
  alembic/env.py → /Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py
- `requirements.txt Stack Pin` --shares_data_with--> `connection.engine (async aiomysql)`  [INFERRED]
  requirements.txt → database_connection/connection.py
- `requirements.txt Stack Pin` --shares_data_with--> `auth.encode_jwt`  [INFERRED]
  requirements.txt → services/admin_users/auth.py

## Hyperedges (group relationships)
- **Login Flow: routes + auth helpers + crud + audit** — admin_users_routes_login, admin_users_auth_verify_password, admin_users_auth_encode_jwt, admin_users_auth_set_auth_cookie, admin_users_crud_get_by_email, admin_users_crud_update_last_login, audit_crud_record [EXTRACTED 0.95]
- **Async DB Stack: Base + engine + session + get_db** — connection_base, connection_engine, connection_async_sessionlocal, connection_get_db [EXTRACTED 0.95]
- **JWT httpOnly Cookie Auth (Arch-23)** — claudemd_arch23_auth_jwt_cookie, admin_users_auth_encode_jwt, admin_users_auth_set_auth_cookie, admin_users_auth_cookie_name, admin_users_dependencies_get_current_user [EXTRACTED 0.90]
- **** — companies_routes, campaigns_routes, call_logs_routes, audit_routes [EXTRACTED 1.00]
- **** — call_logs_enums, campaigns_enums, companies_enums, common_enums [EXTRACTED 1.00]
- **** — companies_crud_companycrud, campaigns_crud_campaigncrud, call_logs_crud_calllogcrud [INFERRED 0.90]
- **Landing page triple (page+variant+visit)** — landing_page_model, landing_page_variant_model, landing_page_visit_model [EXTRACTED 1.00]
- **Job CRUD trio (job+candidate+history)** — job_crud_class, job_candidate_crud_class, job_history_crud_class [EXTRACTED 1.00]
- **Routes use ok envelope + get_db** — email_replies_routes, funnel_snapshots_routes, landing_pages_routes [INFERRED 0.85]
- **job posting cluster (job + candidates + boards)** — prospect_company_job_model, prospect_company_job_candidate_model, prospect_company_job_board_model [EXTRACTED 1.00]
- **atomic stage transition pattern (Arch funnel)** — prospect_model, prospect_stage_history_model, prospect_crud_change_stage [EXTRACTED 1.00]
- **OTP verify -> upsert prospect -> stage promote (§9.4)** — signup_route_otp_verify, thh_backend_otp_verify, prospect_model [INFERRED 0.75]
- **** — worker_settings, task_apollo_sync, task_heat_recalc, task_funnel_snapshot, task_activation_sync [EXTRACTED 1.00]
- **** — webhook_routes, webhook_crud, webhook_model [EXTRACTED 1.00]
- **** — setup_db, import_all_models, unsub_model, webhook_model [EXTRACTED 1.00]

## Communities

### Community 0 - "Models and Schemas"
Cohesion: 0.03
Nodes (74): admin_users (FK target), Base (declarative), campaigns (FK target), common.enums, envelope.ok, companies (FK target), CompanyCreate, CompanyOut (+66 more)

### Community 1 - "CRUD Method Surface"
Cohesion: 0.08
Nodes (57): create(), get_by_domain(), get_by_id(), list_all(), list_open_tasks_for_user(), soft_delete(), update(), ok() (+49 more)

### Community 2 - "Routes and Docstrings"
Cohesion: 0.07
Nodes (52): BaseModel, CompanyCRUD, ProspectNoteCRUD, FastAPI routes for companies (Schema doc §7.2)., TODO: integrate with thh-backend OTP send (Schema §9.3) — call thh-backend     P, Powers the "Jobs at Risk" CSM view., # TODO: replace `created_by_user_id` query param with current-user dep once auth, TODO: integrate with thh-backend OTP verify (Schema §9.4). On success:     - mar (+44 more)

### Community 3 - "ORM Base and CRUD Classes"
Cohesion: 0.08
Nodes (50): Base, Base, Single declarative base shared by every service's models.py.      Every model in, add_prospects(), AuditLogCRUD, CallLogCRUD, CampaignCRUD, CampaignEventCRUD (+42 more)

### Community 4 - "Auth Layer (JWT + Cookie)"
Cohesion: 0.04
Nodes (53): auth.clear_auth_cookie, AUTH_COOKIE_NAME constant, auth.decode_jwt, auth.encode_jwt, auth.hash_password (bcrypt), auth.set_auth_cookie, auth.verify_password, AdminUserCRUD (+45 more)

### Community 5 - "Audit and Call Logs"
Cohesion: 0.11
Nodes (26): audit/routes.py, AuditLogOut, CallLogCRUD, CallLogCRUD.record (3xRNR auto-marker), call_logs/enums.py, CallLog model, call_logs/routes.py, CallLogCreate (+18 more)

### Community 6 - "Auth Helper Functions"
Cohesion: 0.13
Nodes (22): clear_auth_cookie(), _cookie_secure(), decode_jwt(), encode_jwt(), hash_password(), _jwt_secret(), _jwt_ttl_hours(), Auth helpers for admin_users (Schema doc Arch-23, §7.1, §6.1).  DB-agnostic per (+14 more)

### Community 7 - "Landing Pages CRUD"
Cohesion: 0.17
Nodes (12): get_by_external_id(), LandingPageCRUD, LandingPageVariantCRUD, LandingPageVisitCRUD, record(), WebhookDeliveryCRUD, LandingPage, LandingPageVariant (+4 more)

### Community 8 - "Cross-Cutting Concerns"
Cohesion: 0.13
Nodes (19): CAN-SPAM/GDPR compliance, Heat scoring rules (cold/warm/hot), Webhook idempotency (HMAC + dedupe), THH touchpoint #2 (dedupe check), THH touchpoint #5 (activation status), import_all_models(), setup_database bootstrap, activation_sync task (+11 more)

### Community 9 - "Jobs and Candidates CRUD"
Cohesion: 0.25
Nodes (14): distribute(), JobCandidateCRUD, JobCRUD, JobHistoryCRUD, list_at_risk(), list_for_job(), Increment per-board applicant count + total_applicants. Apply Arch-41         on, status=open AND target_met_at IS NULL AND at_risk_at < NOW() (Arch-41). (+6 more)

### Community 10 - "Enum Helpers"
Cohesion: 0.12
Nodes (7): get_label(), get_value(), Company-relevant enums (§6.4)., Build a label -> int reverse map for any of the above., Lookup with safe default for unrecognised values., Reverse lookup; returns None if label not found., reverse()

### Community 11 - "Worker Tasks (ARQ)"
Cohesion: 0.13
Nodes (6): Daily activation status sync (Schema doc Arch-38, §9.5).  For every prospect wit, Apollo sync task (Schema doc Arch-12, §9.2).  Pull-based, every 6 hours. Upserts, Daily funnel snapshot task (Schema doc Arch-20, §7.17).  Aggregates today's pros, Heat score recalculation (Schema doc Arch-21).  Rule (default, tunable): - email, ARQ worker settings (Schema doc Arch-17).  Run with:  arq workers.settings.Worke, WorkerSettings

### Community 12 - "DB Bootstrap"
Cohesion: 0.36
Nodes (7): Alembic env.py target_metadata wiring, Initial Schema Baseline Migration 08085eaf24de, ensure_database_exists(), import_all_models(), main(), Import every services/<domain>/models.py module so SQLAlchemy registers     the, run()

### Community 13 - "Audit Listing"
Cohesion: 0.38
Nodes (4): list_for_actor(), list_for_entity(), for_actor(), for_entity()

### Community 14 - "Unsubscribe Service"
Cohesion: 0.38
Nodes (4): get_by_email(), is_unsubscribed(), UnsubscribeCRUD, check()

### Community 15 - "Architecture Documentation"
Cohesion: 0.33
Nodes (7): Routes/CRUD/Services Architecture Rules, Lead Engine Backend Overview, §14 Pending Inputs P3/P4/P5, §9 Five THH Backend Touch Points, Domain to Tables Mapping, README Quickstart, docs/SCHEMA.md (single source of truth)

### Community 16 - "Job Distribution and At-Risk"
Cohesion: 0.33
Nodes (6): At-Risk One-Way Ratchet (Arch-41), JobCandidateCRUD, JobCRUD, Post-a-Job Distribute (Arch-40), JobHistoryCRUD, ProspectCompanyJob (model)

### Community 17 - "Alembic Migration Env"
Cohesion: 0.4
Nodes (1): Alembic env for THH Lead Engine — async engine, autogenerate-aware.  `run_migrat

### Community 18 - "Response Envelope"
Cohesion: 0.4
Nodes (3): Envelope, Standard response envelope helpers for THH Lead Engine.  Every route returns `{s, Standard API response envelope.

### Community 19 - "Initial Schema Migration"
Cohesion: 0.5
Nodes (1): initial schema baseline  Revision ID: 08085eaf24de Revises:  Create Date: 2026-0

### Community 20 - "Admin Users Listing"
Cohesion: 1.0
Nodes (2): AdminUserCRUD.list_all, routes.list_users

### Community 21 - "Signup OTP TODO"
Cohesion: 1.0
Nodes (2): POST /signups (TODO OTP send), thh-backend POST /api/auth/login-otp/send

### Community 22 - "Webhook Definitions"
Cohesion: 1.0
Nodes (2): Webhook enums, Webhook schemas

### Community 23 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 24 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 25 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 27 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 35 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Module Init"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Module Init"
Cohesion: 1.0
Nodes (1): CORS middleware config

### Community 44 - "Module Init"
Cohesion: 1.0
Nodes (1): AuditLogCRUD

### Community 45 - "Module Init"
Cohesion: 1.0
Nodes (1): companies/schemas.py

### Community 46 - "Module Init"
Cohesion: 1.0
Nodes (1): email_replies/crud.py

### Community 47 - "Module Init"
Cohesion: 1.0
Nodes (1): email_replies/models.py

### Community 48 - "Module Init"
Cohesion: 1.0
Nodes (1): email_replies/schemas.py

### Community 49 - "Module Init"
Cohesion: 1.0
Nodes (1): funnel_snapshots/crud.py

### Community 50 - "Module Init"
Cohesion: 1.0
Nodes (1): funnel_snapshots/models.py

### Community 51 - "Module Init"
Cohesion: 1.0
Nodes (1): funnel_snapshots/schemas.py

### Community 52 - "Module Init"
Cohesion: 1.0
Nodes (1): landing_pages/crud.py

### Community 53 - "Module Init"
Cohesion: 1.0
Nodes (1): landing_pages/models.py

### Community 54 - "Module Init"
Cohesion: 1.0
Nodes (1): landing_pages/schemas.py

### Community 55 - "Module Init"
Cohesion: 1.0
Nodes (1): prospect_company_jobs/crud.py

### Community 56 - "Module Init"
Cohesion: 1.0
Nodes (1): JobCreate schema

### Community 57 - "Module Init"
Cohesion: 1.0
Nodes (1): JobUpdate schema

### Community 58 - "Module Init"
Cohesion: 1.0
Nodes (1): CandidateMatchCreate schema

### Community 59 - "Module Init"
Cohesion: 1.0
Nodes (1): NoteCreate schema

### Community 60 - "Module Init"
Cohesion: 1.0
Nodes (1): NoteUpdate schema

### Community 61 - "Module Init"
Cohesion: 1.0
Nodes (1): ProspectUpdate schema

### Community 62 - "Module Init"
Cohesion: 1.0
Nodes (1): ProspectOut schema

### Community 63 - "Module Init"
Cohesion: 1.0
Nodes (1): StageChange schema

### Community 64 - "Module Init"
Cohesion: 1.0
Nodes (1): SignupCreate schema

### Community 65 - "Module Init"
Cohesion: 1.0
Nodes (1): SignupOut schema

## Ambiguous Edges - Review These
- `CompanyCreate` → `LandingPageVariant`  [AMBIGUOUS]
  services/landing_pages/models.py · relation: semantically_similar_to

## Knowledge Gaps
- **118 isolated node(s):** `THH Lead Engine — FastAPI application entrypoint.  Mirrors the role of thh-backe`, `Run on startup / shutdown — wire up Sentry, warm caches, etc.`, `Async SQLAlchemy 2.0 connection module for THH Lead Engine.  Mirrors the role of`, `Build the async MySQL URL from environment variables.      Uses aiomysql driver.`, `Single declarative base shared by every service's models.py.      Every model in` (+113 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Admin Users Listing`** (2 nodes): `AdminUserCRUD.list_all`, `routes.list_users`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Signup OTP TODO`** (2 nodes): `POST /signups (TODO OTP send)`, `thh-backend POST /api/auth/login-otp/send`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Webhook Definitions`** (2 nodes): `Webhook enums`, `Webhook schemas`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `enums.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `CORS middleware config`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `AuditLogCRUD`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `companies/schemas.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `email_replies/crud.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `email_replies/models.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `email_replies/schemas.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `funnel_snapshots/crud.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `funnel_snapshots/models.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `funnel_snapshots/schemas.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `landing_pages/crud.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `landing_pages/models.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `landing_pages/schemas.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `prospect_company_jobs/crud.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `JobCreate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `JobUpdate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `CandidateMatchCreate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `NoteCreate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `NoteUpdate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `ProspectUpdate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `ProspectOut schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `StageChange schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `SignupCreate schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Module Init`** (1 nodes): `SignupOut schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `CompanyCreate` and `LandingPageVariant`?**
  _Edge tagged AMBIGUOUS (relation: semantically_similar_to) - confidence is low._
- **Why does `FastAPI routes for companies (Schema doc §7.2).` connect `Routes and Docstrings` to `CRUD Method Surface`, `ORM Base and CRUD Classes`, `Auth Helper Functions`, `Landing Pages CRUD`, `Jobs and Candidates CRUD`, `Audit Listing`, `Unsubscribe Service`?**
  _High betweenness centrality (0.147) - this node is a cross-community bridge._
- **Why does `Base` connect `ORM Base and CRUD Classes` to `Auth Layer (JWT + Cookie)`, `Auth Helper Functions`, `Landing Pages CRUD`, `Jobs and Candidates CRUD`, `DB Bootstrap`, `Alembic Migration Env`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `AdminUser` connect `Auth Helper Functions` to `CRUD Method Surface`, `Routes and Docstrings`, `ORM Base and CRUD Classes`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 56 inferred relationships involving `FastAPI routes for companies (Schema doc §7.2).` (e.g. with `CallLogCRUD` and `CallLogCreate`) actually correct?**
  _`FastAPI routes for companies (Schema doc §7.2).` has 56 INFERRED edges - model-reasoned connections that need verification._
- **Are the 55 inferred relationships involving `ok()` (e.g. with `list_for_prospect()` and `list_callbacks()`) actually correct?**
  _`ok()` has 55 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `Async CRUD for companies.` (e.g. with `AuditLogCRUD` and `Prospect`) actually correct?**
  _`Async CRUD for companies.` has 26 INFERRED edges - model-reasoned connections that need verification._