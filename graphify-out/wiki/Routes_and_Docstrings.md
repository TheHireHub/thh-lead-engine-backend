# Routes and Docstrings

> 69 nodes · cohesion 0.07

## Key Concepts

- **FastAPI routes for companies (Schema doc §7.2).** (70 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/routes.py`
- **BaseModel** (38 connections)
- **Pydantic schemas for companies.** (14 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/schemas.py`
- **routes.py** (9 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/routes.py`
- **TODO: integrate with thh-backend OTP send (Schema §9.3) — call thh-backend     P** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/routes.py`
- **Powers the "Jobs at Risk" CSM view.** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/routes.py`
- **TODO: same pattern as Calendly. Provider=1.** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`
- **# TODO: hash IP via VISITOR_IP_HASH_SECRET, attach user_agent from request heade** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/routes.py`
- **CSM "Post a Job" — Schema doc §5.6, Arch-40.** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/routes.py`
- **# TODO: replace `prepared_by_user_id` with current-user dep once auth lands.** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/routes.py`
- **JobDistributionRequest** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **schemas.py** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **CandidateMatchCreate** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **JobCreate** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **JobOut** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **JobUpdate** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- **schemas.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/schemas.py`
- **routes.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/routes.py`
- **schemas.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/schemas.py`
- **schemas.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/schemas.py`
- **# TODO: replace `created_by_user_id` query param with current-user dep once auth** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_notes/routes.py`
- **SignupCreate** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/schemas.py`
- **SignupOut** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/schemas.py`
- **schemas.py** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/schemas.py`
- **schemas.py** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/schemas.py`
- *... and 44 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/admin_users/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/audit/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/routes.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/email_replies/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/enums.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/routes.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/routes.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/routes.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_notes/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_notes/routes.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_notes/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/schemas.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/routes.py`

## Audit Trail

- EXTRACTED: 236 (57%)
- INFERRED: 177 (43%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*