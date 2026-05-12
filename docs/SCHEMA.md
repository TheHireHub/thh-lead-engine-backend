# THH Lead Engine — Schema & Architecture Decisions

**Project**: THH Lead Engine (outbound growth / prospect-conversion system)
**Repos**:

- `thh-lead-engine-backend` (FastAPI + SQLAlchemy 2.0 async + MySQL + ARQ)
- `thh-lead-engine-frontend` (Next.js 15 + TypeScript + Tailwind + shadcn/ui)

**Database**: New MySQL database on the same MySQL server as `thh-backend`. Logically separate, no shared tables.

**Author**: Ishank Sharma (with Claude as co-architect)
**Date**: 2026-04-27 (revised — TINYINT migration, jobs/candidates subsystem, A/B testing in MVP, OTP-via-THH integration)
**Status**: Approved by Prateek (architecture: 2 separate apps interacting with thh-backend via API)

---

## 1. Executive Summary

The lead engine is a standalone outbound acquisition system. It pulls prospects from Apollo, presents them with personalised landing pages, captures their interest, tracks the full Cold → Curious → Interested → Trial → Converted funnel, tracks open jobs at prospect companies as sales hooks, and hands the converted ones off to thh-backend (the main THH product). It is operated only by internal THH staff (admin / growth / BDR / sales / caller / ops / viewer).

**Why this exists** — direct quote from the meeting:

> "Hamara kya hoga ki jab email bhej denge. Usmein variable already set. Har ek ka alag landing page ho jayega. Har ek prospect ka landing page alag hoga. Uske andar ek unique identifier aa jayega. Domain name ka domain name ho gaya identifier."
> — *Prateek*

**Why it is a separate app and separate database** — direct quote:

> "It will be completely different db. Completely new application. Interacting with thh via api."
> — *Prateek (2026-04-27)*

This document is the authoritative source of truth for the schema. Every table, column, and decision below is justified inline with either a meeting quote or a documented engineering rationale.

---

## 2. Architecture Overview

### Two repositories, three running services


| Component            | Repo                                        | Tech                                | Hosting (proposed)                                |
| -------------------- | ------------------------------------------- | ----------------------------------- | ------------------------------------------------- |
| Backend API          | `thh-lead-engine-backend`                   | FastAPI + SQLAlchemy 2.0 (async)    | Fly.io / Railway                                  |
| Background worker    | (same repo, separate process)               | ARQ (async Redis-backed task queue) | Fly.io / Railway                                  |
| Frontend             | `thh-lead-engine-frontend`                  | Next.js 15 App Router               | Vercel (custom domain, e.g. `try-thehirehub.com`) |
| Database             | MySQL (new database on existing THH server) | MySQL 8 InnoDB utf8mb4              | Existing THH MySQL host                           |
| Cache / queue broker | Redis                                       | —                                   | Upstash (free tier to start)                      |


### Layer rules (mirror THH's authoritative Routes / CRUD / Services pattern)

- **Routers** — single HTTP entrypoint per request; validates input via Pydantic; orchestrates CRUD + Services + Integrations; returns standard envelope `{success, message, data, error}`.
- **CRUD** — only layer permitted to import the SQLAlchemy session. Static methods, parameterised queries, no `SELECT `*. Returns dicts / Pydantic objects, never raw SQLAlchemy model instances out of the session scope.
- **Services** — heavy logic, DB-agnostic, receive data as arguments (dedupe rules, heat scoring, reply classifier, signature verification).
- **Integrations** — external API wrappers (Apollo, thh-backend, Telegram, Calendly). Same rules as Services.
- **Workers** — ARQ tasks. Same orchestration rights as Routers (call CRUD + Services + Integrations).

### Five touch points with thh-backend


| #             | Direction                 | Purpose                                                           | Frequency                      | Backend endpoint                                                                                                  |
| ------------- | ------------------------- | ----------------------------------------------------------------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 1             | lead-engine → thh-backend | Promote a converted prospect to a real THH lead                   | Manual button per prospect     | thh-backend `LeadCRUD.create_lead` (existing)                                                                     |
| 2             | lead-engine → thh-backend | Pre-import dedupe check before adding a new Apollo prospect       | During Apollo sync (every 6 h) | thh-backend `check-company-exists` (existing)                                                                     |
| 3             | lead-engine → thh-backend | Send OTP for landing page signup                                  | On signup form submit          | thh-backend `POST /api/auth/login-otp/send` (existing)                                                            |
| 4             | lead-engine → thh-backend | Verify OTP for landing page signup                                | After prospect enters OTP      | thh-backend `POST /api/auth/login-otp/verify` (existing) — on success, lead engine sets `prospects.registered_at` |
| 5             | lead-engine → thh-backend | Activation status sync (jobs + applicants per converted prospect) | Daily ARQ job                  | thh-backend `GET /api/lead-engine/activation-status?thh_user_id=X` (NEW endpoint to add)                          |
| (deferred v2) | lead-engine → thh-backend | Federated admin login via THH JWT                                 | Future                         | TBD                                                                                                               |


Outside these five calls, the systems do not talk. Lead engine survives THH downtime.

### Deliverability + sender infra (forwarded asks)

> "create a separate IP / sign up + email domain"
> — *Prateek (PDF)*

- Lead engine frontend served from a **separate domain** (e.g. `try-thehirehub.com`) to keep the brand consistent with cold-outbound emails and protect the main `thehirehub.ai` domain reputation. Configured as a Vercel custom domain.
- The **separate sending IP** ask is implementation in Apollo's sender configuration (lead engine is record-only, locked decision). Forwarded as an action to whoever administers Apollo's outbound sender setup.

---

## 3. Funnel + KPI Model (RESTRUCTURED 2026-04-28)

> "Interested is someone who has registered with us. Trial is someone who has created a job. Interested can be people who have also booked a demo so it's a superset of demo and trial. Let's do one thing — we won't keep interested. We will show 2 separate Demo and Trial. So Interested is useless."
> — *Ishank (2026-04-28, locking the new model)*

The funnel is now **5 stages + 5 independent milestones**. Stages are a linear progression. Milestones are timestamps that can fire in any order — a prospect may book a demo, then trial, then convert; OR trial first without ever booking a demo; OR convert without doing either via direct sales. Dashboards show milestone counts independently rather than treating them as stages.

### Stages (linear, mutually exclusive — `prospects.stage`)

```
Cold → Curious → Converted
                 ↘ Lost
                 ↘ Unsubscribed
```

Only 5 values:


| Int | Stage        | Definition                                                                 |
| --- | ------------ | -------------------------------------------------------------------------- |
| 0   | cold         | Outreach sent, no engagement yet                                           |
| 1   | curious      | Visited the site (any source — including Warmly-attributed company visits) |
| 2   | converted    | Paying customer                                                            |
| 3   | lost         | Manually marked dead                                                       |
| 4   | unsubscribed | Opted out                                                                  |


**Curious definition** (Ishank, 2026-04-28): *"visit means curious, anyone who comes from visiting from any marketing or anything seo so curious is visits as unique visits, some register themselves some we find out via warmly"*. Any unique visit from any marketing channel → Curious. Some prospects self-identify (signup form, email-tracked link); some are identified at company level via Warmly.

### Milestones (independent timestamps on `prospects` — fire in any order)


| Column                        | Meaning                                                            | Source                                              |
| ----------------------------- | ------------------------------------------------------------------ | --------------------------------------------------- |
| `registered_at`               | Completed OTP signup on landing page                               | Lead engine signup flow (OTP via thh-backend)       |
| `demo_booked_at`              | Scheduled a Calendly demo                                          | Calendly webhook + postMessage                      |
| `first_job_created_at`        | Created their first job inside THH (= what Prateek called "Trial") | Polled from thh-backend (activation sync, see §9.5) |
| `first_applicant_received_at` | One of their jobs got at least 1 applicant                         | Polled from thh-backend (activation sync, see §9.5) |
| `converted_at`                | Became a paying customer                                           | Set on Promote-to-THH or stage→converted            |


Plus running counts: `jobs_created_count INT`, `applicants_received_count INT`.

### KPI ownership


| What                                                 | Owner                                          | Diagnostic on flat                             |
| ---------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| (sourcing) → Cold count                              | Growth                                         | Top-of-funnel sourcing                         |
| Cold → Curious count                                 | Growth                                         | Channel / messaging                            |
| Curious → Registered / Demo Booked / First Job count | Product / Frontend (landing pages) + CSM       | Landing page / offer / CTA / onboarding motion |
| Demo Booked → Converted                              | Sales                                          | Demo / sales process                           |
| First Job → First Applicant                          | CSM                                            | Activation / job posting / distribution        |
| First Applicant → Converted                          | Sales / CSMs                                   | Conversion-to-paid motion                      |
| Converted → Retained                                 | Customer Success (separate team, out of scope) | —                                              |


### Dashboard reporting model (PENDING DEFINITION)

- Prateek explicitly asked: *"lets do a graph per day curious to [next milestone]"* — the dashboard should show daily-granularity graphs for milestone transitions, not just weekly counts. Exact graphs and which milestones to chart is **PENDING USER INPUT**.
- *"Total new is a marketing KPI"* — definition is **PENDING USER INPUT**. Likely lives on a marketing-scoped view, separate from funnel.

---

## 4. User Roles

> "Toh hamare agents, hamare in-house BDR will do it."
> — *Prateek*

> "calls → RBAC for our callers ... → No Reminders"
> — *Prateek (PDF)*

> "wouldn't this be a specific page for ops or as I would call it CSM?"
> — *Ishank (2026-04-28, locking ops → csm rename)*

Internal-only at MVP. Seven roles in `admin_users.role` (TINYINT UNSIGNED — see Enum Reference §6.1):


| Int | Role     | Purpose                                                                                                                       |
| --- | -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 0   | `admin`  | Founder / Ishank / Prateek tier. Full access including settings, integrations, role management.                               |
| 1   | `growth` | Owns Cold and Curious metrics. Manages campaigns and channel mix.                                                             |
| 2   | `bdr`    | Works prospects through stages, owns assignments, fields ambiguous replies.                                                   |
| 3   | `sales`  | Handles Demo Booked → Converted handoff.                                                                                      |
| 4   | `caller` | Outbound call team. RBAC-isolated per Prateek; excluded from reminder notifications. Sees only "Next prospect" UI (see §5.4). |
| 5   | `csm`    | Customer Success Manager. Owns Job Distribution, posting helper, Jobs at Risk, candidate matches. Renamed from `ops`.         |
| 6   | `viewer` | Read-only dashboards (board, finance, observers).                                                                             |


No external/client roles; THH already owns the client-side login.

### Role → default board routing


| Role   | Default landing page          |
| ------ | ----------------------------- |
| admin  | Management (Prateek) board    |
| growth | Funnel board                  |
| bdr    | Funnel board                  |
| sales  | Sales board                   |
| caller | Caller "Next" view (see §5.4) |
| csm    | CSM board                     |
| viewer | Funnel board (read-only)      |


---

## 5. Dashboards / Boards

Four distinct board views drawn from the PDF whiteboard. Role-based default routing per §4.

### 5.1 Funnel Board (base view, available to growth/admin/bdr/viewer)

Cold / Curious / Interested / Trial / Converted counts + WoW deltas + channel breakdown. Reads from `funnel_daily_snapshots` (history) + live `prospects` query (today).

### 5.2 Management Board ("PRATEEK — ACTION & REPORTS")

> "(5) PRATEEK — ACTION & REPORTS / DECISION OF POST JOB OR NOT"
> — *Prateek (PDF)*

- Registered companies / pipeline stages
- Pipeline health
- Prospect → Trial conversion ratio
- Trial → Converted conversion ratio
- COMPANY → J1, J2, J3 grouping (companies with their open jobs nested)
- Sort job-wise / Group company-wise toggles
- Filter: Paid vs Non-Paid (job-level)
- Filter: Active vs Confidential (job-level)
- "No LinkedIn Post" badge per job

### 5.3 Sales Board

> "Total Leads | Email | LinkedIn | Demo booked | Demo given | Trials (Registrations) | OPS New / Old"
> — *Prateek (PDF)*

- Total leads count
- Email outreach count
- LinkedIn outreach count
- Demo booked / Demo given (`demo_booked` and `demo_attended` events)
- Trials (registrations) count
- OPS column: New (recently added prospects) vs Old (existing pipeline)

### 5.4 CSM Board (formerly "OPS — JOBS & CANDIDATES ONLY")

> "(4) OPS — JOBS & CANDIDATES ONLY"
> — *Prateek (PDF)* (role since renamed `ops` → `csm`)

- Lists all open `prospect_company_jobs` rows
- Per-job: candidate matches prepared count + status workflow
- Sort by job title / company / opened date / candidate count
- Group by company (collapses J1/J2/J3 under one company header)
- Filter by job status, paid_status, confidentiality
- Quick links to: Job Distribution page (post a job to boards), Posting Helper page (full field copy), Jobs at Risk view

### 5.5 Caller "Next Prospect" view

> "we will just show next next prospect and he will call and ring and no response, not interested, call back, follow up, demo scheduled if anyone is 3 times rnr then he is not interested and he will always see how many leads of callbacks and date and time for it the caller will see just next and next people to call assigned to him"
> — *Ishank (2026-04-28)*

- UI: single big "Next" button → reveals one assigned prospect at a time
- After call, caller picks an outcome (see Enum Reference §6.26):
  - RNR (Ring No Response)
  - Not Interested
  - Call Back (with date + time)
  - Follow Up
  - Demo Scheduled
- Auto-rule: 3 RNR rows for the same prospect → prospect auto-marked "Not Interested" (writes audit_log)
- Separate sub-view: list of pending callbacks owned by this caller (date + time) + running count
- No batch view, no queue UI — pure "next, next" flow

### 5.6 Job Distribution page (CSM-only)

> "when we click on post a job it will be a dropdown will see job boards, expectation, and then days to put it in at risk. for it to show up in jobs at risk it has to surpass that time he inputted ... we will be using date time even if ui takes days we convert that to hours and then use date time and save that info so future proof ... targets should be overall across all boards not board specific ... we will make at risk as total applications in system as long as that many applications have not been reached and we have crossed the time decided the job will be show in at risk as soon as that many applications are in it can never be at risk"
> — *Ishank (2026-04-28)*

- Triggered by "Post a Job" button on a `prospect_company_jobs` row (CSM-only)
- Form inputs:
  1. **Job boards** to post to (multi-select: LinkedIn, Naukri, Indeed, etc.)
  2. **Expectation / target** — single integer applied to TOTAL across all boards (e.g., 10 applicants total, NOT 10 per board)
  3. **Days threshold** for "at risk" — UI accepts days; backend converts to hours and stores as a single `at_risk_at TIMESTAMP` (= posted_at + threshold). Storing a computed datetime instead of an interval keeps the comparison trivial and lets us change UI units freely without migrating data.
- "Jobs at Risk" view: `WHERE status = open AND target_met_at IS NULL AND at_risk_at < NOW()`
- One-way ratchet: once `target_met_at` is set (the moment total applications ≥ target), the job is permanently NOT at risk — even if numbers later drop, it never re-enters at-risk.

### 5.7 Posting Helper page (CSM-only)

> "we will give all the job details that ish needs to copy on the page where we show that this jobs needs to be posted on the job board ... all fields job id company name etc etc like thh backend has for telegram message on job post"
> — *Ishank (2026-04-28)*

- Shows ALL job fields needed to copy-paste manually into external job boards (LinkedIn, Naukri, etc. — no API auto-posting in MVP)
- Field set MIRRORS thh-backend's `format_job_message()` in `services/telegram/message_formatter.py:196`:
  - **Header**: company name, main job title
  - **Job Information**: id, job_code, title, company, status, total_positions, experience_level, min_experience, max_experience
  - **Job Titles** (array)
  - **Location Details** (array): city, state, country
  - **Required Skills** (array): name, proficiency level (Beginner/Intermediate/Advanced/Expert), Required/Preferred
  - **Key Responsibilities** (array)
  - **Language Requirements** (array): name, proficiency, Required/Preferred
  - **Compensation** (array): budget type, currency, salary_min/max, variable_min/max, incentives, esops, perks
  - **Benefits & Perks** (array)
  - **Work Details**: workplace (Remote/On-site/Hybrid), employment type, search type, relocation_assistance, total_interview_rounds, reporting_to
  - **Educational Requirements** (array): level (UG/PG/PhD), degree, Required/Preferred
  - **Fields of Study** (array): value, Required/Preferred
  - **Diversity Values** (array)
  - **DEI Values** (array)
  - **Travel Requirements** (array)
  - **Team Collaborators** (array): name, designation
  - **Interview Panelists** (array): round, name, designation
  - **Evaluation Criteria** (array): name, weight%
  - **Candidate Job Description** (long text)
  - **Recruiter Job Description** (long text)
  - **Outreach Messages** (array): sequence, platform (LinkedIn/Email/Phone/Other), message
- Each field is copy-friendly (per-field copy button + "copy all" block)
- **PENDING USER INPUT** — data source for these fields: (a) lead engine stores them all locally on `prospect_company_jobs` + child tables OR (b) lead engine pulls live from thh-backend at display time. Recommendation TBD with user.

---

## 6. Enum Reference (TINYINT UNSIGNED value mappings)

**Locked decision**: All enumerated columns are stored as `TINYINT UNSIGNED NOT NULL` instead of MySQL `ENUM`. The application maintains the int → label mapping. Reasons:

1. THH already follows this pattern (`USER_TYPES = {0:'collaborator', 1:'panelist', 2:'admin', 3:'thh_admin'}`)
2. Adding new values is `INSERT` not `ALTER TABLE`
3. ORM portability is better
4. Storage is uniform (1 byte) and predictable
5. Application has the values anyway — DB-side ENUM duplicates that knowledge

This section is the single source of truth for every value mapping. Application code (`backend/app/shared/enums.py` + `frontend/src/schemas/enums.ts`) must mirror these exactly.

### 6.1 Role (`admin_users.role`)


| Int | Label  |
| --- | ------ |
| 0   | admin  |
| 1   | growth |
| 2   | bdr    |
| 3   | sales  |
| 4   | caller |
| 5   | csm    |
| 6   | viewer |


### 6.2 Funnel Stage (`prospects.stage`, `prospect_stage_history.from_stage`, `prospect_stage_history.to_stage`, `funnel_daily_snapshots.stage`) — RESTRUCTURED 2026-04-28


| Int | Label        |
| --- | ------------ |
| 0   | cold         |
| 1   | curious      |
| 2   | converted    |
| 3   | lost         |
| 4   | unsubscribed |


(Interested / Trial dropped — now milestones on `prospects` row, not stages.)

### 6.3 Channel (`prospects.source_channel`, `prospect_channels.channel`, `campaigns.channel`, `funnel_daily_snapshots.channel`)


| Int | Label       |
| --- | ----------- |
| 0   | cold_email  |
| 1   | linkedin    |
| 2   | paid        |
| 3   | seo         |
| 4   | geo         |
| 5   | brand       |
| 6   | remarketing |
| 7   | social      |
| 8   | wom         |
| 9   | apollo      |
| 10  | warmly      |
| 11  | direct      |
| 12  | other       |
| 13  | hh_signup   |


### 6.4 Company source (`companies.source`)


| Int | Label    |
| --- | -------- |
| 0   | apollo   |
| 1   | manual   |
| 2   | signup   |
| 3   | inferred |


### 6.5 Campaign status (`campaigns.status`)


| Int | Label     |
| --- | --------- |
| 0   | draft     |
| 1   | active    |
| 2   | paused    |
| 3   | completed |
| 4   | archived  |


### 6.6 Campaign-prospect status (`campaign_prospects.status`)


| Int | Label        |
| --- | ------------ |
| 0   | queued       |
| 1   | sent         |
| 2   | skipped      |
| 3   | failed       |
| 4   | unsubscribed |


### 6.7 Campaign event type (`campaign_events.event_type`)


| Int | Label                   |
| --- | ----------------------- |
| 0   | sent                    |
| 1   | delivered               |
| 2   | opened                  |
| 3   | clicked                 |
| 4   | bounced                 |
| 5   | replied_positive        |
| 6   | replied_negative        |
| 7   | unsubscribed            |
| 8   | demo_booked             |
| 9   | demo_attended           |
| 10  | demo_no_show            |
| 11  | meeting_scheduled       |
| 12  | landing_visit           |
| 13  | cr_sent                 |
| 14  | linkedin_message_sent   |
| 15  | linkedin_reply_received |
| 16  | otp_sent                |
| 17  | otp_verified            |


### 6.8 Reply classification (`email_replies.classification`)


| Int | Label    |
| --- | -------- |
| 0   | positive |
| 1   | negative |


(Binary per Prateek: *"Do hi tarah ke reply hote hain. Don't send me. Ya I am interested."*)

### 6.9 Reply classified_by (`email_replies.classified_by`)


| Int | Label  |
| --- | ------ |
| 0   | rule   |
| 1   | llm    |
| 2   | manual |


### 6.10 Note status (`prospect_notes.status`)


| Int | Label     |
| --- | --------- |
| 0   | note      |
| 1   | task_open |
| 2   | task_done |


### 6.11 Signup request_type (`signups.request_type`)


| Int | Label     |
| --- | --------- |
| 0   | demo      |
| 1   | audit     |
| 2   | signup    |
| 3   | report    |
| 4   | other     |
| 5   | hh_signup |


### 6.12 Webhook provider (`webhook_deliveries.provider`)


| Int | Label          |
| --- | -------------- |
| 0   | calendly       |
| 1   | apollo         |
| 2   | email_provider |
| 3   | other          |
| 4   | thh_signup     |


### 6.13 Webhook status (`webhook_deliveries.status`)


| Int | Label     |
| --- | --------- |
| 0   | received  |
| 1   | processed |
| 2   | failed    |
| 3   | duplicate |


### 6.14 Merge match strategy (`prospect_merge_log.match_strategy`)


| Int | Label          |
| --- | -------------- |
| 0   | linkedin_exact |
| 1   | email_exact    |
| 2   | phone_exact    |
| 3   | manual_review  |
| 4   | admin_override |


### 6.15 Merge review queue status (`prospect_merge_review_queue.status`)


| Int | Label    |
| --- | -------- |
| 0   | pending  |
| 1   | merged   |
| 2   | rejected |


### 6.16 Job seniority (`prospect_company_jobs.seniority`)


| Int | Label     |
| --- | --------- |
| 0   | unknown   |
| 1   | intern    |
| 2   | junior    |
| 3   | mid       |
| 4   | senior    |
| 5   | lead      |
| 6   | principal |
| 7   | exec      |


### 6.17 Employment type (`prospect_company_jobs.employment_type`)


| Int | Label      |
| --- | ---------- |
| 0   | unknown    |
| 1   | full_time  |
| 2   | part_time  |
| 3   | contract   |
| 4   | internship |


### 6.18 Job paid status (`prospect_company_jobs.paid_status`)


| Int | Label    |
| --- | -------- |
| 0   | unknown  |
| 1   | paid     |
| 2   | non_paid |


### 6.19 Job confidentiality (`prospect_company_jobs.confidentiality`)


| Int | Label        |
| --- | ------------ |
| 0   | active       |
| 1   | confidential |


### 6.20 Job source (`prospect_company_jobs.source`)


| Int | Label        |
| --- | ------------ |
| 0   | manual       |
| 1   | scraped      |
| 2   | apollo       |
| 3   | linkedin     |
| 4   | careers_page |
| 5   | other        |


### 6.21 Job status (`prospect_company_jobs.status`)


| Int | Label     |
| --- | --------- |
| 0   | open      |
| 1   | paused    |
| 2   | closed    |
| 3   | filled    |
| 4   | withdrawn |


### 6.22 Job-candidate match method (`prospect_company_job_candidates.match_method`)


| Int | Label      |
| --- | ---------- |
| 0   | manual     |
| 1   | auto       |
| 2   | ai_matched |


### 6.23 Job-candidate status (`prospect_company_job_candidates.status`)


| Int | Label     |
| --- | --------- |
| 0   | proposed  |
| 1   | presented |
| 2   | accepted  |
| 3   | rejected  |
| 4   | withdrawn |
| 5   | hired     |


### 6.24 Landing page variant status (`landing_page_variants.status`)


| Int | Label    |
| --- | -------- |
| 0   | active   |
| 1   | paused   |
| 2   | archived |


### 6.25 Heat level (`prospects.heat_level`)


| Int | Label |
| --- | ----- |
| 0   | cold  |
| 1   | warm  |
| 2   | hot   |


### 6.26 Call outcome (`call_logs.outcome`)


| Int | Label          |
| --- | -------------- |
| 0   | rnr            |
| 1   | not_interested |
| 2   | call_back      |
| 3   | follow_up      |
| 4   | demo_scheduled |


### 6.27 Job board (`prospect_company_job_boards.board`)


| Int | Label        |
| --- | ------------ |
| 0   | linkedin     |
| 1   | naukri       |
| 2   | indeed       |
| 3   | glassdoor    |
| 4   | monster      |
| 5   | angellist    |
| 6   | wellfound    |
| 7   | careers_page |
| 8   | other        |


### 6.28 Job board posting status (`prospect_company_job_boards.status`)


| Int | Label   |
| --- | ------- |
| 0   | pending |
| 1   | posted  |
| 2   | failed  |
| 3   | removed |


---

## 7. Schema (DDL)

All tables use **InnoDB**, **utf8mb4**, **utf8mb4_unicode_ci**. Primary keys are `BIGINT UNSIGNED AUTO_INCREMENT`. Boolean-style columns are `TINYINT UNSIGNED NOT NULL DEFAULT 0` (1 = true, 0 = false). Soft delete via `deleted_at TIMESTAMP NULL` on every business entity.

### 7.1 `admin_users`

```sql
CREATE TABLE admin_users (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email           VARCHAR(255)    NOT NULL,
    password_hash   VARCHAR(255)    NOT NULL,
    first_name      VARCHAR(100)    NOT NULL,
    last_name       VARCHAR(100)    NULL,
    role            TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.1',
    thh_user_id     BIGINT UNSIGNED NULL COMMENT 'reserved for v2 federation with thh-backend JWT',
    last_login_at   TIMESTAMP       NULL,
    deleted_at      TIMESTAMP       NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_admin_users_email (email),
    KEY idx_admin_users_role (role),
    KEY idx_admin_users_thh_user_id (thh_user_id),
    KEY idx_admin_users_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.2 `companies`

```sql
CREATE TABLE companies (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name            VARCHAR(255)    NOT NULL,
    domain          VARCHAR(255)    NULL,
    linkedin_url    VARCHAR(500)    NULL,
    industry        VARCHAR(100)    NULL,
    size            VARCHAR(50)     NULL COMMENT 'e.g. 1-10, 11-50, 51-200',
    revenue_range   VARCHAR(50)     NULL,
    funding_stage   VARCHAR(50)     NULL,
    source          TINYINT UNSIGNED NOT NULL DEFAULT 1 COMMENT 'see Enum Reference §6.4 (1=manual default)',
    enriched_at     TIMESTAMP       NULL,
    deleted_at      TIMESTAMP       NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_companies_domain (domain),
    KEY idx_companies_source (source),
    KEY idx_companies_deleted_at (deleted_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.3 `prospects`

> "What is the minimum identifier for a cold? LinkedIn URL. That's the first one. Email then phone. Minimum identifier bhi LinkedIn URL unique hota hai. ... Aur yeh ek number hoga X."
> — *Prateek*

```sql
CREATE TABLE prospects (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    linkedin_url        VARCHAR(500)    NULL,
    email               VARCHAR(255)    NULL,
    phone               VARCHAR(30)     NULL,
    first_name          VARCHAR(100)    NULL,
    last_name           VARCHAR(100)    NULL,
    title               VARCHAR(255)    NULL,
    company_id          BIGINT UNSIGNED NULL,
    stage               TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.2 (0=cold default)',
    heat_level          TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.25',
    heat_score          INT             NOT NULL DEFAULT 0 COMMENT 'engagement score; bucketed into heat_level',
    quality_score       TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'ICP fit score 0-10; computed from company + title rules',
    source_channel      TINYINT UNSIGNED NOT NULL DEFAULT 12 COMMENT 'see Enum Reference §6.3 (12=other default)',
    owner_user_id       BIGINT UNSIGNED NULL,
    apollo_contact_id   VARCHAR(100)    NULL COMMENT 'Apollo''s stable contact ID — used as upsert key',
    thh_user_id         BIGINT UNSIGNED NULL COMMENT 'set on Promote-to-THH; reverse pointer into thh-backend.users',
    first_touched_at    TIMESTAMP       NULL,
    last_touched_at     TIMESTAMP       NULL,
    touch_count         INT UNSIGNED    NOT NULL DEFAULT 0,
    -- Milestones (RESTRUCTURED 2026-04-28: independent timestamps, not stages)
    registered_at               TIMESTAMP   NULL COMMENT 'OTP signup completed via thh-backend',
    demo_booked_at              TIMESTAMP   NULL COMMENT 'Calendly demo scheduled',
    first_job_created_at        TIMESTAMP   NULL COMMENT 'created first job in THH (was "trial"); polled from thh-backend',
    first_applicant_received_at TIMESTAMP   NULL COMMENT 'first applicant received on any job; polled from thh-backend',
    converted_at                TIMESTAMP   NULL COMMENT 'became paying customer',
    jobs_created_count          INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'running total polled from thh-backend',
    applicants_received_count   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'running total polled from thh-backend',
    rnr_count                   INT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'running RNR count; auto-marks not_interested when reaches 3',
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_prospects_linkedin_url (linkedin_url),
    UNIQUE KEY uk_prospects_apollo_contact_id (apollo_contact_id),
    KEY idx_prospects_email (email),
    KEY idx_prospects_phone (phone),
    KEY idx_prospects_stage (stage),
    KEY idx_prospects_owner_user_id (owner_user_id),
    KEY idx_prospects_source_channel (source_channel),
    KEY idx_prospects_company_id (company_id),
    KEY idx_prospects_thh_user_id (thh_user_id),
    KEY idx_prospects_quality_score (quality_score),
    KEY idx_prospects_last_touched_at (last_touched_at),
    KEY idx_prospects_registered_at (registered_at),
    KEY idx_prospects_demo_booked_at (demo_booked_at),
    KEY idx_prospects_first_job_created_at (first_job_created_at),
    KEY idx_prospects_first_applicant_received_at (first_applicant_received_at),
    KEY idx_prospects_converted_at (converted_at),
    KEY idx_prospects_deleted_at (deleted_at),
    CONSTRAINT fk_prospects_company FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_prospects_owner   FOREIGN KEY (owner_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

`email` is **not** UNIQUE because (a) nullable, (b) shared inboxes exist. Dedupe enforced in application logic via priority chain (LinkedIn → email → phone, locked decision §8 Arch-Dedupe).

---

### 7.4 `prospect_channels` (junction)

```sql
CREATE TABLE prospect_channels (
    prospect_id         BIGINT UNSIGNED NOT NULL,
    channel             TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.3',
    first_touched_at    TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_touched_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    touch_count         INT UNSIGNED    NOT NULL DEFAULT 1,
    PRIMARY KEY (prospect_id, channel),
    KEY idx_prospect_channels_channel (channel),
    KEY idx_prospect_channels_last_touched_at (last_touched_at),
    CONSTRAINT fk_prospect_channels_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.5 `prospect_stage_history`

```sql
CREATE TABLE prospect_stage_history (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_id         BIGINT UNSIGNED NOT NULL,
    from_stage          TINYINT UNSIGNED NULL COMMENT 'see Enum Reference §6.2; NULL on first insert',
    to_stage            TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.2',
    reason              VARCHAR(255)    NULL,
    changed_by_user_id  BIGINT UNSIGNED NULL COMMENT 'NULL when system-driven (e.g., signup auto-promotes to interested)',
    changed_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_psh_prospect_id (prospect_id),
    KEY idx_psh_changed_at (changed_at),
    KEY idx_psh_to_stage (to_stage),
    CONSTRAINT fk_psh_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_psh_user     FOREIGN KEY (changed_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.6 `campaigns`

```sql
CREATE TABLE campaigns (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name                VARCHAR(255)    NOT NULL,
    channel             TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.3',
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.5 (0=draft default)',
    audience_filter_json JSON           NULL,
    description         TEXT            NULL,
    created_by_user_id  BIGINT UNSIGNED NOT NULL,
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_campaigns_status (status),
    KEY idx_campaigns_channel (channel),
    KEY idx_campaigns_created_by (created_by_user_id),
    KEY idx_campaigns_deleted_at (deleted_at),
    CONSTRAINT fk_campaigns_creator FOREIGN KEY (created_by_user_id) REFERENCES admin_users (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.7 `campaign_prospects` (junction)

```sql
CREATE TABLE campaign_prospects (
    campaign_id     BIGINT UNSIGNED NOT NULL,
    prospect_id     BIGINT UNSIGNED NOT NULL,
    status          TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.6 (0=queued default)',
    added_at        TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (campaign_id, prospect_id),
    KEY idx_cp_prospect_id (prospect_id),
    KEY idx_cp_status (status),
    CONSTRAINT fk_cp_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cp_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.8 `campaign_events`

```sql
CREATE TABLE campaign_events (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    campaign_id     BIGINT UNSIGNED NULL COMMENT 'NULL for one-off prospect events not tied to a campaign',
    prospect_id     BIGINT UNSIGNED NOT NULL,
    event_type      TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.7',
    payload_json    JSON            NULL,
    occurred_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_ce_prospect_id (prospect_id),
    KEY idx_ce_campaign_id (campaign_id),
    KEY idx_ce_event_type (event_type),
    KEY idx_ce_occurred_at (occurred_at),
    CONSTRAINT fk_ce_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ce_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

LinkedIn manual-logging activity types (`cr_sent`, `linkedin_message_sent`, `linkedin_reply_received`) are values 13/14/15 of §6.7 and are written by a "Log LinkedIn Activity" button on the prospect detail page.

---

### 7.9 `landing_pages`

> "Har ek prospect ka landing page alag hoga. Uske andar ek unique identifier aa jayega."
> — *Prateek*

> "(4) Pearls & Promises in 1 Page"
> — *Prateek (PDF)* — landing page design principle: single-page layout, value props + promises front and centre.

```sql
CREATE TABLE landing_pages (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    slug                VARCHAR(255)    NOT NULL,
    prospect_id         BIGINT UNSIGNED NULL COMMENT 'NULL for generic / company-only pages',
    company_id          BIGINT UNSIGNED NULL,
    template_key        VARCHAR(50)     NOT NULL DEFAULT 'classic',
    source_campaign_id  BIGINT UNSIGNED NULL,
    default_content_json JSON           NULL COMMENT 'fallback content if no active variants',
    visit_count         INT UNSIGNED    NOT NULL DEFAULT 0,
    last_visit_at       TIMESTAMP       NULL,
    created_by_user_id  BIGINT UNSIGNED NULL,
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_landing_pages_slug (slug),
    KEY idx_lp_prospect_id (prospect_id),
    KEY idx_lp_company_id (company_id),
    KEY idx_lp_source_campaign_id (source_campaign_id),
    KEY idx_lp_deleted_at (deleted_at),
    CONSTRAINT fk_lp_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_lp_company  FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_lp_campaign FOREIGN KEY (source_campaign_id) REFERENCES campaigns (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_lp_creator  FOREIGN KEY (created_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.10 `landing_page_variants` — A/B test variants per landing page

> "(5) 1st Section — Want to Test"
> — *Prateek (PDF)* — A/B testing the hero/first section of landing pages is in-scope for v1.

```sql
CREATE TABLE landing_page_variants (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    landing_page_id     BIGINT UNSIGNED NOT NULL,
    variant_key         VARCHAR(50)     NOT NULL COMMENT 'human-readable variant ID, e.g. ''hero_v1''',
    content_json        JSON            NOT NULL COMMENT 'overrides for hero text, value props, CTA copy',
    weight              SMALLINT UNSIGNED NOT NULL DEFAULT 100 COMMENT 'weighted random selection; 0 = disabled',
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.24 (0=active default)',
    visit_count         INT UNSIGNED    NOT NULL DEFAULT 0,
    signup_count        INT UNSIGNED    NOT NULL DEFAULT 0,
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_lpv_page_variant (landing_page_id, variant_key),
    KEY idx_lpv_status (status),
    KEY idx_lpv_deleted_at (deleted_at),
    CONSTRAINT fk_lpv_page FOREIGN KEY (landing_page_id) REFERENCES landing_pages (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.11 `landing_page_visits`

```sql
CREATE TABLE landing_page_visits (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    landing_page_id     BIGINT UNSIGNED NOT NULL,
    landing_page_variant_id BIGINT UNSIGNED NULL COMMENT 'which A/B variant was shown',
    prospect_id         BIGINT UNSIGNED NULL COMMENT 'NULL for anonymous; backfilled on signup',
    visitor_id          VARCHAR(64)     NOT NULL COMMENT 'cookie-based stable ID for anonymous→identified backfill',
    ip_hash             VARCHAR(64)     NULL COMMENT 'sha256(ip + secret) — never raw IP',
    user_agent          TEXT            NULL,
    referrer            VARCHAR(500)    NULL,
    utm_source          VARCHAR(100)    NULL,
    utm_medium          VARCHAR(100)    NULL,
    utm_campaign        VARCHAR(100)    NULL,
    utm_content         VARCHAR(100)    NULL,
    utm_term            VARCHAR(100)    NULL,
    visited_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_lpv_landing_page_id (landing_page_id),
    KEY idx_lpv_variant_id (landing_page_variant_id),
    KEY idx_lpv_prospect_id (prospect_id),
    KEY idx_lpv_visitor_id (visitor_id),
    KEY idx_lpv_visited_at (visited_at),
    CONSTRAINT fk_lpvis_landing_page FOREIGN KEY (landing_page_id) REFERENCES landing_pages (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_lpvis_variant      FOREIGN KEY (landing_page_variant_id) REFERENCES landing_page_variants (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_lpvis_prospect     FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.12 `signups`

```sql
CREATE TABLE signups (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    landing_page_id     BIGINT UNSIGNED NULL,
    prospect_id         BIGINT UNSIGNED NULL COMMENT 'set after upsert via dedupe rules',
    email               VARCHAR(255)    NOT NULL,
    name                VARCHAR(255)    NULL,
    company_name        VARCHAR(255)    NULL,
    domain              VARCHAR(255)    NULL,
    phone               VARCHAR(30)     NULL,
    request_type        TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.11 (0=demo default)',
    payload_json        JSON            NULL,
    visitor_id          VARCHAR(64)     NULL COMMENT 'links to landing_page_visits for backfill',
    otp_verified_at     TIMESTAMP       NULL COMMENT 'set when prospect completes OTP via thh-backend; triggers stage→interested',
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_signups_email (email),
    KEY idx_signups_landing_page_id (landing_page_id),
    KEY idx_signups_prospect_id (prospect_id),
    KEY idx_signups_visitor_id (visitor_id),
    KEY idx_signups_created_at (created_at),
    CONSTRAINT fk_signups_landing_page FOREIGN KEY (landing_page_id) REFERENCES landing_pages (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_signups_prospect     FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.13 `email_replies`

> "Do hi tarah ke reply hote hain. Don't send me. Ya I am interested. Yeh to seedhe demo book kar denge uske saath jo I am interested wala hai."
> — *Prateek*

```sql
CREATE TABLE email_replies (
    id                      BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    campaign_id             BIGINT UNSIGNED NULL,
    prospect_id             BIGINT UNSIGNED NOT NULL,
    raw_body                TEXT            NOT NULL,
    subject                 VARCHAR(500)    NULL,
    classification          TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.8 (binary per Prateek)',
    classified_by           TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.9 (0=rule default)',
    classifier_confidence   DECIMAL(4,3)    NULL,
    received_at             TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_er_prospect_id (prospect_id),
    KEY idx_er_campaign_id (campaign_id),
    KEY idx_er_classification (classification),
    KEY idx_er_received_at (received_at),
    CONSTRAINT fk_er_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_er_campaign FOREIGN KEY (campaign_id) REFERENCES campaigns (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.14 `unsubscribes`

```sql
CREATE TABLE unsubscribes (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email               VARCHAR(255)    NOT NULL,
    prospect_id         BIGINT UNSIGNED NULL,
    source_campaign_id  BIGINT UNSIGNED NULL,
    reason              VARCHAR(255)    NULL,
    unsubscribed_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_unsubscribes_email (email),
    KEY idx_unsubscribes_prospect_id (prospect_id),
    KEY idx_unsubscribes_source_campaign_id (source_campaign_id),
    CONSTRAINT fk_unsub_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_unsub_campaign FOREIGN KEY (source_campaign_id) REFERENCES campaigns (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.15 `prospect_notes`

```sql
CREATE TABLE prospect_notes (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_id         BIGINT UNSIGNED NOT NULL,
    body                TEXT            NOT NULL,
    assigned_to_user_id BIGINT UNSIGNED NULL COMMENT 'set when this is a task, not a free-form note',
    due_date            DATE            NULL,
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.10 (0=note default)',
    created_by_user_id  BIGINT UNSIGNED NOT NULL,
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pn_prospect_id (prospect_id),
    KEY idx_pn_assigned (assigned_to_user_id),
    KEY idx_pn_status (status),
    KEY idx_pn_due_date (due_date),
    KEY idx_pn_deleted_at (deleted_at),
    CONSTRAINT fk_pn_prospect  FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pn_assigned  FOREIGN KEY (assigned_to_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_pn_creator   FOREIGN KEY (created_by_user_id) REFERENCES admin_users (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.16 `audit_log`

```sql
CREATE TABLE audit_log (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    actor_user_id   BIGINT UNSIGNED NULL COMMENT 'NULL for system actions (worker, webhook)',
    entity_type     VARCHAR(50)     NOT NULL COMMENT 'e.g. prospect, campaign, landing_page, admin_user, prospect_company_job',
    entity_id       BIGINT UNSIGNED NULL,
    action          VARCHAR(100)    NOT NULL COMMENT 'e.g. create, update, delete, stage_change, reassign, promote_to_thh, gdpr_erase, job_close',
    before_json     JSON            NULL,
    after_json      JSON            NULL,
    ip_address      VARCHAR(45)     NULL,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_audit_entity (entity_type, entity_id),
    KEY idx_audit_actor (actor_user_id),
    KEY idx_audit_action (action),
    KEY idx_audit_created_at (created_at),
    CONSTRAINT fk_audit_actor FOREIGN KEY (actor_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.17 `funnel_daily_snapshots`

```sql
CREATE TABLE funnel_daily_snapshots (
    id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    snapshot_date   DATE            NOT NULL,
    stage           TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.2',
    channel         TINYINT UNSIGNED NULL COMMENT 'see Enum Reference §6.3; NULL for all-channel rollups',
    owner_user_id   BIGINT UNSIGNED NULL,
    prospect_count  INT UNSIGNED    NOT NULL DEFAULT 0,
    created_at      TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_fds_dimension (snapshot_date, stage, channel, owner_user_id),
    KEY idx_fds_snapshot_date (snapshot_date),
    KEY idx_fds_stage (stage),
    CONSTRAINT fk_fds_owner FOREIGN KEY (owner_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

The unique key on `(snapshot_date, stage, channel, owner_user_id)` lets the worker `INSERT ... ON DUPLICATE KEY UPDATE` to make the snapshot job idempotent.

---

### 7.18 `webhook_deliveries`

```sql
CREATE TABLE webhook_deliveries (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    provider            TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.12',
    external_event_id   VARCHAR(255)    NOT NULL COMMENT 'provider-supplied event ID',
    signature           VARCHAR(255)    NULL,
    payload_json        JSON            NOT NULL,
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.13 (0=received default)',
    error_message       TEXT            NULL,
    received_at         TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at        TIMESTAMP       NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_wd_provider_event (provider, external_event_id),
    KEY idx_wd_status (status),
    KEY idx_wd_received_at (received_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.19 `prospect_merge_log`

```sql
CREATE TABLE prospect_merge_log (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    kept_prospect_id    BIGINT UNSIGNED NOT NULL,
    merged_prospect_id  BIGINT UNSIGNED NOT NULL COMMENT 'no FK — the merged row may be hard-deleted post-merge',
    match_strategy      TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.14',
    merged_by_user_id   BIGINT UNSIGNED NULL COMMENT 'NULL for auto-merge by system',
    snapshot_json       JSON            NULL COMMENT 'snapshot of merged_prospect at merge time',
    merged_at           TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pml_kept (kept_prospect_id),
    KEY idx_pml_merged_by (merged_by_user_id),
    KEY idx_pml_merged_at (merged_at),
    CONSTRAINT fk_pml_kept     FOREIGN KEY (kept_prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pml_merged_by FOREIGN KEY (merged_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.20 `prospect_merge_review_queue`

```sql
CREATE TABLE prospect_merge_review_queue (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_a_id       BIGINT UNSIGNED NOT NULL,
    prospect_b_id       BIGINT UNSIGNED NOT NULL,
    match_score         DECIMAL(4,3)    NOT NULL COMMENT '0.000 - 1.000',
    match_reason        VARCHAR(255)    NOT NULL COMMENT 'e.g. domain_and_lastname, fuzzy_name_company',
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.15 (0=pending default)',
    reviewed_by_user_id BIGINT UNSIGNED NULL,
    reviewed_at         TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pmrq_status (status),
    KEY idx_pmrq_created_at (created_at),
    KEY idx_pmrq_prospect_a (prospect_a_id),
    KEY idx_pmrq_prospect_b (prospect_b_id),
    CONSTRAINT fk_pmrq_a        FOREIGN KEY (prospect_a_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pmrq_b        FOREIGN KEY (prospect_b_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pmrq_reviewer FOREIGN KEY (reviewed_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.21 `prospect_company_jobs` — open jobs at prospect companies (sales hooks)

> "(4) OPS — JOBS & CANDIDATES ONLY" + "COMPANY → J1, J2, J3" + "SORTING JOB WISE / GROUPING COMPANY WISE / PAID & NON PAID MAIN / (6) ACTIVE VS CONFIDENTIAL / NO LINKEDIN POST BUTTON"
> — *Prateek (PDF)*

```sql
CREATE TABLE prospect_company_jobs (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    company_id          BIGINT UNSIGNED NOT NULL,
    title               VARCHAR(255)    NOT NULL,
    department          VARCHAR(100)    NULL,
    seniority           TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.16 (0=unknown default)',
    location            VARCHAR(255)    NULL,
    employment_type     TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.17 (0=unknown default)',
    open_count          INT UNSIGNED    NOT NULL DEFAULT 1,
    paid_status         TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.18 (0=unknown default)',
    confidentiality     TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.19 (0=active default)',
    no_linkedin_post    TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '1=do not post to LinkedIn, 0=allowed',
    source              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.20 (0=manual default)',
    source_url          VARCHAR(500)    NULL,
    source_external_id  VARCHAR(255)    NULL,
    status              TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.21 (0=open default)',
    candidates_prepared INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'denormalised count from prospect_company_job_candidates',
    jd_url              VARCHAR(500)    NULL,
    notes               TEXT            NULL,
    -- Job Distribution / At-Risk fields (added 2026-04-28)
    posted_at           TIMESTAMP       NULL COMMENT 'when CSM clicked "Post a Job" and distribution was launched',
    expectation_target  INT UNSIGNED    NULL COMMENT 'total applicants expected across all boards combined',
    at_risk_at          TIMESTAMP       NULL COMMENT 'absolute datetime after which this job is at risk if target not met (= posted_at + threshold; UI takes days, backend stores datetime)',
    target_met_at       TIMESTAMP       NULL COMMENT 'set the moment total_applicants >= target; once set, never resets — one-way ratchet',
    total_applicants    INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'aggregate applicant count across all boards (denormalised)',
    assigned_to_csm_user_id BIGINT UNSIGNED NULL COMMENT 'CSM responsible for this job',
    opened_at           TIMESTAMP       NULL,
    closed_at           TIMESTAMP       NULL,
    created_by_user_id  BIGINT UNSIGNED NULL,
    deleted_at          TIMESTAMP       NULL,
    created_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pcj_source_external (source, source_external_id),
    KEY idx_pcj_company_id (company_id),
    KEY idx_pcj_status (status),
    KEY idx_pcj_paid_status (paid_status),
    KEY idx_pcj_confidentiality (confidentiality),
    KEY idx_pcj_department (department),
    KEY idx_pcj_seniority (seniority),
    KEY idx_pcj_source (source),
    KEY idx_pcj_no_linkedin_post (no_linkedin_post),
    KEY idx_pcj_at_risk_at (at_risk_at),
    KEY idx_pcj_target_met_at (target_met_at),
    KEY idx_pcj_assigned_csm (assigned_to_csm_user_id),
    KEY idx_pcj_deleted_at (deleted_at),
    CONSTRAINT fk_pcj_company FOREIGN KEY (company_id) REFERENCES companies (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pcj_creator FOREIGN KEY (created_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_pcj_assigned_csm FOREIGN KEY (assigned_to_csm_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.22 `prospect_company_job_candidates` — candidate matches per open job

```sql
CREATE TABLE prospect_company_job_candidates (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_company_job_id     BIGINT UNSIGNED NOT NULL,
    thh_candidate_id            BIGINT UNSIGNED NULL COMMENT 'cross-DB pointer to thh-backend candidate; NULL if external/manual',
    candidate_name              VARCHAR(255)    NOT NULL COMMENT 'denormalised snapshot for fast list rendering',
    candidate_title             VARCHAR(255)    NULL,
    candidate_linkedin_url      VARCHAR(500)    NULL,
    candidate_summary           TEXT            NULL,
    match_score                 DECIMAL(4,3)    NULL COMMENT '0.000 - 1.000',
    match_method                TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.22 (0=manual default)',
    match_notes                 TEXT            NULL,
    status                      TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.23 (0=proposed default)',
    presented_to_prospect_id    BIGINT UNSIGNED NULL,
    presented_at                TIMESTAMP       NULL,
    decided_at                  TIMESTAMP       NULL,
    decision_notes              TEXT            NULL,
    prepared_by_user_id         BIGINT UNSIGNED NOT NULL,
    deleted_at                  TIMESTAMP       NULL,
    created_at                  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pcjc_job_id (prospect_company_job_id),
    KEY idx_pcjc_thh_candidate_id (thh_candidate_id),
    KEY idx_pcjc_status (status),
    KEY idx_pcjc_presented_to (presented_to_prospect_id),
    KEY idx_pcjc_prepared_by (prepared_by_user_id),
    KEY idx_pcjc_deleted_at (deleted_at),
    CONSTRAINT fk_pcjc_job          FOREIGN KEY (prospect_company_job_id) REFERENCES prospect_company_jobs (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pcjc_presented_to FOREIGN KEY (presented_to_prospect_id) REFERENCES prospects (id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_pcjc_prepared_by  FOREIGN KEY (prepared_by_user_id) REFERENCES admin_users (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.23 `prospect_company_job_history` — job field-change audit

```sql
CREATE TABLE prospect_company_job_history (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_company_job_id     BIGINT UNSIGNED NOT NULL,
    field_name                  VARCHAR(100)    NOT NULL COMMENT 'e.g. status, paid_status, confidentiality, no_linkedin_post',
    from_value                  VARCHAR(255)    NULL,
    to_value                    VARCHAR(255)    NULL,
    reason                      VARCHAR(255)    NULL,
    changed_by_user_id          BIGINT UNSIGNED NULL,
    changed_at                  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_pcjh_job_id (prospect_company_job_id),
    KEY idx_pcjh_changed_at (changed_at),
    KEY idx_pcjh_field_name (field_name),
    CONSTRAINT fk_pcjh_job  FOREIGN KEY (prospect_company_job_id) REFERENCES prospect_company_jobs (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pcjh_user FOREIGN KEY (changed_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.24 `prospect_company_job_boards` — junction of job × board with per-board posting status

**Why**: a job posts to multiple boards; each board has its own posting state (pending/posted/failed/removed) and its own applicant counter. Aggregate counter on `prospect_company_jobs.total_applicants` is the sum.

```sql
CREATE TABLE prospect_company_job_boards (
    id                          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_company_job_id     BIGINT UNSIGNED NOT NULL,
    board                       TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.27',
    status                      TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT 'see Enum Reference §6.28 (0=pending default)',
    external_url                VARCHAR(500)    NULL COMMENT 'URL of the live posting on this board, once posted',
    posted_at                   TIMESTAMP       NULL,
    removed_at                  TIMESTAMP       NULL,
    applicant_count             INT UNSIGNED    NOT NULL DEFAULT 0 COMMENT 'applicants attributed to this board',
    notes                       TEXT            NULL,
    posted_by_user_id           BIGINT UNSIGNED NULL,
    deleted_at                  TIMESTAMP       NULL,
    created_at                  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_pcjb_job_board (prospect_company_job_id, board),
    KEY idx_pcjb_status (status),
    KEY idx_pcjb_board (board),
    KEY idx_pcjb_posted_at (posted_at),
    KEY idx_pcjb_deleted_at (deleted_at),
    CONSTRAINT fk_pcjb_job  FOREIGN KEY (prospect_company_job_id) REFERENCES prospect_company_jobs (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_pcjb_user FOREIGN KEY (posted_by_user_id) REFERENCES admin_users (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### 7.25 `call_logs` — every caller call outcome

> "we will just show next next prospect and he will call and ring and no response, not interested, call back, follow up, demo scheduled if anyone is 3 times rnr then he is not interested"
> — *Ishank (2026-04-28)*

**Why**: powers the Caller "Next" view, the callbacks sub-view, the auto-3xRNR-marker rule, and the historical record of every caller interaction.

```sql
CREATE TABLE call_logs (
    id                  BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    prospect_id         BIGINT UNSIGNED NOT NULL,
    caller_user_id      BIGINT UNSIGNED NOT NULL,
    outcome             TINYINT UNSIGNED NOT NULL COMMENT 'see Enum Reference §6.26',
    callback_at         TIMESTAMP       NULL COMMENT 'set when outcome=call_back; the date+time the prospect asked us to call back',
    notes               TEXT            NULL,
    called_at           TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_cl_prospect_id (prospect_id),
    KEY idx_cl_caller_user_id (caller_user_id),
    KEY idx_cl_outcome (outcome),
    KEY idx_cl_callback_at (callback_at),
    KEY idx_cl_called_at (called_at),
    CONSTRAINT fk_cl_prospect FOREIGN KEY (prospect_id) REFERENCES prospects (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_cl_caller   FOREIGN KEY (caller_user_id) REFERENCES admin_users (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

The 3×RNR auto-marker is a service rule: on every `call_logs` insert, if `outcome=rnr`, increment `prospects.rnr_count`; if `rnr_count >= 3`, write `audit_log` (`action=auto_marked_not_interested`) and update prospect (mark via a milestone column or stage move — final mechanism TBD).

---

## 8. Architecture Decisions Journal — every choice with proof


| #       | Decision                                                                                                                                                                                                                                                                                                                                                                                                                 | Reason                                                                                                                                                                                                                                            | Proof                                                                                                                                                                                                                                                                                                          |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Arch-1  | Two separate repos: `thh-lead-engine-backend` + `thh-lead-engine-frontend`. New MySQL database, not new tables in `thh-backend`.                                                                                                                                                                                                                                                                                         | Independent deploy, independent failure domain, no schema pollution.                                                                                                                                                                              | Prateek (2026-04-27): *"It will be completely different db. Completely new application. Interacting with thh via api."*                                                                                                                                                                                        |
| Arch-2  | Backend stack: FastAPI + SQLAlchemy 2.0 (async) + Alembic.                                                                                                                                                                                                                                                                                                                                                               | Aligns with where THH itself is heading (`feature/sqlalchemy-migration` branch). Async-native matches the worker stack.                                                                                                                           | Ishank (2026-04-27): *"go fast api"* + *"we will use an orm for thsi no raw queries right?"* → SQLAlchemy 2.0 + Alembic locked. THH backend recon confirmed SQLAlchemy migration in flight.                                                                                                                    |
| Arch-3  | Database: MySQL 8 (new database on the existing THH MySQL server).                                                                                                                                                                                                                                                                                                                                                       | Reuse infra (one MySQL host) while staying logically separate (different database = different schema in MySQL terms).                                                                                                                             | Ishank (2026-04-27): *"i'll keep it mysql only for reusability i'll just make a new schema in the same db"*                                                                                                                                                                                                    |
| Arch-4  | User roles: 7 values (admin, growth, bdr, sales, caller, ops, viewer). Internal-only.                                                                                                                                                                                                                                                                                                                                    | Mirrors funnel ownership + PDF call for separate caller and ops roles.                                                                                                                                                                            | Prateek: *"Toh hamare agents, hamare in-house BDR will do it."* + PDF: *"calls → RBAC for our callers"* + *"OPS — JOBS & CANDIDATES ONLY"*                                                                                                                                                                     |
| Arch-5  | Funnel stages: 9 values (cold, curious, interested_cold/warm/hot, **trial**, converted, lost, unsubscribed).                                                                                                                                                                                                                                                                                                             | Verbatim from Prateek's stage list + Trial stage from PDF.                                                                                                                                                                                        | Prateek: *"Sabse pehle status cold. Second curious. Third interested. ... Interested cold. Interested hot. ... Then finally converted."* + PDF: *"Trial = Lead = Demo scheduled"* + dashboard KPIs *"Prospect to trial"* and *"Trial to converted"*                                                            |
| Arch-6  | Identifier priority: LinkedIn URL → email → phone. Internal `prospects.id` is the system ID.                                                                                                                                                                                                                                                                                                                             | Prateek's explicit ranking.                                                                                                                                                                                                                       | Prateek: *"What is the minimum identifier for a cold? LinkedIn URL. That's the first one. Email then phone. ... Aur yeh ek number hoga X."*                                                                                                                                                                    |
| Arch-7  | Per-channel touch tracking via junction table (`prospect_channels`), not boolean columns.                                                                                                                                                                                                                                                                                                                                | Junction lets new channels be added without `ALTER TABLE`.                                                                                                                                                                                        | Prateek: *"Email campaign yes/no. LinkedIn. Brand guide yes/no. Then your remarketing. Social media. ... Isliye ismein har ek future ke zaroorat hoga usmein ek column hoga."*                                                                                                                                 |
| Arch-8  | Channel set: 13 values including `**geo*`* (Generative Engine Optimization) and `**warmly**` (Warmly.ai ABM/intent vendor).                                                                                                                                                                                                                                                                                              | Both explicitly drawn on the PDF traffic taxonomy.                                                                                                                                                                                                | PDF top-row: *"SEO / GEO ... Paid ... Brand ... Outbound ... Remarketing ... Warmly"*                                                                                                                                                                                                                          |
| Arch-9  | Landing pages identified by slug. Personalisation via URL query params (`?email=`, `?pid=`).                                                                                                                                                                                                                                                                                                                             | Prateek's "har ek prospect ka landing page alag hoga" + standard B2B outbound link pattern.                                                                                                                                                       | Prateek: *"Hamara kya hoga ki jab email bhej denge. Usmein variable already set. Har ek ka alag landing page ho jayega."*                                                                                                                                                                                      |
| Arch-10 | Anonymous → identified backfill via cookie `visitor_id` linked at signup.                                                                                                                                                                                                                                                                                                                                                | Standard pattern (Segment, PostHog, Mixpanel). Solves the "anonymously aa raha hai to woh nahi" gap Prateek named.                                                                                                                                | Prateek: *"If anonymously aa raha hai to woh nahi (track ho raha hoga). Click karke aa raha hai to directly capture ho jayega."*                                                                                                                                                                               |
| Arch-11 | Reply classification is binary: `positive` or `negative`. No `neutral`.                                                                                                                                                                                                                                                                                                                                                  | Honour Prateek's framing. Trade-off mitigated by manual override button.                                                                                                                                                                          | Prateek: *"Do hi tarah ke reply hote hain. Don't send me. Ya I am interested."* + Ishank lock: *"honor prateek"*                                                                                                                                                                                               |
| Arch-12 | Apollo sync: pull-based, every 6 hours. Upsert by `apollo_contact_id`.                                                                                                                                                                                                                                                                                                                                                   | Apollo webhooks are flaky; pull is predictable and idempotent.                                                                                                                                                                                    | Prateek: *"Apollo.io se humein milti hai official leads."* + Ishank lock: *"sure why not"*.                                                                                                                                                                                                                    |
| Arch-13 | Calendly: reuse THH's `react-calendly` widget (postMessage) + add Calendly's server-side webhook for reliability. Separate Calendly event URL for lead engine.                                                                                                                                                                                                                                                           | THH already wires `react-calendly` but only via postMessage — bookings are lost if browser closes before success page renders. Webhook closes the gap.                                                                                            | Recon of `thh-frontend/src/components/CalendlyBookingButton.tsx` and `thh-backend/services/user/routes.py:1664-1726`.                                                                                                                                                                                          |
| Arch-14 | Webhook security: HMAC-SHA256 signature per request + 5-minute timestamp window for replay protection + `webhook_deliveries` idempotency table.                                                                                                                                                                                                                                                                          | Industry standard (Stripe, GitHub, Slack pattern).                                                                                                                                                                                                | Ishank lock: *"yes"* (after walkthrough of HMAC + 5-minute timestamp window + dedupe table mechanism).                                                                                                                                                                                                         |
| Arch-15 | Conversion handoff to thh-backend: manual "Promote to THH" button, not automatic on stage change.                                                                                                                                                                                                                                                                                                                        | Auto-fire creates ghost leads when someone misclicks. Manual button = clear audit trail.                                                                                                                                                          | Ishank lock: *"yes"* (chose manual button over auto-fire on stage change).                                                                                                                                                                                                                                     |
| Arch-16 | OTP verification on landing page signup uses thh-backend's existing OTP API (`POST /api/auth/login-otp/send` + `verify`). Successful verify auto-promotes prospect stage to `interested`.                                                                                                                                                                                                                                | Reuse existing infra; matches Prateek's "OTP = interested" mapping.                                                                                                                                                                               | PDF: *"OTP = interested"* + recon of thh-backend OTP endpoints.                                                                                                                                                                                                                                                |
| Arch-17 | Background job runner: ARQ (async, Redis-backed).                                                                                                                                                                                                                                                                                                                                                                        | Async-native (matches FastAPI), tiny API, scales to thousands of jobs/min.                                                                                                                                                                        | Ishank lock: *"yes"* (after explanation of why background jobs are required for Apollo sync, snapshots, webhook async-processing, heat recalc).                                                                                                                                                                |
| Arch-18 | Audit log: ONE generic `audit_log` table for all entities.                                                                                                                                                                                                                                                                                                                                                               | One query for "what did this user touch this week"; trivial SOC2/compliance later.                                                                                                                                                                | Ishank lock: *"yes"* (chose one generic table over THH's per-entity audit pattern).                                                                                                                                                                                                                            |
| Arch-19 | Soft delete via `deleted_at` timestamp on every business entity. Hard delete only via dedicated GDPR-erase endpoint.                                                                                                                                                                                                                                                                                                     | 99% of "deletes" are mistakes — undelete is critical. Timestamp is free metadata over `is_active`.                                                                                                                                                | Ishank lock: *"deleted at"* (chose timestamp over `is_active` boolean after side-by-side comparison).                                                                                                                                                                                                          |
| Arch-20 | Funnel snapshot table (`funnel_daily_snapshots`) populated nightly by ARQ.                                                                                                                                                                                                                                                                                                                                               | Sub-100ms dashboard at any size; decouples reporting from OLTP.                                                                                                                                                                                   | Prateek: *"Ab basically we will talk to you about the cold and curious number week on week"* + Ishank lock: *"yes"*.                                                                                                                                                                                           |
| Arch-21 | Heat scoring: code-defined rule (open=+1, click=+2, visit-no-signup=+3, positive-reply=+5; bucket 0-2 cold / 3-7 warm / 8+ hot).                                                                                                                                                                                                                                                                                         | Trivial to reason about, recalculable from events.                                                                                                                                                                                                | Ishank lock: *"yes"* (default point values approved, tunable later).                                                                                                                                                                                                                                           |
| Arch-22 | **Quality score** column on `prospects` (TINYINT 0-10), separate from heat score.                                                                                                                                                                                                                                                                                                                                        | Heat measures engagement (behaviour); quality measures fit (ICP). PDF lists Quality as a top-4 KPI.                                                                                                                                               | PDF top-left: *"To make a panel: 1) Keyword List Rank 2) Traffic 3) Lead 4) Quality"*                                                                                                                                                                                                                          |
| Arch-23 | Frontend auth: JWT in httpOnly + Secure + SameSite=Lax cookie. Never localStorage.                                                                                                                                                                                                                                                                                                                                       | localStorage is readable by any XSS bug; admin tool with full prospect-DB access cannot afford that risk.                                                                                                                                         | Ishank lock: explicitly chose Option B (httpOnly cookie) over localStorage; declined adding 2FA in v1.                                                                                                                                                                                                         |
| Arch-24 | Frontend state: Tanstack Query for server state + plain `useState` for local UI state.                                                                                                                                                                                                                                                                                                                                   | Industry standard for API-driven apps; built-in caching, revalidation, optimistic updates.                                                                                                                                                        | Ishank lock: *"yes"* (after walkthrough of caching/revalidation/optimistic-updates rationale).                                                                                                                                                                                                                 |
| Arch-25 | Landing page templates: code-defined React components keyed by `template_key`; per-page content stored in `landing_pages.default_content_json`.                                                                                                                                                                                                                                                                          | Type-safe, fast iteration, version-controlled.                                                                                                                                                                                                    | Ishank lock: *"yes"* (chose code-defined React components over DB-driven CMS approach).                                                                                                                                                                                                                        |
| Arch-26 | Compliance: GDPR + CAN-SPAM from day one. Unsubscribe link on every email, List-Unsubscribe header, right-to-delete endpoint, retention policy doc.                                                                                                                                                                                                                                                                      | One accidental EU-domain email = lawsuit risk.                                                                                                                                                                                                    | Ishank lock: *"yes"* (full GDPR + CAN-SPAM from day one — covers EU + US prospects).                                                                                                                                                                                                                           |
| Arch-27 | Auto-generate TypeScript types in the frontend from FastAPI's OpenAPI spec via `openapi-typescript`.                                                                                                                                                                                                                                                                                                                     | Single source of truth (Pydantic schema) — frontend gets compile errors anywhere it's wrong.                                                                                                                                                      | Ishank lock: *"yes"* (chose auto-codegen TS types over manual hand-written types).                                                                                                                                                                                                                             |
| Arch-28 | Telegram alerts on a separate channel from THH (same bot or new one).                                                                                                                                                                                                                                                                                                                                                    | Growth team wants its own feed without polluting THH's existing alerts.                                                                                                                                                                           | Recon + Ishank decision.                                                                                                                                                                                                                                                                                       |
| Arch-29 | **TINYINT UNSIGNED everywhere instead of MySQL ENUM.** Application code holds the int↔label mapping; this doc is the single source of truth (§6).                                                                                                                                                                                                                                                                        | Matches THH's existing pattern (`USER_TYPES = {0:..., 1:..., 2:...}`). New values = `INSERT` not `ALTER TABLE`. Better ORM portability. Predictable 1-byte storage.                                                                               | Ishank (2026-04-27): *"we wont use enums at all we will always use tiny ints everywhere fix that please everywhere across the documentation and more"*                                                                                                                                                         |
| Arch-30 | LinkedIn outreach activity logged manually via UI button on prospect detail page; writes to `campaign_events` with event_type 13/14/15. AI agent for auto-logging deferred to v2.                                                                                                                                                                                                                                        | Manual covers v1 use case; agent endpoint can be added later without schema change.                                                                                                                                                               | PDF: *"Claude integration that updates CRM of all developments — CR sent / messages sent / Reverts"* + Ishank: *"this thing we wont be doing from the start its future scope as such make a manual way to do this if possible"*                                                                                |
| Arch-31 | **Hero-section A/B testing in MVP scope** via `landing_page_variants` table + weighted random assignment service.                                                                                                                                                                                                                                                                                                        | Prateek explicitly named "1st Section — Want to Test" on PDF; schema is cheap and the feature is small.                                                                                                                                           | PDF: *"(5) 1st Section — Want to Test"* + Ishank lock: *"yes we wil ship it part of current project"*                                                                                                                                                                                                          |
| Arch-32 | **"Pearls & Promises in 1 Page"** documented as the landing page design principle: single-page layout, value props + promises front and centre.                                                                                                                                                                                                                                                                          | Codifies a content design rule from the PDF.                                                                                                                                                                                                      | PDF: *"(4) Pearls & Promises in 1 Page"*                                                                                                                                                                                                                                                                       |
| Arch-33 | **Custom domain on Vercel** (e.g. `try-thehirehub.com`) for the lead engine frontend, separate from `thehirehub.ai`. Separate-IP/sender-config ask forwarded to whoever administers Apollo's outbound sender setup.                                                                                                                                                                                                      | Brand consistency with cold-outbound emails + protect main domain reputation.                                                                                                                                                                     | PDF: *"create a separate IP / sign up + email domain"*                                                                                                                                                                                                                                                         |
| Arch-34 | **Four boards** (Funnel / Management-Prateek / Sales / OPS) with role-based default routing per §4.                                                                                                                                                                                                                                                                                                                      | Explicit role-scoped views from PDF.                                                                                                                                                                                                              | PDF: *"(4) OPS — JOBS & CANDIDATES ONLY ... (5) PRATEEK — ACTION & REPORTS"* + Sales Dashboard block + Management Dashboard block.                                                                                                                                                                             |
| Arch-35 | **Lead engine tracks open jobs at prospect companies** (`prospect_company_jobs`) with paid/non-paid, active/confidential, no-linkedin-post flags. Candidate matches per job (`prospect_company_job_candidates`). Field-change audit (`prospect_company_job_history`).                                                                                                                                                    | Required to power the OPS board features Prateek explicitly drew (sort job-wise, group company-wise, paid/non-paid filter, active/confidential filter, per-job no-linkedin toggle). External jobs (not in thh-backend) so must be cached locally. | PDF: *"OPS — JOBS & CANDIDATES ONLY / COMPANY → J1, J2, J3 / SORTING JOB WISE / GROUPING COMPANY WISE / PAID & NON PAID MAIN / (6) ACTIVE VS CONFIDENTIAL / NO LINKEDIN POST BUTTON"* + Ishank: *"add as many tables as its correct and complete for scale infra"*                                             |
| Arch-36 | **Funnel restructured** — drop `interested_`* and `trial` as stages. New stage enum has only 5 values: cold, curious, converted, lost, unsubscribed. Demo, Trial, Registration, First Job, First Applicant become independent timestamp **milestones** on `prospects` (`registered_at`, `demo_booked_at`, `first_job_created_at`, `first_applicant_received_at`, `converted_at`).                                        | "Interested" was a confusing superset (registered OR demo OR trial). Splitting them out lets dashboards show each independently and lets prospects skip steps in any order.                                                                       | Ishank (2026-04-28): *"intrested is someone who has registered with us trial is someone who has created a job intrested can be people who have also booked a demo so its a superset of demo and trial lets do one thing we wont keep intrested we will show 2 seprate demo and trial so itnrested is useless"* |
| Arch-37 | **Curious = any unique visit from any marketing channel** (SEO, paid, brand, Warmly-attributed company visits, direct, etc.). Some visitors self-identify (signup form, tracked email link); some are identified at company level via Warmly.                                                                                                                                                                            | Replaces the older "engaged with outreach" definition. Aligns with Prateek's *"click karke aa raha hai to directly capture"* and the marketing-funnel framing.                                                                                    | Ishank (2026-04-28): *"visit means curious, anyone who comes from visiting from any marketing or anything seo so curious is visits as unique visits, some register themselves some we find out via warmly"*                                                                                                    |
| Arch-38 | **Activation milestones (`first_job_created_at`, `first_applicant_received_at`) populated by polling thh-backend.** New ARQ worker job runs daily; for every prospect with `thh_user_id` set, calls a new thh-backend endpoint to fetch activation status. Becomes integration touch point #5.                                                                                                                           | Lead engine doesn't have job/applicant data — that lives in thh-backend (the actual product). Polling is simpler than emit logic in thh-backend. 1-day staleness acceptable for these milestones.                                                 | Ishank (2026-04-28): *"how many created at least one job, how many have recieved applcaints min 1 these things are not in the funnel rn but are important"*                                                                                                                                                    |
| Arch-39 | **Role rename**: `ops` → `csm` (Customer Success Manager). `admin_users.role` enum value 5 = `csm`. The OPS Board becomes the CSM Board.                                                                                                                                                                                                                                                                                 | Reflects the actual role title at THH.                                                                                                                                                                                                            | Ishank (2026-04-28): *"wouldn't this be a specific page for ops or as I would call it csm?"*                                                                                                                                                                                                                   |
| Arch-40 | **Job Distribution feature** (CSM-only page): "Post a Job" button → form with (1) job boards multi-select, (2) ONE expectation/target across all boards combined, (3) days threshold for at-risk. Backend stores `at_risk_at TIMESTAMP` (= posted_at + threshold), computed from UI days input. New junction table `prospect_company_job_boards` for per-board posting state.                                            | Mirrors Prateek's PDF (*"DECISION OF POST JOB OR NOT"*) but operationalised as a real workflow. Storing absolute datetime (not interval) keeps queries trivial and is unit-agnostic.                                                              | Ishank (2026-04-28): *"when we click on post a job it will be a dropdown..."* + *"we will be using date time even if ui takes days we convert that to hours and then use date time and save that info so future proof"* + *"targets should be overall across all boards not board specific"*                   |
| Arch-41 | **At-risk one-way ratchet**: a job shows in "Jobs at Risk" iff `status=open AND target_met_at IS NULL AND at_risk_at < NOW()`. The moment total applicants ≥ target, `target_met_at` is set and never cleared — the job is permanently NOT at risk even if numbers later drop.                                                                                                                                           | Prevents flicker (job entering and leaving at-risk repeatedly). Matches Prateek's PDF intent: at-risk is a state of *"haven't hit target yet"*, not *"currently below target"*.                                                                   | Ishank (2026-04-28): *"as soon as that many applications are in it can never be at risk"*                                                                                                                                                                                                                      |
| Arch-42 | **Posting Helper page** (CSM-only): mirrors the full field set from thh-backend's `format_job_message()` (`thh-backend/services/telegram/message_formatter.py:196`). Each field copy-friendly. Used to manually copy-paste into external job boards. **Data source PENDING** (lead engine local store vs live pull from thh-backend).                                                                                    | Manual posting workflow needs all the fields the THH-product-side already standardises. Reuses the existing field model so we don't reinvent.                                                                                                     | Ishank (2026-04-28): *"all fields job id company name etc etc like thh backend has for telegram message on job post"*                                                                                                                                                                                          |
| Arch-43 | **Caller "Next" workflow**: caller sees a single "Next" button → reveals one assigned prospect at a time. Outcomes: RNR / Not Interested / Call Back (with date+time) / Follow Up / Demo Scheduled. Auto-rule: 3 RNR rows on the same prospect → auto-mark Not Interested. Separate sub-view: pending callbacks list with date+time. New table `call_logs` (§7.25). No batch view, no queue UI, no daily-capacity logic. | Simpler operational model than the earlier batch-assignment idea. Reduces caller cognitive load to one prospect at a time.                                                                                                                        | Ishank (2026-04-28): *"skipping all this we will just show next next prospect and he will call and ring and no resposne, not intrested, call back, follow up, demo scheduled if anyone is 3 times rnr then he is not intrested and he will always see how many leeds of callbacks and date and time for it"*   |
| Arch-44 | `**prospect_stage_history.from_stage` and `to_stage` enum values reduced** in line with Arch-36 (only cold/curious/converted/lost/unsubscribed remain). Historical rows referencing old `interested_`* / `trial` values: NOT migrated since this is a greenfield app — the old stage values were never written in production.                                                                                            | Schema-side cleanup of Arch-36.                                                                                                                                                                                                                   | Inherits Arch-36 lock.                                                                                                                                                                                                                                                                                         |


---

## 9. THH Integration Contract

The full surface between lead-engine and thh-backend is exactly four endpoints (deferred fifth for v2). Anything outside this list is duplicated/maintained inside lead-engine.

### 9.1 `POST` Promote prospect to THH


| Item                        | Value                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------- |
| Caller                      | lead-engine-backend (triggered by manual button on prospect detail page)                             |
| Target                      | thh-backend `LeadCRUD.create_lead` (existing endpoint, see `thh-backend/services/user/crud.py:1585`) |
| When                        | Admin clicks "Promote to THH" on a prospect detail page in the lead engine UI.                       |
| Payload                     | `{ email, first_name, last_name, company_name, domain, phone, source, lead_engine_prospect_id }`     |
| Response                    | thh-backend returns the created/upserted `users.id`                                                  |
| Side effects in lead-engine | Set `prospects.thh_user_id`; insert audit_log row `action=promote_to_thh`; disable the button.       |


### 9.2 `GET` Pre-import dedupe check


| Item                        | Value                                                                             |
| --------------------------- | --------------------------------------------------------------------------------- |
| Caller                      | lead-engine ARQ worker (Apollo sync job, every 6 h)                               |
| Target                      | thh-backend `check-company-exists` (existing endpoint per recon)                  |
| When                        | Per-prospect during Apollo sync, before insert/update in lead-engine `prospects`. |
| Payload                     | `{ email, domain }`                                                               |
| Response                    | thh-backend returns `{ exists: bool, thh_user_id?: number }`                      |
| Side effects in lead-engine | If `exists=true`, annotate the prospect (note + flag) — do NOT block the import.  |


### 9.3 `POST` Send OTP


| Item                        | Value                                                                          |
| --------------------------- | ------------------------------------------------------------------------------ |
| Caller                      | lead-engine-backend (triggered by signup form submission on landing page)      |
| Target                      | thh-backend `POST /api/auth/login-otp/send`                                    |
| When                        | Prospect submits the landing page signup form.                                 |
| Payload                     | `{ email, purpose: "lead_engine_signup" }`                                     |
| Response                    | thh-backend returns success/failure + rate-limit info                          |
| Side effects in lead-engine | Insert `signups` row; insert `campaign_events` row event_type=`otp_sent` (16). |


### 9.4 `POST` Verify OTP


| Item                        | Value                                                                                                                                                                                                                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Caller                      | lead-engine-backend (triggered by OTP entry on signup page)                                                                                                                                                                                                                                 |
| Target                      | thh-backend `POST /api/auth/login-otp/verify`                                                                                                                                                                                                                                               |
| When                        | Prospect enters the OTP code.                                                                                                                                                                                                                                                               |
| Payload                     | `{ email, otp_code }`                                                                                                                                                                                                                                                                       |
| Response                    | thh-backend returns success/failure                                                                                                                                                                                                                                                         |
| Side effects in lead-engine | On success: set `signups.otp_verified_at`, upsert `prospects` via dedupe rules, move `prospects.stage` to `interested_warm` (3) via stage-change service (writes `prospect_stage_history` + `audit_log`), insert `campaign_events` row event_type=`otp_verified` (17), fire Telegram alert. |


### 9.5 `GET` Activation status sync


| Item                        | Value                                                                                                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Caller                      | lead-engine ARQ worker (daily activation sync job)                                                                                                                                   |
| Target                      | thh-backend `GET /api/lead-engine/activation-status?thh_user_id=X` (NEW endpoint to be added on thh-backend side — minimal SELECT against `users`, `jobs`, `applicants` tables)      |
| When                        | Daily, for every prospect with `thh_user_id` set (i.e. promoted-to-THH).                                                                                                             |
| Payload                     | `{ thh_user_id }`                                                                                                                                                                    |
| Response                    | `{ has_jobs: bool, job_count: int, has_applicants: bool, applicant_count: int, first_job_at: timestamp|null, first_applicant_at: timestamp|null }`                                   |
| Side effects in lead-engine | Update prospect's `first_job_created_at`, `first_applicant_received_at`, `jobs_created_count`, `applicants_received_count` if changed. Fire Telegram alert on first-time activation. |


### 9.6 (Deferred v2) Federated admin login via THH JWT

Held until lead-engine grows past ~10 admin users or SSO is mandated. `admin_users.thh_user_id` column is reserved now.

---

## 10. Explicit MVP Cuts (what we are NOT building)


| Cut                                               | Why                                                                                                                  | When to revisit                                          |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Live enrichment for unknown-domain landing pages  | Apollo latency + rate limits + fallback complexity = scope tarpit. Generic page + async enrich is industry standard. | When unknown-domain visit rate > 20% of total.           |
| Cross-device anonymous attribution                | Even Mixpanel/Segment get this wrong. Single-device cookie ID is the honest ceiling.                                 | Never (skip permanently).                                |
| LLM-based reply classification                    | Keyword rules give ~70% accuracy free. LLM is a v2 optimisation once we have reply volume to validate against.       | After 1k+ replies logged.                                |
| Multi-tenancy                                     | Only matters if THH itself becomes multi-tenant.                                                                     | When THH multi-tenancy is on the roadmap.                |
| Email composer / sequences inside lead engine     | Apollo handles sending today; replicating triples build cost. Schema is record-only.                                 | If we drop Apollo for sending.                           |
| Email rendering tests across Gmail/Outlook/mobile | Lead engine doesn't send — Apollo does.                                                                              | If we own sending.                                       |
| Claude/AI agent that auto-logs LinkedIn activity  | Manual button covers v1 use case. Agent endpoint can be added later without schema change.                           | v2 — when LinkedIn outreach volume justifies automation. |


---

## 11. Phased Implementation Plan (high-level)


| Phase                       | Days                          | Deliverable                                                                                                                                                                                                | THH touch                                                  |
| --------------------------- | ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 0. Setup                    | 1-2                           | Repos initialised, CLAUDE.md, Docker Compose, GH Actions skeleton, Calendly setup, Telegram bot setup, Vercel custom domain registered.                                                                    | None                                                       |
| 1. Backend foundation       | 3-7                           | FastAPI + SQLAlchemy + Alembic + auth + audit + health + CORS + rate limiter + Sentry. All 23 tables migrated. Deployed to Fly.io staging.                                                                 | None                                                       |
| 2. Backend domain endpoints | 8-15                          | Prospects + Companies + Landing Pages + Variants + Signups + Campaigns + Webhooks + Jobs/Candidates + ARQ workers (Apollo sync, snapshot, heat recalc) + compliance endpoints.                             | None                                                       |
| 3. THH integration          | 16-17                         | THH client wrapper, Promote-to-THH endpoint, pre-import dedupe check, OTP send + verify with stage-auto-move.                                                                                              | FOUR endpoints called against thh-backend staging.         |
| 4. Frontend foundation      | 18-22 (parallel with Phase 3) | Next.js + Tailwind + shadcn + Tanstack Query + auth middleware + login + typed API client + auto-codegen TS types + role-based default routing. Deployed to Vercel staging on custom domain.               | None                                                       |
| 5. Frontend admin features  | 23-30                         | Funnel board, Management/Prateek board, Sales board, OPS board, Prospects list/detail, Campaigns, Landing Pages editor + variants UI, Audit viewer, Merge review queue, Jobs/Candidates UI.                | Promote-to-THH button + OTP-via-THH (verified in staging). |
| 6. Frontend public features | 31-34                         | Dynamic landing pages with variant assignment, "Pearls & Promises" templates, visit tracking with `visitor_id`, signup form with OTP step, thanks page with Calendly embed, mobile + SEO + cookie consent. | OTP send + verify on signup form.                          |
| 7. Smoke test + dogfood     | 35-37                         | Full end-to-end staging walk-through (campaign → landing → variant assigned → signup → OTP → demo book → promote to THH → unsubscribe).                                                                    | Full E2E with thh-backend staging.                         |
| 8. Production rollout       | 38                            | Migrations applied to prod MySQL (new database), backend live on Fly.io prod, frontend live on Vercel prod with custom domain, webhooks pointed at prod.                                                   | Prod base URL switched.                                    |
| 9. Iterate                  | Week 6+                       | LLM classifier, live enrichment, federation, sequences (if pulled in-house), AI agent for LinkedIn auto-logging.                                                                                           | TBD per feature.                                           |


---

## 12. Appendix — Direct Prateek Quotes Referenced

Listed for traceability. Every quote below underwrites a specific decision in this document.

1. *"It will be completely different db. Completely new application. Interacting with thh via api."* — drives Arch-1, Arch-3.
2. *"Hamara kya hoga ki jab email bhej denge. Usmein variable already set. Har ek ka alag landing page ho jayega. Har ek prospect ka landing page alag hoga. Uske andar ek unique identifier aa jayega. Domain name ka domain name ho gaya identifier."* — drives §1, Arch-9, §7.9.
3. *"Page mein look like uska domain uthayega. Agar database mein hoga to as it is dikha dega. Agar database mein nahi hoga to usi waqt generate karke dikha dega."* — drives §7.2 (companies + `source=inferred`).
4. *"What is the minimum identifier for a cold? LinkedIn URL. That's the first one. Email then phone. Minimum identifier bhi LinkedIn URL unique hota hai."* — drives Arch-6, §7.3 unique key on `linkedin_url`.
5. *"Aur yeh ek number hoga X."* — drives Arch-6 (internal system ID = `prospects.id`).
6. *"Email campaign yes/no. LinkedIn. Brand guide yes/no. Then your remarketing. Social media. ... Isliye ismein har ek future ke zaroorat hoga usmein ek column hoga."* — drives Arch-7, §7.4.
7. *"Apollo.io se humein milti hai official leads."* — drives Arch-12, §7.3 (`apollo_contact_id`).
8. *"Sabse pehle status cold. Second curious. Third interested. ... Interested cold. Interested hot. Interested will go. Then finally converted. By the way conversion will not end here. ... That is a different team."* — drives Arch-5, §3, §7.3 stage values.
9. *"Ab basically we will talk to you about the cold and curious number week on week."* — drives §7.5 stage history table, §7.17 snapshot table, Arch-20.
10. *"If my cold is not increasing then it should be resolved that cold should be increased week on week. If my curious is not increasing then somebody else is responsible. ... Curious to interested will be yours. Landing page reactivation required."* — drives §3 KPI ownership table.
11. *"If anonymously aa raha hai to woh nahi (track ho raha hoga). Click karke aa raha hai to directly capture ho jayega."* — drives Arch-10, §7.11 visitor_id mechanism.
12. *"Dekho email par jo reply kar raha hai na woh handle zyada easy hai. Do hi tarah ke reply hote hain. Don't send me. Ya I am interested. Yeh to seedhe demo book kar denge uske saath jo I am interested wala hai."* — drives Arch-11, §7.13 binary classification.
13. *"Open rate kitna aa raha hai?"* — drives §7.8 campaign_events event_type values.
14. *"Toh hamare agents, hamare in-house BDR will do it. Main karta hoon."* — drives Arch-4 (BDR role), §7.15 prospect_notes/tasks.
15. PDF: *"To make a panel: 1) Keyword List Rank 2) Traffic 3) Lead 4) Quality"* — drives Arch-22 (`quality_score`).
16. PDF: *"SEO / GEO ... Paid ... Brand ... Outbound ... Remarketing ... Warmly"* — drives Arch-8 (channels including `geo` and `warmly`).
17. PDF: *"Trial = Lead = Demo scheduled"* + *"Prospect to trial"* + *"Trial to converted"* — drives Arch-5 (trial stage).
18. PDF: *"OTP = interested"* — drives Arch-16 (OTP via THH + auto-stage-move).
19. PDF: *"create a separate IP / sign up + email domain"* — drives Arch-33 (custom Vercel domain + Apollo sender ask).
20. PDF: *"calls → RBAC for our callers ... → No Reminders"* — drives Arch-4 (caller role).
21. PDF: *"Claude integration that updates CRM of all developments — CR sent / messages sent / Reverts"* — drives Arch-30 (manual LinkedIn activity logging; auto-agent deferred).
22. PDF: *"(4) Pearls & Promises in 1 Page"* — drives Arch-32 (landing page design principle).
23. PDF: *"(5) 1st Section — Want to Test"* — drives Arch-31 (hero-section A/B in MVP).
24. PDF: *"(4) OPS — JOBS & CANDIDATES ONLY"* + *"(5) PRATEEK — ACTION & REPORTS / DECISION OF POST JOB OR NOT"* + Sales Dashboard block — drives Arch-34 (4 boards) and Arch-35 (jobs/candidates subsystem).
25. PDF: *"COMPANY → J1, J2, J3 / SORTING JOB WISE / GROUPING COMPANY WISE / PAID & NON PAID MAIN / (6) ACTIVE VS CONFIDENTIAL / NO LINKEDIN POST BUTTON"* — drives Arch-35 (`prospect_company_jobs` columns).

### Ishank lock-in quotes (decisions where Ishank closed an open question)

- *"i'll keep it mysql only for reusability i'll just make a new schema in the same db"* — Arch-3.
- *"honor prateek"* — Arch-11 (binary reply classification).
- *"yes option 2"* — Arch-16 (OTP via THH).
- *"option 1"* — Arch-4 (caller as own role).
- *"yes we wil ship it part of current project"* — Arch-31 (A/B in MVP).
- *"add as many tables as its correct and complete for scale infra"* — Arch-35 (full jobs/candidates subsystem).
- *"we wont use enums at all we will always use tiny ints everywhere fix that please everywhere across the documentation and more"* — Arch-29 (TINYINT migration).

---

## 13. Glossary


| Term                        | Meaning                                                                                                                |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Prospect                    | Any person we have or will outreach. Lives in `prospects`.                                                             |
| Cold                        | Earliest stage. Outreach sent, no signal back.                                                                         |
| Curious                     | Engaged with outreach (open / click / direct visit).                                                                   |
| Interested                  | Submitted form / replied positive / OTP-verified.                                                                      |
| Trial                       | Demo scheduled OR free product trial active.                                                                           |
| Converted                   | Became a paying client. Promoted to thh-backend at this point.                                                         |
| Heat level                  | Derived 0-2 bucket (cold/warm/hot) from `heat_score`.                                                                  |
| Quality score               | ICP fit score 0-10, separate from engagement-based heat.                                                               |
| Visitor ID                  | Anonymous cookie identifier for landing page visitors. Linked to a prospect on signup.                                 |
| Promote to THH              | Manual button that pushes a converted prospect into thh-backend as a real lead.                                        |
| Snapshot                    | Pre-aggregated daily count of prospects per (stage, channel, owner). Powers the dashboard.                             |
| Variant                     | A/B test variant of a landing page's content. Lives in `landing_page_variants`.                                        |
| Job (prospect_company_jobs) | An open role at a prospect company that we track as a sales hook. NOT a THH-product job.                               |
| Candidate match             | A THH candidate prepared/proposed for a specific prospect_company_job.                                                 |
| Pearls & Promises           | Landing page design principle: single-page layout, value props ("pearls") + commitments ("promises") front and centre. |


---

## 14. Pending User Input (still need explicit lock-in)

These items are dictated/implied but lack a final lock and could affect schema or scope:


| #   | Item                                         | What's pending                                                                                                                                                             | First raised                           |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- |
| P1  | "Total new" marketing KPI                    | Definition: new prospects added vs new unique visitors vs something else. Where it lives (new Marketing board?).                                                           | Ishank 2026-04-28                      |
| P2  | "Graph per day" of curious-to-next-milestone | Which milestone(s) to chart (demo_booked? first_job_created? all of them as separate lines?). Time window default.                                                         | Prateek (relayed by Ishank 2026-04-28) |
| P3  | Posting Helper data source                   | Lead engine stores all THH-style job fields locally (huge schema add — maps from `format_job_message`) OR pulls live from thh-backend per render.                          | Ishank 2026-04-28                      |
| P4  | Cold → Curious auto-promotion trigger        | Now that Curious = "any visit", confirm rule: any `landing_page_visits` insert auto-promotes `prospects.stage` from cold → curious. (Was Option B in earlier walkthrough.) | Ishank 2026-04-27                      |
| P5  | 3xRNR auto-mark mechanism                    | Once 3 RNR fires, what exactly happens to the prospect — set a milestone `marked_not_interested_at`, OR move stage to `lost`, OR set a flag column.                        | Ishank 2026-04-28                      |
| P6  | Custom domain final value                    | `try-thehirehub.com` was a placeholder. Confirm actual domain to register.                                                                                                 | Ishank 2026-04-27                      |
| P7  | Repo names final                             | `thh-lead-engine-backend` + `thh-lead-engine-frontend` (current names you created). Confirm OK.                                                                            | Ishank 2026-04-27                      |


---

**End of document.**

This is the source of truth for schema and architecture decisions. Any deviation must be reflected back here with a new entry in §8.