"""
Async CRUD for the jobs subsystem.

The "Post a Job" workflow + at-risk one-way ratchet (Arch-40, 41) are
encoded in `JobCRUD.distribute()` and `JobCRUD.record_applicants()` —
don't bypass these.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ProspectCompanyJob, ProspectCompanyJobBoard,
    ProspectCompanyJobCandidate, ProspectCompanyJobHistory,
)


class JobCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, job_id: int) -> Optional[ProspectCompanyJob]:
        result = await db.execute(
            select(ProspectCompanyJob).where(
                ProspectCompanyJob.id == job_id,
                ProspectCompanyJob.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_company(db: AsyncSession, company_id: int) -> list[ProspectCompanyJob]:
        result = await db.execute(
            select(ProspectCompanyJob).where(
                ProspectCompanyJob.company_id == company_id,
                ProspectCompanyJob.deleted_at.is_(None),
            ).order_by(ProspectCompanyJob.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_at_risk(db: AsyncSession) -> list[ProspectCompanyJob]:
        """status=open AND target_met_at IS NULL AND at_risk_at < NOW() (Arch-41)."""
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(ProspectCompanyJob).where(
                ProspectCompanyJob.status == 0,
                ProspectCompanyJob.target_met_at.is_(None),
                ProspectCompanyJob.at_risk_at < now,
                ProspectCompanyJob.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> ProspectCompanyJob:
        job = ProspectCompanyJob(**fields)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def update(db: AsyncSession, job: ProspectCompanyJob, **fields) -> ProspectCompanyJob:
        for k, v in fields.items():
            if v is not None:
                setattr(job, k, v)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def distribute(
        db: AsyncSession,
        job: ProspectCompanyJob,
        *,
        boards: list[int],
        expectation_target: int,
        days_threshold: int,
        posted_by_user_id: Optional[int] = None,
    ) -> ProspectCompanyJob:
        """
        CSM "Post a Job" workflow (Arch-40):
        - Set posted_at, expectation_target, at_risk_at on the job.
        - Insert/update one prospect_company_job_boards row per board.
        - UI takes days; backend stores absolute at_risk_at.
        """
        now = datetime.now(timezone.utc)
        job.posted_at = now
        job.expectation_target = expectation_target
        job.at_risk_at = now + timedelta(days=days_threshold)

        for board in boards:
            db.add(
                ProspectCompanyJobBoard(
                    prospect_company_job_id=job.id,
                    board=board,
                    status=0,  # pending
                    posted_by_user_id=posted_by_user_id,
                )
            )
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def record_applicants(
        db: AsyncSession, job: ProspectCompanyJob, *, board: int, applicant_count: int
    ) -> ProspectCompanyJob:
        """
        Increment per-board applicant count + total_applicants. Apply Arch-41
        one-way ratchet: if total ever crosses target, set target_met_at once.
        """
        # Update per-board counter
        result = await db.execute(
            select(ProspectCompanyJobBoard).where(
                ProspectCompanyJobBoard.prospect_company_job_id == job.id,
                ProspectCompanyJobBoard.board == board,
            )
        )
        board_row = result.scalar_one_or_none()
        if board_row is not None:
            board_row.applicant_count = applicant_count

        # Recompute aggregate
        result = await db.execute(
            select(ProspectCompanyJobBoard).where(
                ProspectCompanyJobBoard.prospect_company_job_id == job.id
            )
        )
        rows = list(result.scalars().all())
        job.total_applicants = sum(r.applicant_count for r in rows)

        # One-way ratchet
        if (
            job.target_met_at is None
            and job.expectation_target is not None
            and job.total_applicants >= job.expectation_target
        ):
            job.target_met_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(job)
        return job


class JobCandidateCRUD:
    @staticmethod
    async def list_for_job(db: AsyncSession, job_id: int) -> list[ProspectCompanyJobCandidate]:
        result = await db.execute(
            select(ProspectCompanyJobCandidate).where(
                ProspectCompanyJobCandidate.prospect_company_job_id == job_id,
                ProspectCompanyJobCandidate.deleted_at.is_(None),
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(db: AsyncSession, **fields) -> ProspectCompanyJobCandidate:
        row = ProspectCompanyJobCandidate(**fields)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


class JobHistoryCRUD:
    @staticmethod
    async def record(
        db: AsyncSession,
        *,
        prospect_company_job_id: int,
        field_name: str,
        from_value: Optional[str],
        to_value: Optional[str],
        reason: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ) -> ProspectCompanyJobHistory:
        row = ProspectCompanyJobHistory(
            prospect_company_job_id=prospect_company_job_id,
            field_name=field_name,
            from_value=from_value,
            to_value=to_value,
            reason=reason,
            changed_by_user_id=changed_by_user_id,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
