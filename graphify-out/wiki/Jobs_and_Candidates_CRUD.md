# Jobs and Candidates CRUD

> 18 nodes · cohesion 0.25

## Key Concepts

- **crud.py** (15 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **ProspectCompanyJobBoard** (12 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **ProspectCompanyJob** (11 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **ProspectCompanyJobCandidate** (11 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **ProspectCompanyJobHistory** (11 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **JobCandidateCRUD** (9 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **JobCRUD** (9 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **models.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **JobHistoryCRUD** (5 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **Increment per-board applicant count + total_applicants. Apply Arch-41         on** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **status=open AND target_met_at IS NULL AND at_risk_at < NOW() (Arch-41).** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **CSM "Post a Job" workflow (Arch-40):         - Set posted_at, expectation_target** (4 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **distribute()** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **list_at_risk()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **list_for_job()** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **Junction: job × board, with per-board posting state and applicant counter.** (2 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`
- **list_for_company()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- **record_applicants()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/crud.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/services/prospect_company_jobs/models.py`

## Audit Trail

- EXTRACTED: 39 (35%)
- INFERRED: 73 (65%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*