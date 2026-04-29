# Dev A — Backend Lane Instructions

**Owner of:** sourcing, outreach, prospects, campaigns, replies, unsubscribes, notes, admin auth.

> Schema doc references like `§7.3`, `§6.2`, `Arch-12` map into [`SCHEMA.md`](./SCHEMA.md). When in doubt, the schema doc is the source of truth.

---

## 1. Your scope

### Service modules (7)
| Folder | Tables | Schema § |
|---|---|---|
| `services/admin_users/` | `admin_users` | §7.1 |
| `services/companies/` | `companies` | §7.2 |
| `services/prospects/` | `prospects`, `prospect_channels`, `prospect_stage_history`, `prospect_merge_log`, `prospect_merge_review_queue` | §7.3, 7.4, 7.5, 7.19, 7.20 |
| `services/campaigns/` | `campaigns`, `campaign_prospects`, `campaign_events` | §7.6, 7.7, 7.8 |
| `services/email_replies/` | `email_replies` | §7.13 |
| `services/unsubscribes/` | `unsubscribes` | §7.14 |
| `services/prospect_notes/` | `prospect_notes` | §7.15 |

### Workers (2)
- `workers/tasks/apollo_sync.py` — pulls Apollo every 6h, dedupes against thh-backend (touch point 2), upserts prospects + companies (Arch-12)
- `workers/tasks/heat_recalc.py` — replays `campaign_events` since last run, bumps `prospects.heat_score`, rebuckets `heat_level` (Arch-21)

### Webhook handler
- `services/webhooks/routes.py` — your half is the **`POST /api/webhooks/calendly`** handler (Dev B owns Apollo)

---

## 2. Files you must NEVER touch (will conflict with Dev B)

- `app.py` — all 14 routers already registered there. Don't add or reorder.
- `setup_database.py::import_all_models()` — all 14 imports already there.
- `database_connection/connection.py` — stable.
- `alembic/env.py` — stable.
- `services/audit/` — Dev B owns it. You **call** `AuditLogCRUD.record(...)` from your CRUD methods (already imported in `call_logs/crud.py` as a reference pattern), but you don't edit the audit service files.
- Any `services/` folder not in your table above.

If you genuinely need to edit one of these, message Dev B first and do it in a separate PR before any feature work.

## 3. Files you may need to touch (coordinate with Dev B)

- `services/common/enums.py` — only when adding a new TINYINT value (e.g. a new channel, stage, campaign event type). PR-only, never push directly. Tag Dev B in the PR.
- `requirements.txt` — when adding a Python dep, append to the bottom. Separate PR from feature work.
- `env.example` — if you add a new env var, document it here. Separate PR.

---

## 4. Build order (within your lane)

Do these in order. Each step assumes the previous is merged to `main`.

### Step 1 — `services/admin_users/` (auth scaffolding)

**Status:** Lakshay landed `feat(admin_users): JWT cookie auth` already. Your job is to **finish wiring it** so the rest of the codebase has a `current_user` dependency.

**What to build:**
1. Routes (`services/admin_users/routes.py`)
   - `POST /api/auth/login` — verify email + password (bcrypt), set httpOnly + Secure + SameSite=Lax cookie named `lead_engine_session`. Returns `{user: AdminUserOut}`.
   - `POST /api/auth/logout` — clears the cookie.
   - `GET /api/auth/me` — reads cookie, returns the current admin user (the frontend's `authStore.refresh()` calls this).
   - `GET /api/admin-users/` — list (existing, but gate behind `current_user.role == admin`).
   - `POST /api/admin-users/` — create (existing, but gate behind admin role).
   - `PATCH /api/admin-users/{id}` — update (existing, gated).
   - `DELETE /api/admin-users/{id}` — soft-delete (existing, gated).
2. JWT helpers in `services/admin_users/jwt_utils.py`:
   - `create_access_token(user_id, role) -> str`
   - `decode_access_token(token) -> {user_id, role}` — raises 401 on invalid/expired.
3. FastAPI dependency `current_user` in `services/admin_users/deps.py`:
   - Reads cookie → decodes → loads `AdminUser` from DB → returns it.
   - Helper `require_role(*allowed_roles)` for role gating.
4. Frontend's `src/middleware.ts` looks for cookie `lead_engine_session` — keep that name.

**Cross-lane handoff:** once `current_user` lands, every service that takes a `*_user_id` query param (campaigns create, prospect_notes create, etc.) should switch to `current_user: AdminUser = Depends(require_role(...))`. Update those after Step 1 ships.

**Acceptance test:**
```bash
# log in
curl -c cookies.txt -X POST http://127.0.0.1:5050/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"prateek@thehirehub.io","password":"<your seeded pwd>"}'

# /me returns the user
curl -b cookies.txt http://127.0.0.1:5050/api/auth/me

# logout clears cookie
curl -b cookies.txt -X POST http://127.0.0.1:5050/api/auth/logout
```

---

### Step 2 — `services/companies/`

**Status:** scaffold complete (model + schemas + CRUD + routes), but business logic is thin. Your job is to add the missing endpoints and rules.

**What to add:**
1. `POST /api/companies/check-domain` — given a `domain`, returns `{exists: bool, company_id: int|null}`. Used by Dev B's signup flow + by your Apollo sync worker.
2. `POST /api/companies/{id}/enrich` — stub for now; calls a future `services/companies/enrichment.py` (out of scope). Set `enriched_at` to NOW. Returns the updated company.
3. List endpoint: add filter params for `industry`, `funding_stage`, `q` (case-insensitive name/domain search).
4. Audit log integration: every `create`, `update`, `soft_delete` writes an `audit_log` row via `AuditLogCRUD.record(entity_type='company', entity_id=..., action='create'|'update'|'delete', actor_user_id=current_user.id)`.

**Acceptance test:**
```bash
# create + dedupe
curl -X POST http://127.0.0.1:5050/api/companies/ -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"name":"Razorpay","domain":"razorpay.com","industry":"Fintech","source":1}'

curl -X POST http://127.0.0.1:5050/api/companies/check-domain -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"domain":"razorpay.com"}'
# → {exists: true, company_id: 1}
```

---

### Step 3 — `services/prospects/` (the big one)

**Status:** scaffold has model + basic list/get/create/update/delete + `change_stage`. Your job is to flesh out everything else.

**What to add:**

1. **Dedupe priority chain on insert** (Arch-6, locked decision):
   - Add `services/prospects/dedupe.py` with a `find_existing(db, *, linkedin_url, email, phone)` helper.
   - Order of precedence: LinkedIn URL exact → email exact → phone exact.
   - Update `POST /api/prospects/` to use this helper; on hit, return 409 with the existing prospect's id (current scaffold only checks LinkedIn).
2. **Quality score computation** in `services/prospects/quality.py`:
   - Pure function `compute_quality_score(prospect, company) -> int (0-10)` based on company size + funding_stage + title keywords. Document the rules.
   - Recompute on prospect create + on company update.
3. **Channel touch tracking**:
   - `POST /api/prospects/{id}/touch` — body `{channel: int}`. Calls `ProspectChannelCRUD.upsert_touch` (already exists). Increments `prospects.touch_count` + sets `last_touched_at`.
   - Auto-fire from worker tasks where appropriate (Apollo sync touches `apollo`, email events touch `cold_email`, etc.).
4. **Stage history viewer**:
   - `GET /api/prospects/{id}/stage-history` — returns rows from `prospect_stage_history` ordered desc.
5. **Merge review queue**:
   - `POST /api/prospects/merge-review/{id}/decide` — body `{decision: "merged"|"rejected", kept_prospect_id?: int, merged_prospect_id?: int}`. On `merged`: copy fields, write `prospect_merge_log`, soft-delete the loser, mark queue row `merged`. On `rejected`: just mark queue row.
6. **Auto Cold → Curious promotion** (Arch-37, P4 pending):
   - When Dev B's `landing_page_visits` insert fires, you receive a service call (Dev B will import a function from your service). Add `services/prospects/promotion.py::promote_to_curious_on_visit(db, prospect_id)` — checks current stage, if cold → curious via `change_stage` with `reason="auto: landing page visit"`.
   - Dev B will call this from their visit handler.
7. **Promote-to-THH endpoint** (Phase 3 prep, but stub it now):
   - `POST /api/prospects/{id}/promote-to-thh` — currently raises 501 with body `{"detail": "TODO Phase 3"}`. Phase 3 will implement the actual call to thh-backend.
8. **Audit log on every state change** (stage change, owner reassign, manual edit, soft delete).

**Acceptance test:**
```bash
# duplicate by email (different LinkedIn URL)
curl -X POST http://127.0.0.1:5050/api/prospects/ -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"email":"vikram@phonepe.com","first_name":"Vikram"}'

curl -X POST http://127.0.0.1:5050/api/prospects/ -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"email":"vikram@phonepe.com","first_name":"V."}'
# → 409, returns existing prospect id

# stage history written
curl -X POST http://127.0.0.1:5050/api/prospects/1/stage -b cookies.txt \
  -H 'Content-Type: application/json' -d '{"to_stage":1,"reason":"opened email"}'

curl -b cookies.txt http://127.0.0.1:5050/api/prospects/1/stage-history
# → [{ from_stage: 0, to_stage: 1, reason: "opened email", changed_at: ... }]
```

---

### Step 4 — `services/prospect_notes/`

**Status:** scaffold complete; just needs auth gating + minor polish.

**What to add:**
1. Replace the `created_by_user_id` query param on `POST /` with `Depends(current_user)`.
2. Replace the `user_id` path param on `/tasks/open/{user_id}` with the current user (or keep it for admins to view others' tasks — gate by role).
3. List endpoint with pagination (`limit`, `offset`).
4. Endpoint `POST /api/prospect-notes/{id}/complete` to flip a task from `task_open` → `task_done`.
5. Audit row on create + delete.

---

### Step 5 — `services/campaigns/` (+ events)

**Status:** scaffold has list/get/create + `record_event`. Need the rest.

**What to add:**
1. `POST /api/campaigns/{id}/prospects` — body `{prospect_ids: int[]}` — bulk add to `campaign_prospects`. Uses `CampaignProspectCRUD.add_prospects` (already exists).
2. `POST /api/campaigns/{id}/status` — body `{status: int}` — change campaign status, write audit row.
3. `GET /api/campaigns/{id}/events` — paginated list of events for a campaign, optional `event_type` filter.
4. `GET /api/campaigns/{id}/funnel` — aggregate counts by `event_type` for the funnel viz on the frontend Campaign Detail screen. Returns `{sent, delivered, opened, clicked, replied_positive, replied_negative, demo_booked, ...}`.
5. `GET /api/campaigns/{id}/prospects` — list of prospects in the campaign with their latest event.
6. **Heat-score side effect:** when `record_event` fires for `opened` (event_type=2), `clicked` (3), `landing_visit` (12), or `replied_positive` (5), call into Dev A's heat tracker (your own code; just bump `prospects.heat_score`). This is what your `heat_recalc` worker also does in batch — both paths should use the same function.

---

### Step 6 — `services/email_replies/`

**Status:** scaffold has list-for-prospect + record. Add the classifier.

**What to add:**
1. `services/email_replies/classifier.py` — pure function `classify_reply(body, subject) -> {classification: 0|1, classified_by: 0, confidence: float}`. Rule-based for v1 (keywords like "remove me", "unsubscribe", "not interested" → negative; "demo", "interested", "book a call" → positive). Default: positive with low confidence.
2. `POST /api/email-replies/` — when classifier confidence < 0.6, set `classified_by=2` (manual) and surface in a "needs review" queue.
3. `POST /api/email-replies/{id}/reclassify` — body `{classification: 0|1}` — manual override. Sets `classified_by=2`.
4. `GET /api/email-replies/needs-review` — replies where `classified_by=0` (rule) and `classifier_confidence < 0.6`.
5. **Side effect on positive reply:** auto-create a Calendly demo prompt (frontend handles the UI; backend writes a `campaign_events` row event_type=`demo_booked` only when Calendly webhook fires — Dev B's lane).

---

### Step 7 — `services/unsubscribes/`

**Status:** scaffold has GET + POST + check. Add the cascading effect.

**What to add:**
1. **On unsubscribe insert:** also flip the prospect's stage to `unsubscribed` (4) via `ProspectCRUD.change_stage` and write audit row.
2. `POST /api/unsubscribes/by-token/{token}` — public endpoint (no auth), used by email unsubscribe links. The token = HMAC of email + secret. Implement HMAC verify in `services/unsubscribes/tokens.py`.
3. List-Unsubscribe header support: every outbound email (out of your scope, but the email service will call your endpoint) needs `mailto:` and `https://` unsubscribe URLs (Arch-26 / GDPR).

---

### Step 8 — `services/webhooks/routes.py` — Calendly handler

**Status:** scaffold accepts payload + dedupes via `webhook_deliveries`. Add the actual processing.

**What to add (your half only — Dev B owns Apollo handler):**
1. **HMAC signature verification** using `CALENDLY_WEBHOOK_SIGNING_KEY` (env). Use `hmac.compare_digest`. Reject with 401 on mismatch.
2. **Timestamp tolerance** — reject events older than `WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS` (default 300, env-overridable).
3. On valid `invitee.created` event:
   - Extract email from payload.
   - Find prospect via dedupe chain (your `find_existing` helper).
   - Set `prospects.demo_booked_at = now`.
   - Write `campaign_events` row event_type=`demo_booked` (8).
   - Mark `webhook_deliveries.status = processed`.
4. On `invitee.canceled`: write `campaign_events` event_type=`demo_no_show` (10) — only if the demo was scheduled in the past.

**Acceptance:** mock a Calendly POST with a valid HMAC and assert prospect's `demo_booked_at` got set + audit row written.

---

### Step 9 — `workers/tasks/apollo_sync.py`

**What to build:**
1. `services/integrations/apollo.py` — async HTTP wrapper around Apollo's `/v1/people/search` with our ICP filter (engineering / fintech / Indian companies). Page through results.
2. For each contact:
   - Call thh-backend `check-company-exists` (touch point 2; stub for now, real impl in Phase 3 — your service).
   - Upsert into `companies` by domain.
   - Upsert into `prospects` by `apollo_contact_id` (unique key in §7.3).
   - Touch `prospect_channels(channel=apollo)`.
   - Write audit_log per upsert.
3. Schedule via `arq.cron` in `workers/settings.py` — every 6 hours.

---

### Step 10 — `workers/tasks/heat_recalc.py`

**What to build:**
1. Find the timestamp of the last run (store in a `worker_state` row — single source-of-truth). For first run, default to 30 days ago.
2. Query `campaign_events WHERE occurred_at > last_run`.
3. For each event, increment `prospects.heat_score` by:
   - `opened` +1
   - `clicked` +2
   - `landing_visit` (with no signup) +3
   - `replied_positive` +5
4. Recompute `heat_level`: 0–2 → cold, 3–7 → warm, 8+ → hot.
5. Update `worker_state.last_run = now`.
6. Schedule via `arq.cron` — hourly.

---

## 5. Phase 3 (after Phase 2 is done)

Once Dev B is also ~done with Phase 2, you take on Phase 3 (THH integration) since auth + prospects are yours:

- Build `services/integrations/thh_backend.py` — async httpx wrapper with `THH_BACKEND_BASE_URL` + `THH_BACKEND_SERVICE_TOKEN`.
- Implement the 4 touch points:
  1. `LeadCRUD.create_lead` for Promote-to-THH (calls from your `prospects/promote-to-thh` endpoint, replacing the 501 stub).
  2. `check-company-exists` for Apollo dedupe (replacing the stub in `apollo_sync`).
  3. `POST /api/auth/login-otp/send` for signup OTP (called by Dev B's signup flow — coordinate the function signature with Dev B in advance).
  4. `POST /api/auth/login-otp/verify` for signup OTP (same).

Dev B's Activation Sync worker is touch point 5 — they'll import your client.

---

## 6. Workflow rules

1. Branch per service: `feat/dev-a/prospects-dedupe`, `feat/dev-a/calendly-webhook`, etc.
2. Before push: `git fetch origin && git rebase origin/main`. If a rebase conflict appears in `app.py`, `setup_database.py`, or `services/common/enums.py` — **stop and ping Dev B** before resolving.
3. Squash-merge to `main`.
4. PR title format: `feat(prospects): dedupe chain on insert` / `fix(campaigns): null channel handling` / `chore(deps): add httpx`.
5. Run smoke test before opening PR:
   ```bash
   .venv/Scripts/python.exe -c "import app; print(len(app.app.routes), 'routes')"
   ```
   Should not error and should print 59+ as you add routes.
6. Every CRUD method that mutates state should write to `audit_log` — Dev B's `AuditLogCRUD.record` is your friend.

---

## 7. Cross-lane handoffs you owe Dev B

| When you ship | Dev B unblocks |
|---|---|
| `current_user` dependency (Step 1) | Can replace `*_user_id` query params in their services |
| `services/prospects/promotion.py::promote_to_curious_on_visit` (Step 3.6) | Their `landing_page_visits` POST handler can call it |
| `services/prospects/dedupe.py::find_existing` (Step 3.1) | Their signups OTP-verify can use it to upsert prospects |
| `companies/check-domain` endpoint (Step 2.1) | Their signups flow can pre-check before insert |

Communicate function signatures by PR comment **before** you implement — Dev B will sketch their import.

---

## 8. Cross-lane handoffs you depend on (from Dev B)

| What you need | When Dev B ships |
|---|---|
| `AuditLogCRUD.record` is callable from your CRUD methods | Already done in scaffold; don't break it |
| `services/funnel_snapshots/crud.FunnelSnapshotCRUD.upsert` exists | Your dashboards / management board don't need this directly; backend-only |
| Webhook table works | Already in scaffold; you just write records to it via your Calendly handler |

---

## 9. Pending user input (§14) that affects your work

- **P5** — 3xRNR auto-marker mechanism: when call_logs writes 3 RNRs (Dev B's CallLogCRUD does this), what happens to the prospect? The schema doc says "TBD". Coordinate with Ishank — likely a milestone column `marked_not_interested_at` or stage move to `lost`. Update your `prospects/` model + CRUD when locked.
- **P4** — Cold → Curious auto-promotion on landing page visit insert. Step 3.6 above is the implementation — tag Ishank in the PR for sign-off.
