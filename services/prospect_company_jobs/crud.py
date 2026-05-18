"""
Async CRUD for the jobs subsystem.

The "Post a Job" workflow + at-risk one-way ratchet (Arch-40, 41) are
encoded in `JobCRUD.distribute()` and `JobCRUD.record_applicants()` —
don't bypass these.

Field-change history (`prospect_company_job_history`, §7.23) is wired
through `JobCRUD.update_with_history()` for the set of tracked fields.
Direct calls to `update()` skip history; use it only for non-audited
fields or migrations.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    ProspectCompanyJob,
    ProspectCompanyJobBoard,
    ProspectCompanyJobCandidate,
    ProspectCompanyJobCandidateNote,
    ProspectCompanyJobHistory,
)

# Fields that should write a history row whenever they change.
HISTORY_TRACKED_FIELDS: tuple[str, ...] = (
    "status",
    "paid_status",
    "confidentiality",
    "no_linkedin_post",
    "assigned_to_csm_user_id",
    "expectation_target",
)


def _stringify(v) -> Optional[str]:
    return None if v is None else str(v)


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
    async def list_for_company(
        db: AsyncSession, company_id: int
    ) -> list[ProspectCompanyJob]:
        result = await db.execute(
            select(ProspectCompanyJob)
            .where(
                ProspectCompanyJob.company_id == company_id,
                ProspectCompanyJob.deleted_at.is_(None),
            )
            .order_by(ProspectCompanyJob.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_filtered(
        db: AsyncSession,
        *,
        company_id: Optional[int] = None,
        status: Optional[int] = None,
        paid_status: Optional[int] = None,
        confidentiality: Optional[int] = None,
        no_linkedin_post: Optional[int] = None,
        assigned_to_csm_user_id: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ProspectCompanyJob]:
        """Combined filter for the CSM Board."""
        stmt = select(ProspectCompanyJob).where(ProspectCompanyJob.deleted_at.is_(None))
        if company_id is not None:
            stmt = stmt.where(ProspectCompanyJob.company_id == company_id)
        if status is not None:
            stmt = stmt.where(ProspectCompanyJob.status == status)
        if paid_status is not None:
            stmt = stmt.where(ProspectCompanyJob.paid_status == paid_status)
        if confidentiality is not None:
            stmt = stmt.where(ProspectCompanyJob.confidentiality == confidentiality)
        if no_linkedin_post is not None:
            stmt = stmt.where(ProspectCompanyJob.no_linkedin_post == no_linkedin_post)
        if assigned_to_csm_user_id is not None:
            stmt = stmt.where(
                ProspectCompanyJob.assigned_to_csm_user_id == assigned_to_csm_user_id
            )
        stmt = stmt.order_by(ProspectCompanyJob.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
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
    async def update(
        db: AsyncSession, job: ProspectCompanyJob, **fields
    ) -> ProspectCompanyJob:
        """Lower-level update — does NOT write history rows. Prefer update_with_history."""
        for k, v in fields.items():
            if v is not None:
                setattr(job, k, v)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def update_with_history(
        db: AsyncSession,
        job: ProspectCompanyJob,
        *,
        changes: dict,
        reason: Optional[str] = None,
        changed_by_user_id: Optional[int] = None,
    ) -> ProspectCompanyJob:
        """
        Update the job, then for every HISTORY_TRACKED_FIELDS that actually
        changed value, write a `prospect_company_job_history` row.
        """
        history_rows: list[ProspectCompanyJobHistory] = []
        for field, new_value in changes.items():
            if new_value is None:
                continue
            old_value = getattr(job, field, None)
            if old_value == new_value:
                continue
            setattr(job, field, new_value)
            if field in HISTORY_TRACKED_FIELDS:
                history_rows.append(
                    ProspectCompanyJobHistory(
                        prospect_company_job_id=job.id,
                        field_name=field,
                        from_value=_stringify(old_value),
                        to_value=_stringify(new_value),
                        reason=reason,
                        changed_by_user_id=changed_by_user_id,
                    )
                )
        for row in history_rows:
            db.add(row)
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
        - Insert one prospect_company_job_boards row per selected board with
          status=pending. Existing rows for the same board are left alone
          (caller can mark-posted/-failed individually after).
        - UI takes days; backend stores absolute at_risk_at.
        """
        now = datetime.now(timezone.utc)
        job.posted_at = now
        job.expectation_target = expectation_target
        job.at_risk_at = now + timedelta(days=days_threshold)

        # Each posting attempt is its own row. We only skip when the
        # board's LATEST row is still live (pending=0 or posted=1) — that
        # means the CSM is already actively posting there, no need to
        # duplicate. After a halt (status=4) or removed (3) or failed (2),
        # a new attempt creates a fresh row.
        existing_rows = await JobBoardCRUD.list_for_job(db, job.id)
        latest_by_board: dict[int, ProspectCompanyJobBoard] = {}
        for r in existing_rows:
            cur = latest_by_board.get(r.board)
            if cur is None or r.created_at > cur.created_at:
                latest_by_board[r.board] = r
        LIVE_STATUSES = (0, 1)  # pending, posted
        for board in boards:
            latest = latest_by_board.get(board)
            if latest is not None and latest.status in LIVE_STATUSES:
                continue
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
        db: AsyncSession,
        job: ProspectCompanyJob,
    ) -> ProspectCompanyJob:
        """
        Recompute total_applicants from the (live) board-posting rows and
        apply the Arch-41 one-way ratchet: if the total ever crosses target,
        set `target_met_at` once and never clear it.

        Used after a per-board applicant count is edited. The board row
        itself is updated by the caller (route uses `JobBoardCRUD
        .update_applicant_count(row, ...)` keyed by row_id); this helper
        only owns the aggregate + ratchet.

        Originally took `(board, applicant_count)` and ran a sub-select to
        find "the row for this (job, board)" — that broke after the
        UNIQUE(job, board) drop made multiple postings legal per board
        (MultipleResultsFound). The fix: this helper no longer touches
        any row; it just sums everything via `list_for_job`.
        """
        all_rows = await JobBoardCRUD.list_for_job(db, job.id)
        job.total_applicants = sum(r.applicant_count for r in all_rows)

        # One-way ratchet.
        if (
            job.target_met_at is None
            and job.expectation_target is not None
            and job.total_applicants >= job.expectation_target
        ):
            job.target_met_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(job)
        return job


class JobBoardCRUD:
    @staticmethod
    async def get_by_id(
        db: AsyncSession, board_row_id: int
    ) -> Optional[ProspectCompanyJobBoard]:
        result = await db.execute(
            select(ProspectCompanyJobBoard).where(
                ProspectCompanyJobBoard.id == board_row_id,
                ProspectCompanyJobBoard.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_job(
        db: AsyncSession, job_id: int
    ) -> list[ProspectCompanyJobBoard]:
        # Stable order: oldest first. With multiple rows per (job, board)
        # (after the unique drop), the drawer renders top-to-bottom as
        # 'first attempt → latest attempt' which reads naturally as a
        # history. Group-by-board on the FE if we ever want to collapse.
        result = await db.execute(
            select(ProspectCompanyJobBoard)
            .where(
                ProspectCompanyJobBoard.prospect_company_job_id == job_id,
                ProspectCompanyJobBoard.deleted_at.is_(None),
            )
            .order_by(ProspectCompanyJobBoard.created_at.asc(), ProspectCompanyJobBoard.id.asc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_posted(
        db: AsyncSession,
        row: ProspectCompanyJobBoard,
        *,
        external_url: Optional[str] = None,
    ) -> ProspectCompanyJobBoard:
        row.status = 1  # posted
        row.posted_at = datetime.now(timezone.utc)
        if external_url is not None:
            row.external_url = external_url
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def mark_failed(
        db: AsyncSession,
        row: ProspectCompanyJobBoard,
        *,
        notes: Optional[str] = None,
    ) -> ProspectCompanyJobBoard:
        row.status = 2  # failed
        if notes is not None:
            row.notes = notes
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def mark_removed(
        db: AsyncSession, row: ProspectCompanyJobBoard
    ) -> ProspectCompanyJobBoard:
        row.status = 3  # removed
        row.removed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def mark_stopped(
        db: AsyncSession, row: ProspectCompanyJobBoard
    ) -> ProspectCompanyJobBoard:
        """CSM clicked Halt on an active board posting. Same shape as
        mark_removed (sets removed_at) but uses status=4 'stopped' so the
        UI can distinguish 'manually halted by us' from 'pulled by the
        board itself / failed' or 'never posted'."""
        row.status = 4  # stopped
        row.removed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update_applicant_count(
        db: AsyncSession, row: ProspectCompanyJobBoard, *, applicant_count: int
    ) -> ProspectCompanyJobBoard:
        """Manual applicant-count edit on a single board posting. Lets the
        CSM keep numbers fresh for boards we don't auto-scrape (which is
        all of them today — LinkedIn included). Used by the drawer's
        inline-edit affordance."""
        row.applicant_count = max(0, int(applicant_count))
        await db.commit()
        await db.refresh(row)
        return row


class JobCandidateCRUD:
    @staticmethod
    async def get_by_id(
        db: AsyncSession, candidate_id: int
    ) -> Optional[ProspectCompanyJobCandidate]:
        result = await db.execute(
            select(ProspectCompanyJobCandidate).where(
                ProspectCompanyJobCandidate.id == candidate_id,
                ProspectCompanyJobCandidate.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_job(
        db: AsyncSession, job_id: int
    ) -> list[ProspectCompanyJobCandidate]:
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
        # Bump denormalised count on the job.
        await _bump_candidates_count(db, row.prospect_company_job_id, +1)
        return row

    @staticmethod
    async def update_status(
        db: AsyncSession,
        candidate: ProspectCompanyJobCandidate,
        *,
        status: int,
        decision_notes: Optional[str] = None,
    ) -> ProspectCompanyJobCandidate:
        """
        Status transitions per §6.23:
          0 proposed | 1 presented | 2 accepted | 3 rejected | 4 withdrawn | 5 hired
        Side effects:
          status=presented (1) -> set presented_at = now (if not already set)
          status in {2,3,4,5}  -> set decided_at  = now
        """
        candidate.status = status
        now = datetime.now(timezone.utc)
        if status == 1 and candidate.presented_at is None:
            candidate.presented_at = now
        if status in (2, 3, 4, 5):
            candidate.decided_at = now
        if decision_notes is not None:
            candidate.decision_notes = decision_notes
        await db.commit()
        await db.refresh(candidate)
        return candidate

    @staticmethod
    async def soft_delete(
        db: AsyncSession, candidate: ProspectCompanyJobCandidate
    ) -> None:
        candidate.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await _bump_candidates_count(db, candidate.prospect_company_job_id, -1)


async def _bump_candidates_count(db: AsyncSession, job_id: int, delta: int) -> None:
    """Update prospect_company_jobs.candidates_prepared denormalised count."""
    result = await db.execute(
        select(ProspectCompanyJob).where(ProspectCompanyJob.id == job_id)
    )
    job = result.scalar_one_or_none()
    if job is None:
        return
    job.candidates_prepared = max(0, (job.candidates_prepared or 0) + delta)
    await db.commit()


class JobCandidateNoteCRUD:
    """Append-only notes per candidate. Each row is one note; edits stay
    in-place on the same row, deletes are soft (Arch-19)."""

    @staticmethod
    async def get_by_id(
        db: AsyncSession, note_id: int
    ) -> Optional[ProspectCompanyJobCandidateNote]:
        result = await db.execute(
            select(ProspectCompanyJobCandidateNote).where(
                ProspectCompanyJobCandidateNote.id == note_id,
                ProspectCompanyJobCandidateNote.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_candidate(
        db: AsyncSession, candidate_id: int
    ) -> list[ProspectCompanyJobCandidateNote]:
        result = await db.execute(
            select(ProspectCompanyJobCandidateNote)
            .where(
                ProspectCompanyJobCandidateNote.candidate_id == candidate_id,
                ProspectCompanyJobCandidateNote.deleted_at.is_(None),
            )
            .order_by(ProspectCompanyJobCandidateNote.created_at.desc())
        )
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession, **fields
    ) -> ProspectCompanyJobCandidateNote:
        row = ProspectCompanyJobCandidateNote(**fields)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    @staticmethod
    async def update_body(
        db: AsyncSession,
        note: ProspectCompanyJobCandidateNote,
        *,
        body: str,
    ) -> ProspectCompanyJobCandidateNote:
        note.body = body
        await db.commit()
        await db.refresh(note)
        return note

    @staticmethod
    async def soft_delete(
        db: AsyncSession, note: ProspectCompanyJobCandidateNote
    ) -> None:
        note.deleted_at = datetime.now(timezone.utc)
        await db.commit()


class JobHistoryCRUD:
    @staticmethod
    async def list_for_job(
        db: AsyncSession, job_id: int, limit: int = 100
    ) -> list[ProspectCompanyJobHistory]:
        result = await db.execute(
            select(ProspectCompanyJobHistory)
            .where(ProspectCompanyJobHistory.prospect_company_job_id == job_id)
            .order_by(ProspectCompanyJobHistory.changed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

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


def group_by_company(jobs: Iterable[ProspectCompanyJob]) -> dict[int, list[ProspectCompanyJob]]:
    """In-memory grouping for the CSM Board's company-grouped view."""
    out: dict[int, list[ProspectCompanyJob]] = {}
    for j in jobs:
        out.setdefault(j.company_id, []).append(j)
    return out
