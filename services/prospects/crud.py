"""
Async CRUD for the prospects domain.

NOTE: stage transitions MUST go through `change_stage()` which writes both
the prospects.stage column and a prospect_stage_history row in one
transaction. Don't update prospects.stage directly elsewhere.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.crud import AuditLogCRUD

from .models import (
    Prospect,
    ProspectChannel,
    ProspectMergeLog,
    ProspectMergeReviewQueue,
    ProspectStageHistory,
)


# Funnel stage ints (§6.2)
_STAGE_CONVERTED = 2

# Heat scoring rules (Schema doc Arch-21)
_HEAT_EVENT_SCORES: dict[str, int] = {
    "open": 1,
    "click": 2,
    "visit_no_signup": 3,
    "positive_reply": 5,
}


def _bucket_heat_level(score: int) -> int:
    """Map numeric heat_score to §6.25 heat_level: 0-2 cold, 3-7 warm, 8+ hot."""
    if score >= 8:
        return 2
    if score >= 3:
        return 1
    return 0


class ProspectCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, prospect_id: int) -> Optional[Prospect]:
        result = await db.execute(
            select(Prospect).where(Prospect.id == prospect_id, Prospect.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_linkedin(db: AsyncSession, linkedin_url: str) -> Optional[Prospect]:
        # Note: NOT filtered by deleted_at. Soft-deleted rows still hold the
        # unique constraint on linkedin_url, so dedupe must surface them.
        result = await db.execute(select(Prospect).where(Prospect.linkedin_url == linkedin_url))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[Prospect]:
        result = await db.execute(
            select(Prospect).where(Prospect.email == email, Prospect.deleted_at.is_(None))
        )
        return result.scalars().first()

    @staticmethod
    async def get_by_phone(db: AsyncSession, phone: str) -> Optional[Prospect]:
        result = await db.execute(
            select(Prospect).where(Prospect.phone == phone, Prospect.deleted_at.is_(None))
        )
        return result.scalars().first()

    @staticmethod
    async def get_by_apollo_id(db: AsyncSession, apollo_contact_id: str) -> Optional[Prospect]:
        result = await db.execute(select(Prospect).where(Prospect.apollo_contact_id == apollo_contact_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def find_duplicate(
        db: AsyncSession,
        *,
        linkedin_url: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
    ) -> Optional[Prospect]:
        """
        Arch-6 dedupe priority: LinkedIn URL > email > phone.

        Returns the first existing prospect matched by the strongest
        identifier supplied. Used by manual create + Apollo sync upsert +
        OTP-verify upsert.
        """
        if linkedin_url:
            existing = await ProspectCRUD.get_by_linkedin(db, linkedin_url)
            if existing:
                return existing
        if email:
            existing = await ProspectCRUD.get_by_email(db, email)
            if existing:
                return existing
        if phone:
            existing = await ProspectCRUD.get_by_phone(db, phone)
            if existing:
                return existing
        return None

    @staticmethod
    async def list_by_stage(
        db: AsyncSession, stage: Optional[int] = None, limit: int = 100, offset: int = 0
    ) -> list[Prospect]:
        stmt = select(Prospect).where(Prospect.deleted_at.is_(None))
        if stage is not None:
            stmt = stmt.where(Prospect.stage == stage)
        stmt = stmt.order_by(Prospect.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> Prospect:
        prospect = Prospect(**fields)
        db.add(prospect)
        await db.commit()
        await db.refresh(prospect)
        return prospect

    @staticmethod
    async def update(db: AsyncSession, prospect: Prospect, **fields) -> Prospect:
        for key, value in fields.items():
            if value is not None:
                setattr(prospect, key, value)
        await db.commit()
        await db.refresh(prospect)
        return prospect

    @staticmethod
    async def soft_delete(db: AsyncSession, prospect: Prospect) -> None:
        prospect.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    @staticmethod
    async def change_stage(
        db: AsyncSession,
        prospect: Prospect,
        *,
        to_stage: int,
        reason: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ) -> Prospect:
        """
        Atomically: update prospect.stage AND insert prospect_stage_history row
        AND write audit_log. Use this — never set prospect.stage directly.

        Side-effects:
        - On to_stage=converted (2): set converted_at if NULL (Arch-36 milestone).
        """
        from_stage = prospect.stage
        prospect.stage = to_stage
        if to_stage == _STAGE_CONVERTED and prospect.converted_at is None:
            prospect.converted_at = datetime.now(timezone.utc)
        db.add(
            ProspectStageHistory(
                prospect_id=prospect.id,
                from_stage=from_stage,
                to_stage=to_stage,
                reason=reason,
                changed_by_user_id=changed_by_user_id,
            )
        )
        await db.commit()
        await db.refresh(prospect)
        await AuditLogCRUD.record(
            db,
            actor_user_id=changed_by_user_id,
            entity_type="prospect",
            entity_id=prospect.id,
            action="stage_change",
            before_json={"stage": from_stage},
            after_json={"stage": to_stage, "reason": reason},
        )
        return prospect

    # ---- Milestone setters (Schema doc §3) -----------------------------
    # All idempotent: only set when currently NULL. Repeated calls are no-ops.

    @staticmethod
    async def set_registered(db: AsyncSession, prospect: Prospect) -> Prospect:
        if prospect.registered_at is None:
            prospect.registered_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(prospect)
        return prospect

    @staticmethod
    async def set_demo_booked(db: AsyncSession, prospect: Prospect) -> Prospect:
        if prospect.demo_booked_at is None:
            prospect.demo_booked_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(prospect)
        return prospect

    @staticmethod
    async def set_first_job_created(
        db: AsyncSession, prospect: Prospect, *, count: int
    ) -> Prospect:
        """Called by activation_sync when first_job_at flips from NULL→non-NULL."""
        changed = False
        if prospect.first_job_created_at is None and count > 0:
            prospect.first_job_created_at = datetime.now(timezone.utc)
            changed = True
        if prospect.jobs_created_count != count:
            prospect.jobs_created_count = count
            changed = True
        if changed:
            await db.commit()
            await db.refresh(prospect)
        return prospect

    @staticmethod
    async def set_first_applicant_received(
        db: AsyncSession, prospect: Prospect, *, count: int
    ) -> Prospect:
        changed = False
        if prospect.first_applicant_received_at is None and count > 0:
            prospect.first_applicant_received_at = datetime.now(timezone.utc)
            changed = True
        if prospect.applicants_received_count != count:
            prospect.applicants_received_count = count
            changed = True
        if changed:
            await db.commit()
            await db.refresh(prospect)
        return prospect

    @staticmethod
    async def set_thh_user_id(db: AsyncSession, prospect: Prospect, thh_user_id: int) -> Prospect:
        """Called by promote-to-THH after thh-backend §9.1 returns a users.id."""
        prospect.thh_user_id = thh_user_id
        await db.commit()
        await db.refresh(prospect)
        return prospect

    # ---- Touch + heat (Arch-7, Arch-21) --------------------------------

    @staticmethod
    async def record_touch(
        db: AsyncSession, prospect: Prospect, *, channel: int
    ) -> Prospect:
        """
        Bump last_touched_at + touch_count on the prospect AND upsert the
        per-channel junction row in `prospect_channels` (Arch-7).
        """
        now = datetime.now(timezone.utc)
        if prospect.first_touched_at is None:
            prospect.first_touched_at = now
        prospect.last_touched_at = now
        prospect.touch_count = (prospect.touch_count or 0) + 1

        # upsert prospect_channels row
        result = await db.execute(
            select(ProspectChannel).where(
                ProspectChannel.prospect_id == prospect.id,
                ProspectChannel.channel == channel,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            db.add(ProspectChannel(prospect_id=prospect.id, channel=channel, touch_count=1))
        else:
            row.touch_count += 1
            row.last_touched_at = now
        await db.commit()
        await db.refresh(prospect)
        return prospect

    @staticmethod
    async def apply_heat_event(
        db: AsyncSession, prospect: Prospect, *, event_type: str
    ) -> Prospect:
        """
        Increment heat_score per Arch-21 rule + re-bucket heat_level.
        Unknown event_type = 0 score = no-op write but still re-buckets.
        """
        delta = _HEAT_EVENT_SCORES.get(event_type, 0)
        if delta:
            prospect.heat_score = (prospect.heat_score or 0) + delta
        prospect.heat_level = _bucket_heat_level(prospect.heat_score or 0)
        await db.commit()
        await db.refresh(prospect)
        return prospect


class ProspectChannelCRUD:
    @staticmethod
    async def upsert_touch(db: AsyncSession, prospect_id: int, channel: int) -> ProspectChannel:
        result = await db.execute(
            select(ProspectChannel).where(
                ProspectChannel.prospect_id == prospect_id,
                ProspectChannel.channel == channel,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = ProspectChannel(prospect_id=prospect_id, channel=channel, touch_count=1)
            db.add(row)
        else:
            row.touch_count += 1
            row.last_touched_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row


class ProspectMergeReviewCRUD:
    @staticmethod
    async def list_pending(db: AsyncSession, limit: int = 50) -> list[ProspectMergeReviewQueue]:
        stmt = (
            select(ProspectMergeReviewQueue)
            .where(ProspectMergeReviewQueue.status == 0)
            .order_by(ProspectMergeReviewQueue.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def enqueue(
        db: AsyncSession,
        *,
        prospect_a_id: int,
        prospect_b_id: int,
        match_score: float,
        match_reason: str,
    ) -> ProspectMergeReviewQueue:
        """Add a fuzzy match to the review queue (status=0 pending §6.15)."""
        row = ProspectMergeReviewQueue(
            prospect_a_id=prospect_a_id,
            prospect_b_id=prospect_b_id,
            match_score=match_score,
            match_reason=match_reason,
            status=0,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def mark_merged(
        db: AsyncSession,
        row: ProspectMergeReviewQueue,
        *,
        reviewed_by_user_id: Optional[int] = None,
    ) -> ProspectMergeReviewQueue:
        row.status = 1
        row.reviewed_by_user_id = reviewed_by_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def mark_rejected(
        db: AsyncSession,
        row: ProspectMergeReviewQueue,
        *,
        reviewed_by_user_id: Optional[int] = None,
    ) -> ProspectMergeReviewQueue:
        row.status = 2
        row.reviewed_by_user_id = reviewed_by_user_id
        row.reviewed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row


class ProspectMergeLogCRUD:
    @staticmethod
    async def record_merge(
        db: AsyncSession,
        *,
        kept_prospect_id: int,
        merged_prospect_id: int,
        match_strategy: int,
        merged_by_user_id: Optional[int] = None,
        snapshot_json: Optional[dict] = None,
    ) -> ProspectMergeLog:
        row = ProspectMergeLog(
            kept_prospect_id=kept_prospect_id,
            merged_prospect_id=merged_prospect_id,
            match_strategy=match_strategy,
            merged_by_user_id=merged_by_user_id,
            snapshot_json=snapshot_json,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
