"""
Async CRUD for call_logs.

The 3xRNR auto-marker (Schema doc §5.5, Arch-43) lives here: every insert
where outcome=rnr increments prospects.rnr_count; on the third RNR we
write an audit_log entry. The exact "what happens to the prospect" is
P5 (PENDING USER INPUT) — see §14.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.crud import AuditLogCRUD
from services.prospects.models import Prospect

from .models import CallLog


class CallLogCRUD:
    @staticmethod
    async def list_for_prospect(db: AsyncSession, prospect_id: int) -> list[CallLog]:
        result = await db.execute(
            select(CallLog).where(CallLog.prospect_id == prospect_id).order_by(CallLog.called_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_callbacks_for_caller(db: AsyncSession, caller_user_id: int) -> list[CallLog]:
        result = await db.execute(
            select(CallLog).where(
                CallLog.caller_user_id == caller_user_id,
                CallLog.outcome == 2,  # call_back
                CallLog.callback_at.is_not(None),
            ).order_by(CallLog.callback_at.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def record(db: AsyncSession, **fields) -> CallLog:
        """
        Insert a call log + apply 3xRNR auto-marker side-effect.

        On RNR insert: increment prospects.rnr_count. If it reaches 3,
        write an audit_log row (action=auto_marked_not_interested).
        """
        log = CallLog(**fields)
        db.add(log)
        await db.flush()

        if fields.get("outcome") == 0:  # rnr
            result = await db.execute(select(Prospect).where(Prospect.id == fields["prospect_id"]))
            prospect = result.scalar_one_or_none()
            if prospect:
                prospect.rnr_count += 1
                if prospect.rnr_count >= 3:
                    # P5 PENDING: decide whether to set a milestone column or
                    # move stage. For now we just record the audit log.
                    await AuditLogCRUD.record(
                        db,
                        entity_type="prospect",
                        entity_id=prospect.id,
                        action="auto_marked_not_interested",
                        actor_user_id=None,
                        after_json={"rnr_count": prospect.rnr_count},
                    )

        await db.commit()
        await db.refresh(log)
        return log
