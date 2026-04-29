# Cross-Cutting Concerns

> 19 nodes · cohesion 0.13

## Key Concepts

- **apollo_sync task** (5 connections) — `workers/tasks/apollo_sync.py`
- **WebhookDeliveryCRUD** (4 connections) — `services/webhooks/crud.py`
- **ARQ WorkerSettings** (4 connections) — `workers/settings.py`
- **import_all_models()** (3 connections) — `setup_database.py`
- **heat_recalc task** (3 connections) — `workers/tasks/heat_recalc.py`
- **UnsubscribeCRUD** (3 connections) — `services/unsubscribes/crud.py`
- **Unsubscribes routes** (3 connections) — `services/unsubscribes/routes.py`
- **Webhooks routes (Calendly+Apollo)** (3 connections) — `services/webhooks/routes.py`
- **Webhook idempotency (HMAC + dedupe)** (2 connections) — `services/webhooks/crud.py`
- **activation_sync task** (2 connections) — `workers/tasks/activation_sync.py`
- **funnel_snapshot task** (2 connections) — `workers/tasks/funnel_snapshot.py`
- **Unsubscribe model** (2 connections) — `services/unsubscribes/models.py`
- **WebhookDelivery model** (2 connections) — `services/webhooks/models.py`
- **CAN-SPAM/GDPR compliance** (1 connections) — `services/unsubscribes/routes.py`
- **Heat scoring rules (cold/warm/hot)** (1 connections) — `workers/tasks/heat_recalc.py`
- **THH touchpoint #2 (dedupe check)** (1 connections) — `workers/tasks/apollo_sync.py`
- **THH touchpoint #5 (activation status)** (1 connections) — `workers/tasks/activation_sync.py`
- **setup_database bootstrap** (1 connections) — `setup_database.py`
- **Unsubscribe schemas** (1 connections) — `services/unsubscribes/schemas.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `services/unsubscribes/crud.py`
- `services/unsubscribes/models.py`
- `services/unsubscribes/routes.py`
- `services/unsubscribes/schemas.py`
- `services/webhooks/crud.py`
- `services/webhooks/models.py`
- `services/webhooks/routes.py`
- `setup_database.py`
- `workers/settings.py`
- `workers/tasks/activation_sync.py`
- `workers/tasks/apollo_sync.py`
- `workers/tasks/funnel_snapshot.py`
- `workers/tasks/heat_recalc.py`

## Audit Trail

- EXTRACTED: 32 (73%)
- INFERRED: 12 (27%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*