"""
ARQ worker settings (Schema doc Arch-17).

Run with:  arq workers.settings.WorkerSettings

The four scheduled jobs are:
- apollo_sync          (every 6h)   — pull Apollo, dedupe vs thh-backend, upsert prospects
- funnel_snapshot      (daily)      — populate funnel_daily_snapshots
- heat_recalc          (hourly)     — recompute heat_score / heat_level
- activation_sync      (daily)      — poll thh-backend §9.5 for first_job_at + first_applicant_at

Cron schedules use IST (Asia/Kolkata) since that's the team's timezone.
DEV_A owns apollo_sync + heat_recalc cron entries; DEV_B owns
funnel_snapshot + activation_sync. Add to the cron_jobs list when
adding a new task; this is the only file both lanes touch and only
on cron-add events.
"""

from __future__ import annotations

import os

from arq.connections import RedisSettings
from arq.cron import cron

from .tasks.activation_sync import activation_sync
from .tasks.apollo_sync import apollo_sync
from .tasks.funnel_snapshot import funnel_snapshot
from .tasks.heat_recalc import heat_recalc


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    functions = [apollo_sync, funnel_snapshot, heat_recalc, activation_sync]
    cron_jobs = [
        # DEV_B: daily aggregate of prospects -> funnel_daily_snapshots, 02:00 IST.
        # IST is UTC+05:30 -> 02:00 IST == 20:30 UTC the previous day.
        cron(funnel_snapshot, hour=20, minute=30),
        # DEV_B: poll thh-backend activation status, 03:00 IST -> 21:30 UTC.
        cron(activation_sync, hour=21, minute=30),
        # TODO DEV_A: cron(apollo_sync, hour={...}) — every 6h per Arch-12.
        # TODO DEV_A: cron(heat_recalc, hour='*', minute=0) — hourly.
    ]
    max_jobs = 10
    job_timeout = 600
