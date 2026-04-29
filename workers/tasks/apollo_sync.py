"""
Apollo sync task (Schema doc Arch-12, §9.2).

Pull-based, every 6 h (Arch-12). Apollo webhooks are flaky; pull is
predictable and idempotent.

Per md flow:
1. Page through Apollo /v1/mixed_people/search with the ICP filter
2. For each contact:
   a. Upsert `companies` row by domain (source=0 apollo)
   b. Call thh-backend `check-company-exists` (touch point §9.2);
      if exists, set `prospects.thh_user_id` (annotate, do not block import)
   c. Find existing prospect via dedupe priority (linkedin > email > phone)
   d. Insert new prospect or update existing one
   e. Touch `prospect_channels` row for channel=apollo (§6.3 channel=9)
   f. Write `audit_log` row for insert/update (Arch-18)
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

from database_connection.connection import AsyncSessionLocal
from services.audit.crud import AuditLogCRUD
from services.companies.crud import CompanyCRUD
from services.integrations import apollo, thh_backend
from services.prospects.crud import ProspectCRUD

logger = logging.getLogger(__name__)

# §6.3 channel int
_CHANNEL_APOLLO = 9
# §6.4 company source int
_COMPANY_SOURCE_APOLLO = 0


def _ilter_filters() -> dict:
    """ICP filter for Apollo people-search. Read from env or use defaults."""
    # md doesn't lock the ICP filter — leave as a single env knob for now.
    raw = os.getenv("APOLLO_ICP_FILTER_JSON")
    if raw:
        import json
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("apollo_sync: APOLLO_ICP_FILTER_JSON is not valid JSON, ignoring")
    return {}


def _split_name(full_name: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not full_name:
        return None, None
    parts = full_name.strip().split(" ", 1)
    return parts[0], (parts[1] if len(parts) > 1 else None)


def _company_fields(person: dict[str, Any]) -> dict[str, Any]:
    org = person.get("organization") or {}
    return {
        "name": org.get("name"),
        "domain": org.get("primary_domain") or org.get("website_url"),
        "linkedin_url": org.get("linkedin_url"),
        "industry": org.get("industry"),
        "size": org.get("estimated_num_employees"),
    }


async def _process_person(db, person: dict[str, Any]) -> dict[str, Any]:
    """Returns counters dict {inserted, updated, skipped, thh_overlap}."""
    counters = {"inserted": 0, "updated": 0, "skipped": 0, "thh_overlap": 0}

    apollo_id = person.get("id")
    email = person.get("email")
    linkedin_url = person.get("linkedin_url")
    phone_numbers = person.get("phone_numbers") or []
    phone = phone_numbers[0].get("sanitized_number") if phone_numbers else None

    if not apollo_id or (not linkedin_url and not email):
        counters["skipped"] += 1
        return counters

    # 2a. company upsert
    company_id: Optional[int] = None
    cf = _company_fields(person)
    if cf.get("domain") and cf.get("name"):
        company, _created = await CompanyCRUD.get_or_create_by_domain(
            db,
            domain=cf["domain"],
            name=cf["name"],
            source=_COMPANY_SOURCE_APOLLO,
            linkedin_url=cf.get("linkedin_url"),
            industry=cf.get("industry"),
            size=str(cf["size"]) if cf.get("size") is not None else None,
        )
        company_id = company.id

    # 2b. thh-backend dedupe annotation (§9.2)
    thh_user_id: Optional[int] = None
    try:
        resp = await thh_backend.check_company_exists(email=email, domain=cf.get("domain"))
        if resp and resp.get("exists"):
            thh_user_id = resp.get("thh_user_id")
            counters["thh_overlap"] += 1
    except (httpx.HTTPError, httpx.RequestError) as exc:
        logger.warning("apollo_sync: thh-backend check failed (%s) — continuing", exc)

    # 2c. dedupe priority lookup (Arch-6)
    existing = await ProspectCRUD.find_duplicate(
        db, linkedin_url=linkedin_url, email=email, phone=phone
    )

    first_name, last_name = _split_name(person.get("name"))

    if existing is None:
        prospect = await ProspectCRUD.create(
            db,
            linkedin_url=linkedin_url,
            email=email,
            phone=phone,
            first_name=person.get("first_name") or first_name,
            last_name=person.get("last_name") or last_name,
            title=person.get("title"),
            company_id=company_id,
            apollo_contact_id=apollo_id,
            source_channel=_CHANNEL_APOLLO,
            thh_user_id=thh_user_id,
        )
        await AuditLogCRUD.record(
            db,
            actor_user_id=None,  # system
            entity_type="prospect",
            entity_id=prospect.id,
            action="apollo_create",
            after_json={"apollo_contact_id": apollo_id, "company_id": company_id},
        )
        counters["inserted"] += 1
    else:
        # Lightweight update — fill missing identifiers + apollo_contact_id.
        updates: dict[str, Any] = {}
        if not existing.apollo_contact_id and apollo_id:
            updates["apollo_contact_id"] = apollo_id
        if not existing.email and email:
            updates["email"] = email
        if not existing.linkedin_url and linkedin_url:
            updates["linkedin_url"] = linkedin_url
        if not existing.phone and phone:
            updates["phone"] = phone
        if not existing.title and person.get("title"):
            updates["title"] = person["title"]
        if not existing.company_id and company_id:
            updates["company_id"] = company_id
        if not existing.thh_user_id and thh_user_id:
            updates["thh_user_id"] = thh_user_id

        if updates:
            await ProspectCRUD.update(db, existing, **updates)
            await AuditLogCRUD.record(
                db,
                actor_user_id=None,
                entity_type="prospect",
                entity_id=existing.id,
                action="apollo_update",
                after_json=updates,
            )
            counters["updated"] += 1
        prospect = existing

    # 2e. touch channel apollo (Arch-7)
    await ProspectCRUD.record_touch(db, prospect, channel=_CHANNEL_APOLLO)
    return counters


async def apollo_sync(ctx: dict) -> dict:
    """ARQ entrypoint. Returns aggregate counters."""
    totals = {"inserted": 0, "updated": 0, "skipped": 0, "thh_overlap": 0, "errors": 0}
    filters = _ilter_filters()

    async with AsyncSessionLocal() as db:
        try:
            async for person in apollo.iter_contacts(filters=filters):
                try:
                    counters = await _process_person(db, person)
                    for k, v in counters.items():
                        totals[k] += v
                except Exception as exc:  # noqa: BLE001 — keep worker alive
                    logger.exception("apollo_sync: per-person error: %s", exc)
                    totals["errors"] += 1
        except (httpx.HTTPError, httpx.RequestError) as exc:
            logger.exception("apollo_sync: Apollo API error: %s", exc)

    logger.info("apollo_sync done: %s", totals)
    return totals
