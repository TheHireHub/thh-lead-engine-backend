# Models and Schemas

> 74 nodes · cohesion 0.03

## Key Concepts

- **Prospect (model)** (11 connections) — `services/prospects/models.py`
- **common.enums** (8 connections) — `services/common/enums.py`
- **LandingPage** (8 connections) — `services/landing_pages/models.py`
- **landing_pages/routes.py** (7 connections) — `services/landing_pages/routes.py`
- **ProspectCompanyJob (model)** (7 connections) — `services/prospect_company_jobs/models.py`
- **email_replies/routes.py** (6 connections) — `services/email_replies/routes.py`
- **EmailReply** (6 connections) — `services/email_replies/models.py`
- **admin_users (FK target)** (5 connections) — `services/admin_users/models.py`
- **envelope.ok** (4 connections) — `services/common/envelope.py`
- **FunnelSnapshotCRUD** (4 connections) — `services/funnel_snapshots/crud.py`
- **funnel_snapshots/routes.py** (4 connections) — `services/funnel_snapshots/routes.py`
- **LandingPageVariant** (4 connections) — `services/landing_pages/models.py`
- **LandingPageVisit** (4 connections) — `services/landing_pages/models.py`
- **ProspectNoteCRUD** (4 connections) — `services/prospect_notes/crud.py`
- **ProspectNote (model)** (4 connections) — `services/prospect_notes/models.py`
- **Base (declarative)** (3 connections) — `database_connection/connection.py`
- **companies (FK target)** (3 connections) — `services/companies/models.py`
- **CompanyCreate** (3 connections) — `services/companies/schemas.py`
- **EmailReplyCRUD** (3 connections) — `services/email_replies/crud.py`
- **FunnelDailySnapshot** (3 connections) — `services/funnel_snapshots/models.py`
- **_serialize (jobs)** (3 connections) — `services/prospect_company_jobs/routes.py`
- **_serialize (notes)** (3 connections) — `services/prospect_notes/routes.py`
- **ProspectCRUD** (3 connections) — `services/prospects/crud.py`
- **ProspectCRUD.change_stage** (3 connections) — `services/prospects/crud.py`
- **docs/SCHEMA.md** (3 connections) — `docs/SCHEMA.md`
- *... and 49 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `database_connection/connection.py`
- `docs/SCHEMA.md`
- `services/admin_users/models.py`
- `services/campaigns/models.py`
- `services/common/enums.py`
- `services/common/envelope.py`
- `services/companies/models.py`
- `services/companies/schemas.py`
- `services/email_replies/crud.py`
- `services/email_replies/enums.py`
- `services/email_replies/models.py`
- `services/email_replies/routes.py`
- `services/email_replies/schemas.py`
- `services/funnel_snapshots/crud.py`
- `services/funnel_snapshots/enums.py`
- `services/funnel_snapshots/models.py`
- `services/funnel_snapshots/routes.py`
- `services/funnel_snapshots/schemas.py`
- `services/landing_pages/crud.py`
- `services/landing_pages/enums.py`

## Audit Trail

- EXTRACTED: 156 (84%)
- INFERRED: 28 (15%)
- AMBIGUOUS: 2 (1%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*