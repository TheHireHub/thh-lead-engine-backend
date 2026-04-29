# Job Distribution and At-Risk

> 6 nodes · cohesion 0.33

## Key Concepts

- **JobCRUD** (3 connections) — `services/prospect_company_jobs/crud.py`
- **ProspectCompanyJob (model)** (3 connections) — `services/prospect_company_jobs/models.py`
- **At-Risk One-Way Ratchet (Arch-41)** (1 connections) — `services/prospect_company_jobs/crud.py`
- **JobCandidateCRUD** (1 connections) — `services/prospect_company_jobs/crud.py`
- **Post-a-Job Distribute (Arch-40)** (1 connections) — `services/prospect_company_jobs/crud.py`
- **JobHistoryCRUD** (1 connections) — `services/prospect_company_jobs/crud.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `services/prospect_company_jobs/crud.py`
- `services/prospect_company_jobs/models.py`

## Audit Trail

- EXTRACTED: 10 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*