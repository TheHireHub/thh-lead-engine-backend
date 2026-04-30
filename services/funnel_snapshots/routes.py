"""FastAPI routes for funnel snapshots (powers the dashboard)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_dashboard_read
from services.admin_users.models import AdminUser
from services.common.envelope import ok

from .crud import FunnelSnapshotCRUD
from .enums import CHANNELS, FUNNEL_STAGES, get_label
from .schemas import (
    AggregatedBucket,
    ConversionRatesOut,
    DailySeriesOut,
    DailySeriesPoint,
    SnapshotMode,
    SnapshotOut,
    TodayCountsOut,
)

router = APIRouter(prefix="/api/funnel-snapshots", tags=["funnel_snapshots"])


def _serialize(s) -> dict:
    out = SnapshotOut.model_validate(s).model_dump()
    out["stage_label"] = get_label(FUNNEL_STAGES, s.stage)
    if s.channel is not None:
        out["channel_label"] = get_label(CHANNELS, s.channel)
    return out


def _bucket_key(d: date, mode: SnapshotMode) -> tuple[str, date]:
    """Return (bucket_key, bucket_start) for a given date + mode."""
    if mode == "weekly":
        # ISO week — Monday-anchored
        iso_year, iso_week, _ = d.isocalendar()
        monday = d - timedelta(days=d.weekday())
        return f"{iso_year}-W{iso_week:02d}", monday
    if mode == "monthly":
        return f"{d.year:04d}-{d.month:02d}", date(d.year, d.month, 1)
    return d.isoformat(), d  # daily


@router.get("")
async def list_snapshots(
    from_date: date = Query(...),
    to_date: date = Query(...),
    stage: Optional[int] = None,
    channel: Optional[int] = None,
    mode: SnapshotMode = "daily",
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Daily snapshots, optionally aggregated to weekly/monthly buckets.

    `mode=daily` returns raw rows (default).
    `mode=weekly` groups by ISO week (Mon-anchored), summing prospect_count.
    `mode=monthly` groups by calendar month.
    """
    rows = await FunnelSnapshotCRUD.list_by_date_range(
        db, from_date=from_date, to_date=to_date, stage=stage, channel=channel
    )
    if mode == "daily":
        return ok([_serialize(s) for s in rows])

    # Aggregate.
    buckets: dict[tuple[str, int], AggregatedBucket] = {}
    for s in rows:
        key, start = _bucket_key(s.snapshot_date, mode)
        composite = (key, s.stage)
        if composite in buckets:
            buckets[composite].prospect_count += s.prospect_count
        else:
            buckets[composite] = AggregatedBucket(
                bucket_key=key,
                bucket_start=start,
                stage=s.stage,
                stage_label=get_label(FUNNEL_STAGES, s.stage),
                prospect_count=s.prospect_count,
            )
    out_rows = sorted(
        [b.model_dump() for b in buckets.values()],
        key=lambda r: (r["bucket_start"], r["stage"]),
    )
    return ok(out_rows)


# Stage label → int (Schema doc §6.2). Lowercase keys; matches what the FE
# Funnel Board sends as the `series` query string.
_STAGE_NAME_TO_INT: dict[str, int] = {
    "cold": 0,
    "curious": 1,
    "converted": 2,
    "lost": 3,
    "unsubscribed": 4,
}
_MILESTONE_KEYS: frozenset[str] = frozenset(
    {"registered", "demo_booked", "first_job_created", "first_applicant_received"}
)


@router.get("/daily")
async def daily_series(
    from_date: date = Query(...),
    to_date: date = Query(...),
    series: str = Query(
        ...,
        description=(
            "stage label (cold|curious|converted|lost|unsubscribed), "
            "milestone (registered|demo_booked|first_job_created|first_applicant_received), "
            "or 'visits'"
        ),
    ),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Pivot the funnel data into a `[{date, value}]` time series for ONE
    series — the shape the FE Funnel Board's line/bar chart consumes.

    Resolution:
    - stage labels (cold/curious/converted/lost/unsubscribed) → reads
      `funnel_daily_snapshots` (all-channel rollup, channel IS NULL).
    - milestone labels (registered/demo_booked/first_job_created/
      first_applicant_received) → cohort count grouped by `<milestone>_at`
      day from the live `prospects` table (Schema doc §3 — milestones
      are independent timestamps, not stages).
    - "visits" → `landing_page_visits` count per day.

    Output is dense: every day in `[from_date, to_date]` inclusive appears,
    `value=0` for days with no data.
    """
    if from_date > to_date:
        raise HTTPException(status_code=400, detail="from_date must be <= to_date")

    series_key = series.strip().lower()

    if series_key in _STAGE_NAME_TO_INT:
        sparse = await FunnelSnapshotCRUD.daily_stage_series(
            db, from_date=from_date, to_date=to_date, stage=_STAGE_NAME_TO_INT[series_key]
        )
    elif series_key in _MILESTONE_KEYS:
        sparse = await FunnelSnapshotCRUD.daily_milestone_series(
            db, from_date=from_date, to_date=to_date, milestone=series_key
        )
    elif series_key == "visits":
        # Cross-service read: landing_pages owns the table; we just count rows.
        from services.landing_pages.models import LandingPageVisit

        bucket = func.date(LandingPageVisit.visited_at).label("bucket")
        stmt = (
            select(bucket, func.count(LandingPageVisit.id))
            .where(
                func.date(LandingPageVisit.visited_at) >= from_date,
                func.date(LandingPageVisit.visited_at) <= to_date,
            )
            .group_by(bucket)
        )
        result = await db.execute(stmt)
        sparse = {row[0]: int(row[1] or 0) for row in result.all()}
    else:
        raise HTTPException(status_code=400, detail=f"unknown series '{series}'")

    # Densify — fill every day in the range with 0 if missing.
    points: list[DailySeriesPoint] = []
    cursor = from_date
    while cursor <= to_date:
        points.append(DailySeriesPoint(date=cursor, value=sparse.get(cursor, 0)))
        cursor = cursor + timedelta(days=1)

    return ok(
        DailySeriesOut(
            series=series_key,
            from_date=from_date,
            to_date=to_date,
            points=points,
        ).model_dump(mode="json")
    )


@router.get("/today")
async def today(
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Live current-day stage counts (read directly from `prospects`, not
    snapshots — snapshots are at most a day behind). Powers the
    dashboard's "today's funnel" widget.
    """
    counts = await FunnelSnapshotCRUD.today_live_counts_by_stage(db)
    payload = TodayCountsOut(
        stage_counts={int(k): int(v) for k, v in counts.items()},
        stage_labels={int(k): get_label(FUNNEL_STAGES, k) for k in counts.keys()},
        total=sum(counts.values()),
    )
    return ok(payload.model_dump())


@router.get("/conversion-rates")
async def conversion_rates(
    from_date: date = Query(...),
    to_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_dashboard_read),
) -> dict:
    """
    Coarse-grained funnel KPIs over a date range (Schema doc §3 KPI table).

    Stage counts come from the all-channel snapshot rollup; milestone
    counts come from the prospects table. Note: stage values are
    point-in-time totals summed over the range — high-traffic ranges
    skew this; treat as a smoothed view, not a precise cohort metric.
    """
    stage_totals = await FunnelSnapshotCRUD.stage_totals_in_range(
        db, from_date=from_date, to_date=to_date
    )
    milestones = await FunnelSnapshotCRUD.milestone_counts(
        db, from_date=from_date, to_date=to_date
    )

    # Snapshot worker (ARQ) populates `funnel_daily_snapshots` once a day.
    # In dev (no Redis/no worker) and on a fresh deploy before the first
    # daily run, that table is empty and stage_totals comes back all zeros,
    # which renders as a meaningless "0% conversion" on every Mgmt Board.
    # Fall back to live `prospects` counts so the dashboard is never blank.
    # The shape stays the same; the numbers are just point-in-time instead
    # of range-summed (BUG-015).
    if not any(stage_totals.values()):
        stage_totals = await FunnelSnapshotCRUD.today_live_counts_by_stage(db)

    cold = stage_totals.get(0, 0)
    curious = stage_totals.get(1, 0)
    converted = stage_totals.get(2, 0)
    demo_booked = milestones["demo_booked"]
    first_job_created = milestones["first_job_created"]

    payload = ConversionRatesOut(
        from_date=from_date,
        to_date=to_date,
        cold=cold,
        curious=curious,
        converted=converted,
        cold_to_curious_pct=(curious / cold * 100.0) if cold else 0.0,
        curious_to_converted_pct=(converted / curious * 100.0) if curious else 0.0,
        # Schema doc §3: Curious → Trial (= first_job_created milestone)
        curious_to_first_job_pct=(
            (first_job_created / curious * 100.0) if curious else 0.0
        ),
        # Schema doc §3: Demo Booked → Converted (Sales-owned)
        demo_to_converted_pct=(
            (converted / demo_booked * 100.0) if demo_booked else 0.0
        ),
        demo_booked=demo_booked,
        first_job_created=first_job_created,
        first_applicant_received=milestones["first_applicant_received"],
        registered=milestones["registered"],
    )
    return ok(payload.model_dump())
