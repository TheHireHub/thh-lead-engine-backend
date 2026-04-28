"""
ARQ worker settings (Schema doc Arch-17).

Run with:  arq workers.settings.WorkerSettings

The four scheduled jobs are:
- apollo_sync          (every 6h)   — pull Apollo, dedupe vs thh-backend, upsert prospects
- funnel_snapshot      (daily)      — populate funnel_daily_snapshots
- heat_recalc          (hourly)     — recompute heat_score / heat_level
- activation_sync      (daily)      — poll thh-backend §9.5 for first_job_at + first_applicant_at
"""

from __future__ import annotations

import os

from arq.connections import RedisSettings

from .tasks.activation_sync import activation_sync
from .tasks.apollo_sync import apollo_sync
from .tasks.funnel_snapshot import funnel_snapshot
from .tasks.heat_recalc import heat_recalc


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    functions = [apollo_sync, funnel_snapshot, heat_recalc, activation_sync]
    cron_jobs: list = []  # populate via arq.cron once tasks are implemented
    max_jobs = 10
    job_timeout = 600
