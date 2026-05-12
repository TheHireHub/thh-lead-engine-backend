# Inbound Leads — HH-BE → LEADS CRM ingestion

**Author:** Lakshay
**Status:** DRAFT (pending Ishank approval)
**Date:** 2026-05-11
**Scope:** L1 (partial-typed) + L2 (OTP requested) + L3 (OTP verified / company onboarded). **L4 (job posted) is deferred** — wire after L1-L3 ships and bugs settle.

---

## 1. Goal

Capture every inbound signup event from `thh-backend` (HH-BE) into the LEADS CRM so the sales / growth team can work them from the same surface that already handles outbound prospects. Telegram bots stay live — CRM is **additive**, not a replacement.

Three user-visible lead tiers (matching the existing HH-BE event vocabulary):

| Tier | Trigger | HH-BE event_type | What's known |
|------|---------|------------------|--------------|
| **L1 partial** | User types email into any landing-form input. FE fires `POST /api/users/lead` after a 5000ms idle debounce on blur/submit. | `partial_signup`, `enquiry_form`, `calendly_booked` | email (+ optional name, phone, company_name, designation, slug, source_meta) |
| **L2 OTP requested** | User submitted the form and clicked "Send OTP". | `otp_requested` (NEW — see §6.2) | email + signup intent |
| **L3 OTP verified / company onboarded** | OTP code verified → LP auto-enriches company → profile PATCH succeeds. | `otp_verified` + `company_onboarded` | email + verified user + company details |

L4 (`job_posted` — first job created post-signup) is reserved as a follow-up event; the prospect record already supports it via `first_job_created_at` (set by the existing `activation_sync` ARQ worker, §9.5). Nothing to build for L4 inside this scope.

## 2. Non-goals

- Replacing or muting the existing telegram bots (`partial_leads`, `verified_signups`). They keep firing alongside.
- Building a new lead table in HH-BE. HH-BE already stores leads in `users` rows + `lead_activities`. We're forwarding events out, not duplicating storage.
- L4 (`first_job_created_at`). Deferred.
- Backfilling historical leads (everything pre-merge). Cut-over is forward-only; if backfill is wanted, a one-shot script reads `lead_activities` and replays it through the webhook.
- LEADS→HH direction. Already covered by §9.1-5.

## 3. Data model — reuse existing LEADS-BE schema

**No new tables.** The existing `prospects` + `signups` + `prospect_channels` cover this cleanly.

### 3.1 `source_channel` — extend enum (§6.3)

Add one row to the channel enum (TINYINT — additive, no `ALTER`, just an `INSERT` per Arch-29 enum policy):

| Int | Label | Notes |
|-----|-------|-------|
| 13 | `hh_signup` | NEW. Signup originated inside the HH product (app.thehirehub.ai) — not via a lead-engine landing page. |

This is the **"Source" filter** the user asked for. Future inbound channels (Warmly = 10 already exists; future: enrichments, partner pixels) bucket into separate enum values and the FE source chip filters by `source_channel`.

### 3.2 `prospects` — fields used

All inbound leads upsert into `prospects` (deduped by email — see §4):

| Field | L1 | L2 | L3 |
|-------|----|----|----|
| `email` | required | required | required |
| `first_name` / `last_name` | if known (enquiry form) | same | from verified user |
| `phone` | if known | if known | if known |
| `company_id` | NULL until company name lands | NULL | set via `companies` upsert |
| `source_channel` | **13 (hh_signup)** | 13 | 13 |
| `stage` | 1 (curious — visit-equivalent) | 1 | 1 (stays curious until first job → curious is the new "registered+visited" band per §3) |
| `first_touched_at` / `last_touched_at` / `touch_count` | set / bumped | bumped | bumped |
| `registered_at` | NULL | NULL | **set** when OTP verified |
| `thh_user_id` | NULL | NULL | set (HH `users.id`) |

> Note on `stage`: per the §3 funnel restructure, `registered_at` is a **milestone timestamp** that fires independently — the stage itself doesn't change for an inbound visit. Stage moves to `converted` only on Promote-to-THH or paying-customer flip. So L1/L2/L3 all sit at `stage=1 (curious)` and the difference is which milestone columns are populated. This matches existing semantics — we don't invent a new lifecycle.

### 3.3 `signups` — one row per touch

Each inbound event also inserts a row in `signups` (append-only audit trail of the event itself, not just the prospect snapshot):

| Field | Value |
|-------|-------|
| `prospect_id` | FK to the upserted prospect |
| `email` | required |
| `name` / `company_name` / `phone` | as supplied |
| `request_type` | new enum value `5=hh_signup` (see §3.4) |
| `payload_json` | full raw event payload from HH-BE (slug, source_meta, touch info, event_type, signup_source, etc.) — preserves fidelity for forensics |
| `visitor_id` | NULL (no LP visitor on the HH side; field stays nullable) |
| `landing_page_id` | NULL |
| `otp_verified_at` | NULL on L1/L2; **set** on L3 |
| `created_at` | server time |

Rationale for one-row-per-touch (not one-row-per-prospect):
- HH-BE already dedupes telegram via the 5-min `touch_count` mechanism inside `LeadCRUD._apply_touch_tracking`. The CRM should receive **every touch** for full timeline fidelity and let the UI collapse via `touch_count` chip on the prospect card.
- `signups` is already designed append-only; reading it back gives a full event log per prospect.

### 3.4 `request_type` — extend enum (§6.11)

Add one row:

| Int | Label | Notes |
|-----|-------|-------|
| 5 | `hh_signup` | NEW. The signup came from an HH-BE event, not a lead-engine LP form. |

### 3.5 `prospect_channels` — touch tracking

Standard junction upsert: on every event, insert-or-bump the `(prospect_id, channel=13)` row with `last_touched_at = NOW()`, `touch_count = touch_count + 1`.

### 3.6 Migration

**No Alembic migration required.** Per Arch-29 the enum maps live in `services/common/enums.py` (pure Python, no DB-side enum table). Adding values = code-only edit + matching SCHEMA.md update. Existing TINYINT columns already accept the new ints.

## 4. Dedupe rule

Lookup priority: **`thh_user_id` exact → `email` exact (lowercase, trimmed) → create new**.

- `thh_user_id` is only known after L3, so for L1/L2 it's always email-keyed.
- Email comparison is case-insensitive and trimmed.
- If an existing prospect was created by Apollo sync (channel=9), an inbound HH signup **upgrades** it: keep the existing row, add `channel=13` to `prospect_channels`, leave `source_channel` as whichever fired first. The funnel UI shows multi-channel attribution via `prospect_channels`.
- Soft-deleted prospects (`deleted_at IS NOT NULL`) are revived: clear `deleted_at`, append a new `signups` row, and log a stage-history row noting the revival.

## 5. Transport — HH-BE pushes, LEADS-BE receives

### 5.1 New endpoint in LEADS-BE

```
POST /api/signups/inbound
Headers: X-Service-Token: <THH_INCOMING_SERVICE_TOKEN>
Content-Type: application/json
```

Reuses the existing `services/candidate_outreach/auth.py::require_service_token` dependency. **No new env var** — `THH_INCOMING_SERVICE_TOKEN` is already validated at startup (per `feedback_leads_be_prod_env_validator` memory). HH-BE side reads its own copy as `LEADS_INBOUND_SERVICE_TOKEN`.

Request body (Pydantic `InboundLeadEvent` in `services/signups/schemas.py`):

```json
{
  "event_type": "partial_signup | enquiry_form | calendly_booked | otp_requested | otp_verified | company_onboarded",
  "dedup_key": "hh:partial_signup:12345:1715419542",
  "event_occurred_at": "2026-05-11T08:35:42Z",
  "email": "ishank@thehirehub.ai",
  "thh_user_id": 12345,
  "first_name": "Ishank",
  "last_name": null,
  "phone": null,
  "company_name": null,
  "designation": null,
  "slug": "signup_page",
  "thh_company_id": 678,
  "signup_source": "google_signup | otp | calendly | ...",
  "source_meta": { "utm_source": "...", "utm_campaign": "...", "page": "/lp/abc" },
  "touch": { "is_new_touch": true, "touch_count": 2, "first_seen_at": "2026-05-11T08:30:00Z" },
  "anonymous": false
}
```

Validation: at least one of `email` OR `thh_user_id` must be set (400 otherwise). For Calendly-anonymous, HH-BE sends a synthetic email `anonymous+calendly+<ts>@thh.internal` + `anonymous=true`.

Response envelope (standard `{success, message, data, error}`):

```json
{ "success": true, "message": "ingested", "data": { "created": true, "prospect_id": 9001, "signup_id": 4421, "is_l3": false, "dedup_key": "hh:..." } }
```

Idempotency: server stores `dedup_key` as `webhook_deliveries.external_event_id` with `provider=4 (thh_signup)`. Duplicate keys return 200 with `created=false` and skip the insert. Protects against retries from HH-BE.

Prospect lookup order: `thh_user_id` exact → `email` (lowercase, trimmed) → `phone`. First match wins. New prospects get `source_channel=13 (hh_signup)` + `stage=1 (curious)`.

### 5.2 HH-BE integration module

New file `services/integrations/leads_engine.py` (HH-BE side). Mirrors the existing candidate-outreach push pattern. Single public function:

```python
def push_lead_event(
    event_type: str,
    *,
    email: str,
    first_name: str | None = None,
    last_name: str | None = None,
    phone: str | None = None,
    company_name: str | None = None,
    designation: str | None = None,
    slug: str | None = None,
    thh_user_id: int | None = None,
    thh_company_id: int | None = None,
    signup_source: str | None = None,
    source_meta: dict | None = None,
    touch: dict | None = None,
) -> bool:
    """Fire-and-forget POST to LEADS-BE inbound webhook. Best-effort,
    never raises (matches telegram-send semantics). Returns success bool
    for logging. Reads LEADS_BASE_URL + LEADS_INBOUND_SERVICE_TOKEN env."""
```

Failure handling:
- Wrapped in `try/except` exactly like the existing `telegram_service` send calls — primary signup flow must never break if the CRM webhook is down.
- Builds an `idempotency_key` deterministically: `f"hh:{event_type}:{thh_user_id or email}:{int(event_occurred_at.timestamp())}"`. Repeat fires within the same second collapse.
- Logs warnings to the standard logger on non-2xx.

### 5.3 Call-site patches in HH-BE

Add a `push_lead_event(...)` call **next to every `telegram_service.send_*` call** identified in the audit:

| # | File:line | Telegram call | New `push_lead_event` event_type |
|---|-----------|---------------|----------------------------------|
| 1 | `services/user/routes.py:1561` | `send_partial_lead_notification` (create_lead, email-only) | `partial_signup` |
| 2 | `services/user/routes.py:1641` | `send_partial_lead_notification` (update_lead, enquiry form) | `enquiry_form` |
| 3 | `services/user/routes.py:1697` | `send_partial_lead_notification` (calendly known email) | `calendly_booked` |
| 4 | `services/user/routes.py:1715` | `send_partial_lead_notification` (calendly anonymous) | `calendly_booked` with synthetic `anonymous+calendly+<ts>@thh.internal` email + `payload_json.anonymous=true` (per §10 decision 2) |
| 5 | `services/user/routes.py:2142` | `send_otp_verified_notification` (Google signup, domain claim) | `otp_verified` (with `signup_source=google_signup_domain_claim`) |
| 6 | `services/user/routes.py:2247` | `send_otp_verified_notification` (Google signup, new company) | `otp_verified` |
| 7 | `services/user/routes.py:2250` | `send_company_onboarded_notification` | `company_onboarded` |
| 8 | `services/companies/routes.py:384` | `send_otp_verified_notification` | `otp_verified` |
| 9 | `services/companies/routes.py:389` | `send_company_onboarded_notification` | `company_onboarded` |
| 10 | `services/companies/routes.py:1715` | `send_company_onboarded_notification` | **skip** — standalone admin company-create has no email/user, nothing to mirror to a CRM lead |
| 11 | `services/companies/routes.py:3449` | `send_otp_verified_notification` | `otp_verified` |
| 12 | `services/companies/routes.py:3642` | `send_otp_verified_notification` | `otp_verified` |
| 13 | `services/companies/routes.py:3647` | `send_company_onboarded_notification` | `company_onboarded` |

**L2 (`otp_requested`) deferred** — per Ishank 2026-05-11: HH-BE patches should mirror existing telegram fires ONLY. `send_login_otp` has no telegram trigger today; introducing one would expand HH-BE blast radius. Site 14 (and the new telegram pairing from §10 decision 1) is therefore NOT shipped in v1. Effect: L2 events do not flow into the CRM. The stage chip "OTP requested" still exists in the FE but only fills when an L3 event later confirms the user actually verified. If L2 visibility becomes critical, add a telegram fire in HH-BE first, then mirror to CRM.

**Known follow-ups (deferred)**:
- **L2**: as above.
- **Pending company name**: Google-signup path fires `company_onboarded` with `company_name='Pending'`. The real name is filled later by the post-OTP enrichment screen, which does not fire another `company_onboarded`. LEADS sees "Pending" until the enrichment-complete handler also fires (out of scope for v1).

## 6. Frontend (LEADS-FE)

### 6.1 Sidebar entry

New top-level item in the lane-A sidebar block (between "Prospects" and "Campaigns" — confirm order with dev-c per the sidebar-merge pattern memory):

```
Leads
 ├─ All
 ├─ Inbound (badge: count of last-7d new prospects with source_channel=13)
 └─ Outbound (existing prospects view)
```

The existing "Prospects" page becomes the "Outbound" sub-item. "Inbound" is a new page that pre-filters `?source_channel=hh_signup`.

### 6.2 Inbound list page (`/leads/inbound`)

Table columns:

| Column | Source | Notes |
|--------|--------|-------|
| Email | `prospects.email` | primary identifier |
| Name | `prospects.first_name + last_name` | dash if both null |
| Company | `companies.name` via `prospects.company_id` | dash if NULL |
| Stage chip | derived: `registered_at IS NULL ? "Partial" : (thh_user_id NULL ? "OTP requested" : "Verified")` | colour-coded; user wants leads visible with status chip, not retired — matches the `feedback_no_silent_retire` rule |
| Source chip | `source_channel` label | filterable; future-proofs for Warmly etc |
| Touches | `prospects.touch_count` | shows the dedupe-collapsed re-engagement count |
| First seen / Last seen | `first_touched_at` / `last_touched_at` | IST display |
| Owner | `admin_users.first_name` via `owner_user_id` | reassignable per existing prospect detail page |

### 6.3 Filters / source bifurcation

Source-chip filter at the top of the list. Default = all. Multi-select: `hh_signup`, `warmly`, `apollo`, etc. The filter is server-side via `?source_channel=<csv>` so pagination is honest. This is the explicit "source button" the user asked for.

### 6.4 Detail drawer / timeline

Reuse the existing prospect detail drawer. Add a "Signups" tab populated from `signups WHERE prospect_id = X ORDER BY created_at DESC` showing one row per touch with the raw event_type chip + payload preview. This mirrors the HH-BE `lead_activities` timeline that powers the digest emails today.

## 7. RBAC

| Role | Inbound page |
|------|--------------|
| admin | full (list + assign + retire + promote) |
| growth | full |
| bdr | view + claim self |
| caller | view inbound only when owned (existing caller-scope memory holds) |
| viewer | view-only |

Same matrix the outbound Prospects board uses today — no special-casing for inbound.

## 8. Telemetry / observability

- Each `push_lead_event` call logs structured: `{event=lead_event_push, type=<event_type>, status=<2xx|fail>, latency_ms, idempotency_key}`. Reuse existing `services.common.env_helpers` logger setup.
- Per existing local-vs-prod-DB hygiene rule, the `LEADS_BASE_URL` resolves to local LEADS-BE in dev, staging in stage, prod in prod. No hardcoded URLs.

## 9. Implementation order (matches the "first till L3 then bug fix" instruction)

1. **LEADS-BE branch `feature/inbound-leads-ingest`** (this repo).
   - Enum additions in `services/common/enums.py`: CHANNELS[13]='hh_signup', SIGNUP_REQUEST_TYPES[5]='hh_signup' + SCHEMA.md sync.
   - New router `services/webhooks/inbound_thh.py` (or extend existing `services/webhooks/`).
   - New service helper `services/signups/inbound_service.py` (does the dedupe + upsert + signup-row insert + channel-junction bump).
   - Pydantic model + envelope, idempotency check via `webhook_deliveries`.
   - Tests: idempotent replay, dedupe upgrade path (Apollo→inbound), soft-delete revival, unknown email path.
2. **HH-BE side patch (no new branch in HH-BE — small, surgical, ride existing main per the `feedback_direct_to_main_workflow` if Ishank prefers; otherwise `feature/inbound-leads-push`).**
   - New `services/integrations/leads_engine.py`.
   - Patch all 13 telegram call-sites + 1 new L2 site (table §5.3).
   - Env-var additions: `LEADS_BASE_URL`, `LEADS_INBOUND_SERVICE_TOKEN`. Add to `_validate_env()` (the same pattern memory references).
3. **LEADS-FE branch `feature/inbound-leads-ingest`** (this repo's FE counterpart).
   - Sidebar item.
   - `/leads/inbound` list page.
   - Source-chip filter (server-side).
   - Detail drawer "Signups" tab.
4. **End-to-end verification** (per `feedback_thorough_testing` — full action chain, multiple roles, repeats, state persistence, console/network):
   - Local browser drive: type email → idle 5s → row appears in `/leads/inbound`. Type again → touch_count bumps, no duplicate row.
   - Submit form with name → row updates, stage chip stays "Partial".
   - Request OTP → stage chip flips to "OTP requested".
   - Verify OTP → stage chip flips to "Verified", `thh_user_id` set, `registered_at` set.
   - Repeat with same email after 1 hour → touch_count bumps but no stage regression.
   - Filter by `source_channel`: only hh_signup rows show.
   - Admin reassign owner → caller sees only their owned inbound rows.
5. **Bug-fix pass.** Whatever surfaces in (4). Land after Ishank signs off.
6. **L4 (job_posted) — separate doc, separate PR.** Will reuse `prospects.first_job_created_at` via the existing `activation_sync` worker plus a new "Jobs" tab in the detail drawer.

## 10. Decisions (locked 2026-05-11 by Ishank)

1. **L2 (`otp_requested`)** — **REVISED 2026-05-11 (later that day)**: HH-BE changes must mirror existing telegram fires only. `send_login_otp` has no telegram trigger, so introducing one purely for CRM expands HH-BE blast radius. **L2 is deferred** — neither telegram nor CRM fire on `otp_requested`. Original decision (BOTH fires) is reversed.
2. **Calendly anonymous (call-site #4)** → fires BOTH CRM and telegram. For CRM, insert a `signups` row with `email=NULL` allowed via a synthetic placeholder `anonymous+calendly+<timestamp>@thh.internal` (so the email column NOT NULL constraint still holds). Mark `payload_json.anonymous=true`. UI shows "Anonymous Calendly" with the booking URL from `source_meta`. (Ishank: own calendly during dev, swap to sales person in prod.)
3. **Backfill** → none. Forward-only cutover from the merge timestamp. If historical seed is needed later, run a one-shot script that reads `lead_activities` and POSTs to the webhook.
4. **Stage chip wording** → "Partial" / "OTP requested" / "Verified" (sales-readable, matches the L1/L2/L3 tiers without exposing internal jargon).
5. **Source filter default** → `hh_signup` only on `/leads/inbound`, source chip clearable to reveal other inbound channels (Warmly, etc).
6. **HH-BE branch** → `feature/inbound-leads-push` (14 call-site patches is too big to ride direct-to-main).

## 11. Risks

- **Webhook outage on the LEADS side**: HH-BE primary flow already wraps in try/except so OTP/signup never breaks; the worst case is a missed touch (eventually-consistent backfill can replay from `lead_activities`).
- **Token mismatch in deploy**: same failure mode as the existing `THH_INCOMING_SERVICE_TOKEN` — `_validate_env()` on the LEADS-BE side must require `THH_INBOUND_SERVICE_TOKEN` or block startup. Memory entry `feedback_leads_be_prod_env_validator` already covers the pattern; mirror it for the new token.
- **Dedupe collisions on shared inboxes** (e.g. `hr@acme.com` used by two real people): mitigated by `thh_user_id` becoming the priority key as soon as L3 fires. Pre-L3, two different people on the same email collapse to one prospect by design — same as the existing telegram behaviour.

---

**Sign-off:**
- [x] Ishank — §10 decisions locked 2026-05-11
- [x] HH-BE branch policy → `feature/inbound-leads-push`
