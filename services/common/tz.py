"""Business timezone helpers.

KPIs and "today" semantics are computed in the business TZ (default
`Asia/Kolkata`, UTC+05:30). Storage stays in UTC; only date cuts shift.

Set `BUSINESS_TZ_OFFSET_MINUTES` in env to override. The offset is
expressed as minutes east of UTC (IST = +330). DST is not applied —
appropriate for tenants whose business hours sit in a fixed-offset
timezone like IST. Add proper zoneinfo handling if a tenant operates
across DST.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

# Default = IST (+05:30). Stored as minutes east of UTC.
_DEFAULT_OFFSET_MINUTES = 330


def _offset_minutes() -> int:
    raw = os.getenv("BUSINESS_TZ_OFFSET_MINUTES")
    if raw is None:
        return _DEFAULT_OFFSET_MINUTES
    try:
        return int(raw)
    except (ValueError, TypeError):
        return _DEFAULT_OFFSET_MINUTES


def business_tz() -> timezone:
    return timezone(timedelta(minutes=_offset_minutes()))


def today_business() -> date:
    """Today's date in the business TZ — drives KPI cuts."""
    return datetime.now(business_tz()).date()


def business_offset_str() -> str:
    """MySQL CONVERT_TZ-friendly offset, e.g. '+05:30'."""
    minutes = _offset_minutes()
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"
