"""
ARQ worker settings (Schema doc Arch-12, Arch-20, Arch-21, Arch-38).

Run with:  arq workers.settings.WorkerSettings

Scheduled jobs:
- apollo_sync          (every 6h)   — pull Apollo, dedupe vs thh-backend, upsert prospects
- funnel_snapshot      (daily 00:30) — populate funnel_daily_snapshots          [Dev B]
- heat_recalc          (hourly)     — recompute heat_score / heat_level
- activation_sync      (daily 01:00) — poll thh-backend §9.5                    [Dev B]
"""

from __future__ import annotations

import os

from arq import cron
from arq.connections import RedisSettings

from .tasks.activation_sync import activation_sync
from .tasks.apollo_sync import apollo_sync
from .tasks.funnel_snapshot import funnel_snapshot
from .tasks.heat_recalc import heat_recalc


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    functions = [apollo_sync, funnel_snapshot, heat_recalc, activation_sync]
    cron_jobs = [
        # apollo_sync — every 6h on the hour (00:00, 06:00, 12:00, 18:00 UTC)
        cron(apollo_sync, hour={0, 6, 12, 18}, minute=0, run_at_startup=False),
        # heat_recalc — top of every hour
        cron(heat_recalc, minute=0, run_at_startup=False),
        # funnel_snapshot — daily 00:30 UTC (Dev B)
        cron(funnel_snapshot, hour=0, minute=30, run_at_startup=False),
        # activation_sync — daily 01:00 UTC (Dev B)
        cron(activation_sync, hour=1, minute=0, run_at_startup=False),
    ]
    max_jobs = 10
    job_timeout = 600
