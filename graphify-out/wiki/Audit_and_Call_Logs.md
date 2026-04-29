# Audit and Call Logs

> 26 nodes · cohesion 0.11

## Key Concepts

- **campaigns/routes.py** (8 connections) — `services/campaigns/routes.py`
- **call_logs/routes.py** (6 connections) — `services/call_logs/routes.py`
- **companies/routes.py** (6 connections) — `services/companies/routes.py`
- **audit/routes.py** (4 connections) — `services/audit/routes.py`
- **campaigns/enums.py** (4 connections) — `services/campaigns/enums.py`
- **common/enums.py (TINYINT mappings §6)** (4 connections) — `services/common/enums.py`
- **common/envelope.py (ok/fail)** (4 connections) — `services/common/envelope.py`
- **CallLogCRUD.record (3xRNR auto-marker)** (3 connections) — `services/call_logs/crud.py`
- **call_logs/enums.py** (3 connections) — `services/call_logs/enums.py`
- **CampaignCRUD** (3 connections) — `services/campaigns/crud.py`
- **Campaign model** (3 connections) — `services/campaigns/models.py`
- **CompanyCRUD** (3 connections) — `services/companies/crud.py`
- **companies/enums.py** (3 connections) — `services/companies/enums.py`
- **CallLog model** (2 connections) — `services/call_logs/models.py`
- **CampaignEventCRUD** (2 connections) — `services/campaigns/crud.py`
- **CampaignEvent model** (2 connections) — `services/campaigns/models.py`
- **CampaignProspect model** (2 connections) — `services/campaigns/models.py`
- **Company model** (2 connections) — `services/companies/models.py`
- **AuditLogOut** (1 connections) — `services/audit/schemas.py`
- **CallLogCRUD** (1 connections) — `services/call_logs/crud.py`
- **CallLogCreate** (1 connections) — `services/call_logs/schemas.py`
- **CallLogOut** (1 connections) — `services/call_logs/schemas.py`
- **CampaignProspectCRUD** (1 connections) — `services/campaigns/crud.py`
- **CampaignCreate** (1 connections) — `services/campaigns/schemas.py`
- **CampaignEventCreate** (1 connections) — `services/campaigns/schemas.py`
- *... and 1 more nodes in this community*

## Relationships

- No strong cross-community connections detected

## Source Files

- `services/audit/routes.py`
- `services/audit/schemas.py`
- `services/call_logs/crud.py`
- `services/call_logs/enums.py`
- `services/call_logs/models.py`
- `services/call_logs/routes.py`
- `services/call_logs/schemas.py`
- `services/campaigns/crud.py`
- `services/campaigns/enums.py`
- `services/campaigns/models.py`
- `services/campaigns/routes.py`
- `services/campaigns/schemas.py`
- `services/common/enums.py`
- `services/common/envelope.py`
- `services/companies/crud.py`
- `services/companies/enums.py`
- `services/companies/models.py`
- `services/companies/routes.py`

## Audit Trail

- EXTRACTED: 54 (75%)
- INFERRED: 18 (25%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*