# Worker Tasks (ARQ)

> 15 nodes · cohesion 0.13

## Key Concepts

- **settings.py** (6 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/settings.py`
- **activation_sync.py** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/activation_sync.py`
- **apollo_sync.py** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/apollo_sync.py`
- **funnel_snapshot.py** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/funnel_snapshot.py`
- **heat_recalc.py** (3 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/heat_recalc.py`
- **activation_sync()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/activation_sync.py`
- **Daily activation status sync (Schema doc Arch-38, §9.5).  For every prospect wit** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/activation_sync.py`
- **apollo_sync()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/apollo_sync.py`
- **Apollo sync task (Schema doc Arch-12, §9.2).  Pull-based, every 6 hours. Upserts** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/apollo_sync.py`
- **funnel_snapshot()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/funnel_snapshot.py`
- **Daily funnel snapshot task (Schema doc Arch-20, §7.17).  Aggregates today's pros** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/funnel_snapshot.py`
- **heat_recalc()** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/heat_recalc.py`
- **Heat score recalculation (Schema doc Arch-21).  Rule (default, tunable): - email** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/heat_recalc.py`
- **ARQ worker settings (Schema doc Arch-17).  Run with:  arq workers.settings.Worke** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/settings.py`
- **WorkerSettings** (1 connections) — `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/settings.py`

## Relationships

- No strong cross-community connections detected

## Source Files

- `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/settings.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/activation_sync.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/apollo_sync.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/funnel_snapshot.py`
- `/Users/lakshayjain/thh/thh-lead-engine-backend/workers/tasks/heat_recalc.py`

## Audit Trail

- EXTRACTED: 28 (100%)
- INFERRED: 0 (0%)
- AMBIGUOUS: 0 (0%)

---

*Part of the graphify knowledge wiki. See [[index]] to navigate.*