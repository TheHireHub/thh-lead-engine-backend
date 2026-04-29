"""
Daily activation status sync (Schema doc Arch-38, §9.5).

For every promoted prospect (`thh_user_id IS NOT NULL`), call
thh-backend §9.5 to fetch:
  has_jobs, job_count, has_applicants, applicant_count,
  first_job_at, first_applicant_at

Update the prospect's milestone columns and fire a Telegram alert on
first-time activation.

Phase 2: thh_backend.get_activation_status returns a stub payload
(success=True, all zeros). When Dev A's Phase 3 wraps the real httpx
call, this worker's behaviour becomes meaningful — no code change here.

Schedule (in workers/settings.py): daily at 03:00 IST (after
funnel_snapshot at 02:00).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from database_connection.connection import AsyncSessionLocal
from services.audit.crud import AuditLogCRUD
from services.integrations import telegram, thh_backend
from services.prospects.models import Prospect
from setup_database import import_all_models

# Same registration trick as funnel_snapshot — make sure all FK targets
# are loaded so SQLAlchemy can resolve cross-service references.
import_all_models()

logger = logging.getLogger(__name__)


def _to_dt(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


async def activation_sync(ctx: dict) -> dict:
    """
    ARQ entrypoint. Iterates promoted prospects, polls thh-backend §9.5,
    updates milestone timestamps, fires Telegram on first-time activation.
    """
    checked = 0
    newly_activated_jobs = 0
    newly_activated_applicants = 0

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Prospect).where(
                Prospect.thh_user_id.is_not(None),
                Prospect.deleted_at.is_(None),
            )
        )
        prospects = list(result.scalars().all())
        logger.info("activation_sync: %d promoted prospects to check", len(prospects))

        for prospect in prospects:
            checked += 1
            try:
                resp = await thh_backend.get_activation_status(
                    thh_user_id=prospect.thh_user_id  # type: ignore[arg-type]
                )
            except Exception:
                logger.exception(
                    "activation_sync: thh-backend call failed for prospect %s",
                    prospect.id,
                )
                continue

            first_job_at = _to_dt(resp.get("first_job_at"))
            first_applicant_at = _to_dt(resp.get("first_applicant_at"))
            job_count = int(resp.get("job_count") or 0)
            applicant_count = int(resp.get("applicant_count") or 0)

            now = datetime.now(timezone.utc)

            jobs_newly_activated = False
            if first_job_at and prospect.first_job_created_at is None:
                prospect.first_job_created_at = first_job_at
                jobs_newly_activated = True

            applicants_newly_activated = False
            if first_applicant_at and prospect.first_applicant_received_at is None:
                prospect.first_applicant_received_at = first_applicant_at
                applicants_newly_activated = True

            # Always sync the running counts (they only ever go up in normal
            # operation, but guard against reset).
            if job_count != prospect.jobs_created_count:
                prospect.jobs_created_count = job_count
            if applicant_count != prospect.applicants_received_count:
                prospect.applicants_received_count = applicant_count

            if jobs_newly_activated or applicants_newly_activated:
                await db.commit()
                await db.refresh(prospect)
                if jobs_newly_activated:
                    newly_activated_jobs += 1
                    name = " ".join(
                        p for p in [prospect.first_name, prospect.last_name] if p
                    ) or prospect.email or f"prospect #{prospect.id}"
                    await telegram.send_alert(
                        f"🎯 First job created: {name} (prospect #{prospect.id})"
                    )
                if applicants_newly_activated:
                    newly_activated_applicants += 1
                    name = " ".join(
                        p for p in [prospect.first_name, prospect.last_name] if p
                    ) or prospect.email or f"prospect #{prospect.id}"
                    await telegram.send_alert(
                        f"🎉 First applicant received: {name} (prospect #{prospect.id})"
                    )
                await AuditLogCRUD.record(
                    db,
                    entity_type="prospect",
                    entity_id=prospect.id,
                    action="first_activation",
                    after_json={
                        "first_job_at": (
                            prospect.first_job_created_at.isoformat()
                            if prospect.first_job_created_at
                            else None
                        ),
                        "first_applicant_at": (
                            prospect.first_applicant_received_at.isoformat()
                            if prospect.first_applicant_received_at
                            else None
                        ),
                        "via": "activation_sync_worker",
                        "ts": now.isoformat(),
                    },
                )
            else:
                # Just sync the running counts.
                await db.commit()

    logger.info(
        "activation_sync: checked=%d new_jobs=%d new_applicants=%d",
        checked,
        newly_activated_jobs,
        newly_activated_applicants,
    )
    return {
        "checked": checked,
        "newly_activated_jobs": newly_activated_jobs,
        "newly_activated_applicants": newly_activated_applicants,
    }
