# HH-BE ↔ LEADS Service Integration

Two independent services that call each other in **both directions**.
Each direction has its own service-token; the two tokens are unrelated
random secrets, rotated independently.

---

## Service identities

| Service | Repo / role                                 | Local URL              |
|---------|---------------------------------------------|------------------------|
| HH-BE   | `thh-backend` — Flask, recruiter-facing API | `http://localhost:5000`|
| LEADS   | `thh-lead-engine-backend` — FastAPI, CRM    | `http://localhost:5050`|

Both call each other server-to-server. End-users never hit LEADS directly.

---

## Direction 1 — HH-BE → LEADS  (inbound to us)

**When it fires:** recruiter clicks "Initiate Outreach" in HH-FE.

**Path:**
HH-FE → `POST /api/outreach/initiate` (HH-BE) → fire-and-forget daemon
thread → `POST {LEADS_BASE_URL}/api/candidate-outreach/ingest` (LEADS)

**Header:** `X-Service-Token: <secret-A>`

**Behavior:** non-blocking. The recruiter's 200 + toast fires before the
LEADS push completes. Up to 4 retries with exponential backoff
(0.5s + 1s + 2s + 4s ≈ 7.5s total). 4xx = poison pill, no retry. Both
env vars must be set or the push is silently skipped (logged at INFO).

**Env vars (same value, different names per side):**

| Side    | Var name                       | Role                                      |
|---------|--------------------------------|-------------------------------------------|
| HH-BE   | `LEADS_SERVICE_TOKEN`          | What HH-BE presents in the outbound header|
| HH-BE   | `LEADS_BASE_URL`               | Where to POST (e.g. `http://localhost:5050`) |
| LEADS   | `THH_INCOMING_SERVICE_TOKEN`   | What LEADS validates the header against   |

`LEADS_SERVICE_TOKEN` (HH-BE) === `THH_INCOMING_SERVICE_TOKEN` (LEADS).

**Code refs:**
- HH-BE caller: `services/outreach_trigger/leads_pusher.py`
- HH-BE route that triggers it: `services/outreach_trigger/routes.py`
- LEADS endpoint: `POST /api/candidate-outreach/ingest`
- LEADS auth: [services/candidate_outreach/auth.py](../services/candidate_outreach/auth.py)

---

## Direction 2 — LEADS → HH-BE  (outbound from us)

**When it fires:** LEADS wants to promote a prospect into HH (create an
HH user), check if a company already exists, or poll a prospect's
activation status. These are touch points §9.1, §9.2, §9.5 from
[SCHEMA.md](./SCHEMA.md). (§9.3/§9.4 — OTP send/verify — also flow
through this direction but use a different auth context.)

**Path:** LEADS → one of HH-BE's `/api/lead-engine/*` endpoints.

**Header:** `X-Service-Token: <secret-B>`

**Endpoints on HH-BE that require this token:**

| Method | Path                                       | Purpose                              | SCHEMA |
|--------|--------------------------------------------|--------------------------------------|--------|
| POST   | `/api/lead-engine/leads`                   | Promote prospect → HH user           | §9.1   |
| GET    | `/api/lead-engine/check-company-exists`    | Pre-import dedupe                    | §9.2   |
| GET    | `/api/lead-engine/activation-status`       | Daily activation poll                | §9.5   |

If the env var is unset on HH-BE, every call returns 500
(`service_token_not_configured`). If the header value mismatches → 401.

**Env vars (same value, different names per side):**

| Side    | Var name                       | Role                                      |
|---------|--------------------------------|-------------------------------------------|
| HH-BE   | `LEAD_ENGINE_SERVICE_TOKEN`    | What HH-BE validates the inbound header against |
| LEADS   | `THH_BACKEND_SERVICE_TOKEN`    | What LEADS presents in the outbound header|

`LEAD_ENGINE_SERVICE_TOKEN` (HH-BE) === `THH_BACKEND_SERVICE_TOKEN` (LEADS).

**Code refs:**
- HH-BE auth decorator: `services/lead_engine/auth.py` (`require_service_token`)
- HH-BE routes: `services/lead_engine/routes.py`
- LEADS client: [services/integrations/thh_backend.py](../services/integrations/thh_backend.py)

---

## Pairing summary (the cheat sheet)

```
Direction              HH-BE var                       LEADS var                      Same value?
─────────────────────  ─────────────────────────────   ────────────────────────────   ───────────
HH-BE → LEADS          LEADS_SERVICE_TOKEN             THH_INCOMING_SERVICE_TOKEN     YES (secret-A)
LEADS → HH-BE          LEAD_ENGINE_SERVICE_TOKEN       THH_BACKEND_SERVICE_TOKEN      YES (secret-B)
```

secret-A ≠ secret-B. They're independent random strings so a leak in one
direction doesn't compromise the other and they can be rotated separately.

---

## .env templates

### HH-BE (`thh-backend/.env`)
```
LEADS_BASE_URL=http://localhost:5050
LEADS_SERVICE_TOKEN=<secret-A>
LEAD_ENGINE_SERVICE_TOKEN=<secret-B>
```

### LEADS (`backend/.env`)
```
THH_INCOMING_SERVICE_TOKEN=<secret-A>
THH_BACKEND_SERVICE_TOKEN=<secret-B>
```

Generate new secrets with: `python -c "import secrets; print(secrets.token_urlsafe(32))"`

---

## Common failure modes

| Symptom                                       | Likely cause                                                       |
|-----------------------------------------------|--------------------------------------------------------------------|
| HH-BE log: `LEADS_* env not configured — skipping push` | `LEADS_BASE_URL` or `LEADS_SERVICE_TOKEN` unset on HH-BE   |
| HH-BE log: `LEADS push rejected with 4xx (401)` | secret-A mismatch (HH-BE value ≠ LEADS value)                    |
| HH-BE log: `LEADS push rejected with 4xx (422)` | Payload schema mismatch — diff against LEADS' Pydantic schema    |
| HH-BE log: `LEADS push rejected with 4xx (503)` | LEADS server has `THH_INCOMING_SERVICE_TOKEN` unset                |
| HH-BE log: `LEADS push gave up after 4 attempts` | LEADS unreachable or 5xx — check LEADS logs                       |
| HH-BE inbound endpoint returns 500 `service_token_not_configured` | `LEAD_ENGINE_SERVICE_TOKEN` unset on HH-BE          |
| HH-BE inbound endpoint returns 401 `unauthorized` | secret-B mismatch (HH-BE value ≠ LEADS value)                    |

After editing `.env`, **hard-restart** the affected server.
`python-dotenv` only reads `.env` once at process start.

---

## Operational notes

- Both `.env` files are gitignored. Never commit either secret.
- Same `X-Service-Token` header name is used on both directions of the
  wire — only the **values** differ. Don't let the shared header name
  mislead you into thinking it's one token.
- Token comparison on the LEADS side uses `hmac.compare_digest` and
  strips whitespace; trailing newlines from copy-paste are tolerated.
- LEADS endpoint contract: `POST /api/candidate-outreach/ingest` accepts
  `Content-Type: application/json`. Returns 200 on success and on
  duplicate `dedup_key` (idempotent — `data.created` flag distinguishes).
- HH-BE's outbound `dedup_key` is `sha256({job_id}:{user_id}:{sorted_candidate_ids})[:16]` →
  same recruiter sending the same candidate set on the same job collapses
  to one LEADS row.
- The actual outreach send (LinkedIn DM / email) is currently a stub
  inside HH-BE's `_dispatch_outreach()`. Today's flow only records the
  click intent in LEADS for CRM visibility; no message reaches the
  candidate yet.
