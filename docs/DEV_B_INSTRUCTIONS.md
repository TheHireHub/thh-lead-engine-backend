# Dev B — Backend Lane Instructions

**Owner of:** landing pages, signups, jobs/CSM subsystem, call logs, funnel snapshots, audit, Apollo webhook.

> Schema doc references like `§7.21`, `§6.27`, `Arch-40` map into [`SCHEMA.md`](./SCHEMA.md). When in doubt, the schema doc is the source of truth.

---

## 1. Your scope

### Service modules (7)
| Folder | Tables | Schema § |
|---|---|---|
| `services/landing_pages/` | `landing_pages`, `landing_page_variants`, `landing_page_visits` | §7.9, 7.10, 7.11 |
| `services/signups/` | `signups` | §7.12 |
| `services/audit/` | `audit_log` | §7.16 |
| `services/funnel_snapshots/` | `funnel_daily_snapshots` | §7.17 |
| `services/prospect_company_jobs/` | `prospect_company_jobs`, `prospect_company_job_candidates`, `prospect_company_job_history`, `prospect_company_job_boards` | §7.21, 7.22, 7.23, 7.24 |
| `services/call_logs/` | `call_logs` | §7.25 |

### Workers (2)
- `workers/tasks/funnel_snapshot.py` — daily aggregate of prospects by (stage, channel, owner) → upsert into `funnel_daily_snapshots` (Arch-20)
- `workers/tasks/activation_sync.py` — daily, for every promoted prospect calls thh-backend §9.5 to update `first_job_created_at` + `first_applicant_received_at` (Arch-38)

### Webhook handler
- `services/webhooks/routes.py` — your half is the **`POST /api/webhooks/apollo`** handler (Dev A owns Calendly)

---

## 2. Files you must NEVER touch (will conflict with Dev A)

- `app.py` — all 14 routers already registered there. Don't add or reorder.
- `setup_database.py::import_all_models()` — all 14 imports already there.
- `database_connection/connection.py` — stable.
- `alembic/env.py` — stable.
- `services/admin_users/` — Dev A owns it. You **import** `current_user` and `require_role` from `services.admin_users.deps` once Dev A ships them, but don't edit auth files.
- Any `services/` folder not in your table above.

If you genuinely need to edit one of these, message Dev A first and do it in a separate PR before any feature work.

## 3. Files you may need to touch (coordinate with Dev A)

- `services/common/enums.py` — only when adding a new TINYINT value (e.g. a new job board, candidate status). PR-only, never push directly. Tag Dev A in the PR.
- `requirements.txt` — when adding a Python dep, append to the bottom. Separate PR from feature work.
- `env.example` — if you add a new env var, document it here. Separate PR.

---

## 4. Build order (within your lane)

Do these in order. Each step assumes the previous is merged to `main`.

### Step 1 — `services/audit/`

**Status:** scaffold complete (`AuditLogCRUD.record` works). Just polish.

**What to build:**
1. **Verify** `AuditLogCRUD.record` is callable from any CRUD method without circular imports — it already is, but Dev A is going to start writing audit rows in Step 2 of their lane. Run the smoke test below to confirm.
2. `GET /api/audit-log/by-action/{action}` — search by action string (e.g. `auto_marked_not_interested`, `promote_to_thh`, `gdpr_erase`). Pagination with `limit`/`offset`.
3. `GET /api/audit-log/recent` — last N audit events across all entities, default 50. For the future "Audit Log" page in the admin UI.
4. **No mutations.** `audit_log` is append-only. Don't add an `update` or `delete` route.

**Acceptance test:**
```bash
# Dev A's prospects/change_stage already calls AuditLogCRUD.record.
# After a stage change you should see:
curl -b cookies.txt "http://127.0.0.1:5050/api/audit-log/by-entity/prospect/1"
# → list with action="stage_change"
```

---

### Step 2 — `services/landing_pages/`

**Status:** scaffold has list/get-by-slug/create + variant create + visit record. Add the rest.

**What to build:**

1. **Variant assignment service** — `services/landing_pages/variant_picker.py`:
   - Pure function `pick_variant(variants: list[Variant], visitor_id: str) -> Variant | None`.
   - **Sticky** per visitor: hash `(visitor_id + landing_page_id)` → modulo total `weight`. Same visitor → always same variant.
   - Skip variants where `status != active` (0) or `weight == 0`.
2. `GET /api/landing-pages/by-slug/{slug}/render` — returns `{page, picked_variant, content_json}`. The frontend public landing page calls this.
3. **Visit handler enhancements:**
   - `POST /api/landing-pages/visits` already exists. Add: hash IP via `VISITOR_IP_HASH_SECRET` env (sha256(ip + secret)), pull `user_agent` from request headers, parse `utm_*` from query params if not in body.
   - **Cross-lane side effect:** if `prospect_id` is set on the visit, call `services.prospects.promotion.promote_to_curious_on_visit(db, prospect_id)` (Dev A's helper, ships in their Step 3.6). Until they ship: comment with `# TODO Dev A handoff` and skip silently.
   - Increment `landing_pages.visit_count` and set `last_visit_at`.
4. **Variant performance endpoint:**
   - `GET /api/landing-pages/{id}/variants/performance` — returns each variant's `visit_count`, `signup_count`, computed `signup_rate`. Populated by the visit + signup handlers.
5. **Signup-count side effect on signups (Dev A's signups won't exist; this is your service):** when Dev B's own signup creation runs (Step 3 below), bump `landing_page_variants.signup_count` for the variant the signer was shown. The visit row records `landing_page_variant_id` — read it back from the visitor's most recent visit.
6. `POST /api/landing-pages/{id}/variants` — already exists. Add `weight` validation (0–1000). Default new variants to `status=active` (0).
7. **List endpoint** with filters: `prospect_id`, `company_id`, `template_key`. Pagination.
8. **Audit row** on landing_page create + variant create + variant status change.

**Acceptance test:**
```bash
curl -X POST http://127.0.0.1:5050/api/landing-pages/ -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"slug":"phonepe-vikram","template_key":"classic","default_content_json":{"hero":"Hi Vikram"}}'

curl -X POST http://127.0.0.1:5050/api/landing-pages/variants -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"landing_page_id":1,"variant_key":"hero_v1","content_json":{"hero":"Variant A"},"weight":100}'

curl -X POST http://127.0.0.1:5050/api/landing-pages/variants -b cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"landing_page_id":1,"variant_key":"hero_v2","content_json":{"hero":"Variant B"},"weight":100}'

# render — should pick the same variant for the same visitor every time
curl "http://127.0.0.1:5050/api/landing-pages/by-slug/phonepe-vikram/render?visitor_id=abc123"
curl "http://127.0.0.1:5050/api/landing-pages/by-slug/phonepe-vikram/render?visitor_id=abc123"
# → both same variant_key
```

---

### Step 3 — `services/signups/`

**Status:** scaffold has create + mark_otp_verified. The actual OTP flow is Phase 3 (calls thh-backend); your Phase 2 job is the wiring around it.

**What to build:**

1. **POST `/api/signups/`** — when a prospect submits the landing page form:
   - Validate email format (Pydantic `EmailStr` already does this).
   - Pull `landing_page_id` and `landing_page_variant_id` from the most recent `landing_page_visits` row for this `visitor_id` (denormalised onto the signup row for analytics).
   - Insert `signups` row with `otp_verified_at = NULL`.
   - Call thh-backend's `POST /api/auth/login-otp/send` — **stub for Phase 2** (Phase 3 brings real impl); for now write `campaign_events` row event_type=`otp_sent` (16) and return `{success: true, signup_id}`.
   - Audit row.
2. **POST `/api/signups/{id}/otp-verify`** — when prospect enters the OTP:
   - Call thh-backend's `POST /api/auth/login-otp/verify` — **stub for Phase 2** (Phase 3 brings real impl); for now accept any 6-digit code.
   - On success:
     - Set `signups.otp_verified_at = now`.
     - **Upsert prospect** via Dev A's `services.prospects.dedupe.find_existing` (their Step 3.1 ships this). If exists, update `first_name`/`last_name`/`phone`/`company_id` from signup. If not, create a new prospect with stage=cold + source_channel based on the landing page's source_campaign.
     - Set `prospects.registered_at = now`.
     - Bump `landing_page_variants.signup_count` for the variant they were shown (read from the visit row).
     - Write `campaign_events` event_type=`otp_verified` (17).
     - Telegram alert via `services/integrations/telegram.py` (skeleton in Phase 2; real impl in Phase 9 — for now just log).
   - Returns `{success: true, prospect_id}`.
3. **GET `/api/signups/`** — list, filter by `request_type` and `otp_verified` (computed: `otp_verified_at IS NOT NULL`), pagination.
4. **Resend OTP** endpoint: `POST /api/signups/{id}/resend-otp` — rate-limit to 1/min. Same stub logic as #1.
5. **Audit rows** on every state change.

**Cross-lane handoff:** you cannot finish Step 3 until Dev A ships `dedupe.find_existing` (their Step 3.1) and `companies/check-domain` (their Step 2.1). Until then, ship a partial version that creates the signup row + writes `otp_sent` event but leaves the prospect upsert as `# TODO`.

---

### Step 4 — `services/prospect_company_jobs/` (the big one)

**Status:** scaffold has list-for-company / at-risk / get / create / update / distribute (the workflow) / candidates list + create. Polish + add audit + history.

**What to build:**

1. **Job field-change history** (`prospect_company_job_history`):
   - Wrap `update` in a helper that compares before/after on these fields: `status`, `paid_status`, `confidentiality`, `no_linkedin_post`, `assigned_to_csm_user_id`, `expectation_target`. For each change, insert a `prospect_company_job_history` row.
   - `GET /api/prospect-company-jobs/{id}/history` — returns rows desc.
2. **Distribute (Post-a-Job) workflow** (Schema §5.6, Arch-40, already partially scaffolded in CRUD):
   - `POST /api/prospect-company-jobs/{id}/distribute` — already accepts `boards`, `expectation_target`, `days_threshold`. Verify the CRUD writes:
     - `posted_at = now`
     - `expectation_target = body.expectation_target`
     - `at_risk_at = posted_at + days_threshold` (UI takes days, store absolute datetime — already in scaffold).
     - one `prospect_company_job_boards` row per selected board with `status=pending`.
   - Audit row `action=distribute`.
3. **Per-board posting state:**
   - `POST /api/prospect-company-jobs/boards/{board_row_id}/mark-posted` — sets `status=posted`, `posted_at=now`, optional `external_url`.
   - `POST /api/prospect-company-jobs/boards/{board_row_id}/mark-failed` — sets `status=failed` + `notes`.
   - `POST /api/prospect-company-jobs/boards/{board_row_id}/mark-removed` — sets `status=removed` + `removed_at=now`.
   - History row on each.
4. **Applicant counter intake** (Arch-41 one-way ratchet):
   - `POST /api/prospect-company-jobs/{id}/applicants` — body `{board: int, applicant_count: int}`. Calls existing `JobCRUD.record_applicants`.
   - Verify the ratchet: once `total_applicants >= expectation_target`, set `target_met_at = now` and **never clear it** even if counts later drop. (Already in scaffold; cover with a test.)
5. **Posting Helper page data source** (Schema §5.7, P3 pending):
   - **PENDING** decision: lead engine stores all THH-style job fields locally OR pulls live from thh-backend. Tag Ishank in your PR for sign-off before deciding.
   - For now: stub the helper as `GET /api/prospect-company-jobs/{id}/posting-helper` — returns whatever fields exist on the job (title, dept, location, etc.) wrapped in a "ready to copy" envelope. Phase 9 expands.
6. **Candidate matching:**
   - `GET /api/prospect-company-jobs/{id}/candidates` — already exists.
   - `POST /api/prospect-company-jobs/candidates` — already exists. Add: when status changes to `presented` (1), set `presented_at=now`. When status hits `accepted`/`rejected`/`withdrawn`/`hired`, set `decided_at=now`. Audit row.
   - `PATCH /api/prospect-company-jobs/candidates/{id}/status` — body `{status: int, decision_notes?: str}`. Updates status + appropriate timestamp + history.
   - Bump `prospect_company_jobs.candidates_prepared` denormalised count on candidate insert/delete.
7. **Filter endpoints for the CSM Board:**
   - `GET /api/prospect-company-jobs/?company_id=&status=&paid_status=&confidentiality=&no_linkedin_post=` — combined filter.
   - `GET /api/prospect-company-jobs/grouped-by-company` — for the design's company-grouped view.

---

### Step 5 — `services/call_logs/`

**Status:** scaffold has by-prospect / callbacks / record. The 3xRNR auto-marker is partially there; finish it.

**What to build:**
1. **Verify** `CallLogCRUD.record` correctly:
   - Increments `prospects.rnr_count` on RNR (outcome=0).
   - Writes `audit_log` action=`auto_marked_not_interested` when count hits 3.
2. **PENDING (P5):** what happens to the prospect at 3 RNRs — set a milestone column? Move to stage `lost`? Set a flag? Tag Ishank in your PR. Until decided, leave the audit row as the only side effect.
3. **POST `/api/call-logs/`** — already exists. Add validation: when `outcome=2` (call_back), `callback_at` is required.
4. **Caller "Next" view backend:**
   - `GET /api/call-logs/next-prospect?caller_user_id=...` — returns the next assigned prospect for the caller. Logic: prospects with `owner_user_id == caller_user_id`, sorted by oldest `last_touched_at` first, excluding those with stage in (lost, unsubscribed, converted) and excluding those with a recent RNR within 24h.
   - `POST /api/call-logs/skip` — body `{prospect_id: int}` — bumps `last_touched_at` so the same prospect doesn't reappear immediately.
5. **Callback list:** `GET /api/call-logs/callbacks/{caller_user_id}` already exists. Add filter `?upcoming_only=true` (callback_at >= now).
6. Audit row on every call_log insert.

---

### Step 6 — `services/funnel_snapshots/`

**Status:** scaffold has range query + upsert. Just polish + helpers.

**What to build:**
1. `GET /api/funnel-snapshots/` already exists; add aggregation modes:
   - `?mode=daily` (default)
   - `?mode=weekly` — group rows by ISO week
   - `?mode=monthly`
2. `GET /api/funnel-snapshots/today` — fast query for current-day live counts (computed from `prospects` table directly, not from snapshots which are nightly).
3. `GET /api/funnel-snapshots/conversion-rates` — given a from/to date range, returns:
   - Cold → Curious %
   - Curious → Trial first_job_created %
   - Demo → Converted %
   (Powers the Funnel Board KPI strip.)

---

### Step 7 — `services/webhooks/routes.py` — Apollo handler

**Status:** scaffold accepts payload + dedupes. Add the actual processing.

**What to add (your half — Dev A owns Calendly):**
1. **HMAC verification** if Apollo sends one (most accounts don't; document in `env.example` whether to enforce).
2. On valid `prospect.updated` / `prospect.created` event:
   - Extract Apollo contact id, email, name, company.
   - Upsert into `prospects` by `apollo_contact_id` (uses Dev A's `find_existing` once it ships; until then upsert by linkedin_url match).
   - Update freshness timestamps.
   - Write audit row.
3. `webhook_deliveries.status = processed` on success, `failed` + `error_message` on exception.

---

### Step 8 — `workers/tasks/funnel_snapshot.py`

**What to build:**
1. Compute today's date in IST (project default).
2. Query `prospects WHERE deleted_at IS NULL` grouped by `(stage, source_channel, owner_user_id)`.
3. For each combination, call `FunnelSnapshotCRUD.upsert(snapshot_date=today, stage=..., channel=..., owner_user_id=..., prospect_count=...)`. The unique key on the table makes this idempotent.
4. Also write an **all-channel rollup** with `channel=NULL` for each stage.
5. Schedule via `arq.cron` in `workers/settings.py` — daily at 02:00 IST.

---

### Step 9 — `workers/tasks/activation_sync.py`

**What to build:**
1. Query prospects with `thh_user_id IS NOT NULL AND deleted_at IS NULL`.
2. For each, call `services.integrations.thh_backend.get_activation_status(thh_user_id)` — **stub for Phase 2** returns `{has_jobs: false, ...}`. Phase 3 brings real impl (Dev A's lane, but the worker is yours).
3. On real data:
   - If `prospect.first_job_created_at` is NULL and response has `first_job_at`, set it. Fire Telegram alert "{prospect.name} created their first job".
   - Same for `first_applicant_received_at`.
   - Update `jobs_created_count` and `applicants_received_count`.
   - Audit row on first-time activation (action=`first_activation`).
4. Schedule via `arq.cron` — daily at 03:00 IST (after funnel_snapshot).

---

## 5. Phase 3 (after Phase 2 is done)

Phase 3 lives mostly in Dev A's lane (auth + prospects + thh-backend client). Your Phase 3 work:

- Once Dev A ships `services/integrations/thh_backend.py`, **swap the stubs** in:
  - Your `signups/` OTP send + verify (replace stub with real call).
  - Your `activation_sync` worker (replace stub with real call to §9.5).
- Telegram alert wiring in `signups/otp-verify` and `activation_sync` (PR up `services/integrations/telegram.py` with `send_alert(channel, text)`). Coordinate with Dev A on whether they or you own this file — recommend you, since both your services use it.

---

## 6. Branching model and workflow

### The four branches

```
main      ← production / stable. Only Phase milestones land here.
  ↑
dev       ← integration branch. Both devs' work converges here.
  ↑   ↑
dev-a   dev-b
```

- **`main`** — touch only when Phase 2 / 3 hits a milestone. Reviewed merges from `dev` only.
- **`dev`** — every PR you open targets this branch. Once both devs' work on `dev` is stable + smoke-tested, someone (whoever's free) opens a PR `dev → main`.
- **`dev-b`** — your working branch. You commit here freely.
- **`dev-a`** — Dev A's working branch. **You never touch it.**

### Daily flow

1. **Start your day**:
   ```bash
   git checkout dev-b
   git fetch origin
   git rebase origin/dev          # pull in any of Dev A's merged work
   ```
2. **Work** — commit to `dev-b` directly, or use sub-feature branches off `dev-b` if a single piece of work is large enough to want its own PR-style review:
   ```bash
   git checkout -b feat/landing-variant-picker dev-b
   # ... work ...
   git checkout dev-b
   git merge --no-ff feat/landing-variant-picker
   git branch -d feat/landing-variant-picker
   ```
3. **Push to remote**:
   ```bash
   git push origin dev-b
   ```
4. **Open a PR `dev-b → dev`** when a chunk is ready for integration. Every chunk should be independently reviewable — don't sit on 3 weeks of work.
5. **After your PR merges into `dev`**, both you and Dev A should rebase your branches:
   ```bash
   git checkout dev-b
   git fetch origin
   git rebase origin/dev
   git push --force-with-lease origin dev-b
   ```
   `--force-with-lease` is safe; never use plain `--force`.

### Conflict prevention

- **If a rebase conflict appears in `app.py`, `setup_database.py`, or `services/common/enums.py`** — stop, ping Dev A, resolve together. These are the only files where you might collide.
- **If a conflict appears anywhere else**, it means you accidentally edited Dev A's territory. Revert your change and re-do it in your lane.
- Don't merge `dev-a` into `dev-b` directly. Both branches only flow through `dev`.

### PR title + commit message format

- `feat(landing_pages): variant picker`
- `fix(call_logs): callback_at validation`
- `chore(deps): add httpx`
- `docs(jobs): document distribute workflow`

### Pre-PR checklist

```bash
# 1. Smoke test — app imports cleanly
.venv/Scripts/python.exe -c "import app; print(len(app.app.routes), 'routes')"

# 2. Migrations apply cleanly (if you added/changed models)
alembic upgrade head

# 3. setup_database.py still works on a fresh DB
python setup_database.py --drop
```

### Audit row reminder

Every CRUD method that mutates state should write to `audit_log` — you own the audit service, so eat your own dog food. Call `AuditLogCRUD.record(...)` from every mutation in every service of yours.

---

## 7. Cross-lane handoffs you owe Dev A

| When you ship | Dev A unblocks |
|---|---|
| `audit/` polish (Step 1) | They can already write audit rows; just confirms shape |
| `landing_page_visits` POST that calls into `prospects.promotion.promote_to_curious_on_visit` (Step 2.3) | Their Cold → Curious auto-promotion gets exercised |
| `signups/otp-verify` calls `prospects.dedupe.find_existing` (Step 3) | Their dedupe helper gets exercised through the signup path |
| `webhooks/apollo` upserts via `prospects.dedupe` (Step 7) | Apollo sync worker has a parallel inbound path |

Communicate function signatures by PR comment **before** you implement — Dev A will adjust their helpers if needed.

---

## 8. Cross-lane handoffs you depend on (from Dev A)

| What you need | When Dev A ships |
|---|---|
| `current_user` dependency + `require_role` | Their Step 1 — required before you can gate any of your endpoints |
| `services/prospects/dedupe.py::find_existing` | Their Step 3.1 — required for your signup OTP-verify flow + Apollo webhook |
| `services/companies/check-domain` endpoint | Their Step 2.1 — your signup flow can pre-check |
| `services/prospects/promotion.py::promote_to_curious_on_visit` | Their Step 3.6 — your visit handler calls this |
| `services/integrations/thh_backend.py` (Phase 3) | Their Phase 3 — replace stubs in signups + activation_sync |

Until each ships, leave a `# TODO Dev A handoff` and a working stub so the route doesn't break.

---

## 9. Pending user input (§14) that affects your work

- **P3** — Posting Helper data source: store all THH-style job fields locally on `prospect_company_jobs` child tables OR pull live from thh-backend at render time. Stub for now (Step 4.5); tag Ishank in the PR for the sign-off.
- **P5** — 3xRNR auto-marker mechanism: what happens to the prospect at 3 RNRs (Step 5.2). Tag Ishank.
- **P1** — "Total new" KPI definition: needed for `funnel_snapshots/` aggregation queries (Step 6). Tag Ishank.
- **P2** — "Graph per day curious → milestone" — which milestones to chart, default time window. Affects your funnel_snapshots endpoints. Tag Ishank.
