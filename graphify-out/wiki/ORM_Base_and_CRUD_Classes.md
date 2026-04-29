# ORM Base and CRUD Classes

> 67 nodes · cohesion 0.08

## Key Concepts

- **Async CRUD for companies.** (40 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/crud.py`
- **Base** (36 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- **Base** (25 connections)
- **crud.py** (18 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/crud.py`
- **SQLAlchemy model for `companies` (Schema doc §7.2).** (15 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/models.py`
- **Prospect** (12 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **crud.py** (12 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/crud.py`
- **ProspectChannel** (11 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **ProspectMergeLog** (10 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **ProspectStageHistory** (10 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **ProspectMergeReviewQueue** (9 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **Campaign** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/models.py`
- **CampaignEvent** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/models.py`
- **CampaignProspect** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/models.py`
- **crud.py** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/crud.py`
- **ProspectCRUD** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/crud.py`
- **ProspectMergeReviewCRUD** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/crud.py`
- **CallLog** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/models.py`
- **WebhookDelivery** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/models.py`
- **crud.py** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/crud.py`
- **crud.py** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/email_replies/crud.py`
- **models.py** (7 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- **AuditLogCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/audit/crud.py`
- **CallLogCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/crud.py`
- **CampaignCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/crud.py`
- *... and 42 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/database_connection/connection.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/audit/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/audit/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/call_logs/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/campaigns/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/companies/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/email_replies/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/email_replies/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/funnel_snapshots/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_notes/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospects/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/signups/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/unsubscribes/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`

## Audit Trail

- EXTRACTED: 217 (49%)
- INFERRED: 226 (51%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*