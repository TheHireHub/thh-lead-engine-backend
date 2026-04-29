"""
Apollo.io HTTP client (Schema doc Arch-12).

DB-agnostic per CLAUDE.md "Integrations" rules — pure HTTP wrapper. The
worker `workers/tasks/apollo_sync.py` orchestrates this client + CRUD.

Pull-based: Apollo's /v1/mixed_people/search is paginated. The worker
runs every 6 h (Arch-12). Webhook delivery is unreliable per Arch-12.

Env:
    APOLLO_API_KEY                — required for live calls; if absent the
                                     iterator yields nothing (dev no-op).
    APOLLO_SYNC_INTERVAL_HOURS    — informational; cron is in workers/settings.py
"""

from __future__ import annotations

import logging
import os
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

_APOLLO_BASE = "https://api.apollo.io"
_SEARCH_PATH = "/v1/mixed_people/search"


def _api_key() -> Optional[str]:
    return os.getenv("APOLLO_API_KEY") or None


async def search_people(
    *,
    page: int = 1,
    per_page: int = 100,
    filters: Optional[dict] = None,
    timeout: float = 30.0,
) -> dict:
    """
    Single-page POST to Apollo /v1/mixed_people/search. Returns the parsed
    JSON body. Raises on non-2xx.

    `filters` shape follows Apollo's documented people-search params; pass
    your ICP filter as-is. A missing APOLLO_API_KEY returns an empty page.
    """
    key = _api_key()
    if not key:
        logger.warning("apollo: APOLLO_API_KEY not set — returning empty page")
        return {"people": [], "pagination": {"page": page, "total_pages": 0}}

    payload = {"page": page, "per_page": per_page}
    if filters:
        payload.update(filters)

    headers = {
        "X-Api-Key": key,
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(_APOLLO_BASE + _SEARCH_PATH, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def iter_contacts(
    *,
    filters: Optional[dict] = None,
    per_page: int = 100,
    max_pages: int = 50,
) -> AsyncIterator[dict]:
    """
    Async iterator over every Apollo contact matching `filters`, paging
    until exhaustion or `max_pages`.
    """
    page = 1
    while page <= max_pages:
        body = await search_people(page=page, per_page=per_page, filters=filters)
        people = body.get("people") or []
        if not people:
            return
        for person in people:
            yield person
        pagination = body.get("pagination") or {}
        total_pages = pagination.get("total_pages") or page
        if page >= total_pages:
            return
        page += 1
