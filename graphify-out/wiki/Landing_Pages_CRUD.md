# Landing Pages CRUD

> 20 nodes · cohesion 0.17

## Key Concepts

- **record()** (23 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- **crud.py** (12 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **LandingPage** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/models.py`
- **LandingPageVariant** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/models.py`
- **LandingPageVisit** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/models.py`
- **crud.py** (8 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- **LandingPageCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **LandingPageVariantCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **LandingPageVisitCRUD** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **WebhookDeliveryCRUD** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- **models.py** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/models.py`
- **apollo_webhook()** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`
- **calendly_webhook()** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`
- **routes.py** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`
- **get_by_external_id()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- **TODO:     1. Verify HMAC-SHA256 signature against `CALENDLY_WEBHOOK_SIGNING_KEY`** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`
- **get_by_slug()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **list_active_for_page()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- **mark_failed()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- **mark_processed()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/landing_pages/models.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/webhooks/routes.py`

## Audit Trail

- EXTRACTED: 57 (50%)
- INFERRED: 58 (50%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*