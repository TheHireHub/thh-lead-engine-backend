"""
Async CRUD for candidate_outreach.

Two responsibilities:
1. **Ingest** — receive a HH-BE Initiate Outreach push, resolve the THH
   company → LEADS prospect, insert parent + child rows atomically,
   ensure idempotency via `dedup_key` UNIQUE.
2. **Mutate** — admin flips status (initiated → engaged → hired/dropped)
   or per-candidate outcome (no_response/replied/.../hired/rejected).
   Each mutation writes one `audit_log` row (Arch-18).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.audit.crud import AuditLogCRUD
from services.companies.models import Company
from services.prospects.models import Prospect

from .models import CandidateOutreach, CandidateOutreachCandidate


class CandidateOutreachCRUD:
    # ─── Resolution helpers ────────────────────────────────────────────

    @staticmethod
    async def _resolve_prospect_id(
        db: AsyncSession, *, thh_company_id: int, thh_company_domain: Optional[str]
    ) -> Optional[int]:
        """
        Best-effort match of a THH company to a LEADS prospect.

        Order:
          1. `prospects.thh_user_id == thh_company_id` (set by EP-PROMOTE).
          2. `companies.domain == thh_company_domain` → join via `prospects.company_id`.
          3. None — caller leaves prospect_id NULL (Unattributed queue).
        """
        # Fast path: company already promoted via EP-PROMOTE.
        result = await db.execute(
            select(Prospect.id)
            .where(Prospect.thh_user_id == thh_company_id, Prospect.deleted_at.is_(None))
            .order_by(Prospect.id.asc())
            .limit(1)
        )
        pid = result.scalar_one_or_none()
        if pid is not None:
            return pid

        # Fallback: domain match against the companies table, then any
        # live prospect at that company.
        if thh_company_domain:
            domain_lower = thh_company_domain.strip().lower()
            if domain_lower:
                result = await db.execute(
                    select(Company.id)
                    .where(
                        func.lower(Company.domain) == domain_lower,
                        Company.deleted_at.is_(None),
                    )
                    .limit(1)
                )
                company_id = result.scalar_one_or_none()
                if company_id is not None:
                    result = await db.execute(
                        select(Prospect.id)
                        .where(
                            Prospect.company_id == company_id,
                            Prospect.deleted_at.is_(None),
                        )
                        .order_by(Prospect.id.asc())
                        .limit(1)
                    )
                    pid = result.scalar_one_or_none()
                    if pid is not None:
                        return pid

        return None

    @staticmethod
    def _normalise_to_utc_naive(dt: datetime) -> datetime:
        """Coerce inbound `initiated_at` to UTC, stored as a naive value.

        MySQL `DATETIME` carries no tz, so we fix the convention at the
        boundary: the column always means "UTC". A tz-aware payload is
        converted; a naive payload is *assumed* UTC (defensible: HH-BE's
        contract is to send UTC, and this matches `created_at`'s server
        default `CURRENT_TIMESTAMP` which MySQL writes in session tz —
        kept UTC by setting `time_zone='+00:00'` on the connection).
        """
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @staticmethod
    def _build_dedup_key(payload) -> str:
        """Synthesise a dedup key when HH-BE didn't supply one. Format:
        `{job_id}:{user_id|0}:{epoch_seconds}` — stable across retries
        for the same click."""
        dt = payload.initiated_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        epoch = int(dt.timestamp())
        actor = payload.initiated_by.thh_user_id or 0
        return f"{payload.thh_job_id}:{actor}:{epoch}"

    # ─── Ingest (THH → LEADS) ──────────────────────────────────────────

    @staticmethod
    async def ingest(
        db: AsyncSession, payload, *, ip_address: Optional[str] = None
    ) -> tuple[CandidateOutreach, bool]:
        """
        Insert a new outreach event with all candidate children.

        Returns `(outreach, created)` where `created` is False if the same
        `dedup_key` already exists (idempotency win — HH-BE retried).
        """
        dedup_key = payload.dedup_key or CandidateOutreachCRUD._build_dedup_key(payload)

        # Idempotency: if we have a row with this dedup_key already, skip.
        existing = await db.execute(
            select(CandidateOutreach).where(CandidateOutreach.dedup_key == dedup_key)
        )
        existing_row = existing.scalar_one_or_none()
        if existing_row is not None:
            return existing_row, False

        prospect_id = await CandidateOutreachCRUD._resolve_prospect_id(
            db,
            thh_company_id=payload.thh_company_id,
            thh_company_domain=payload.thh_company_domain,
        )

        outreach = CandidateOutreach(
            prospect_id=prospect_id,
            prospect_company_job_id=None,  # not auto-linked in v1
            thh_job_id=payload.thh_job_id,
            thh_job_title=payload.thh_job_title,
            thh_company_id=payload.thh_company_id,
            thh_company_name=payload.thh_company_name,
            thh_company_domain=payload.thh_company_domain,
            initiated_by_thh_user_id=payload.initiated_by.thh_user_id,
            initiated_by_email=payload.initiated_by.email,
            initiated_by_name=payload.initiated_by.name,
            initiated_at=CandidateOutreachCRUD._normalise_to_utc_naive(
                payload.initiated_at
            ),
            channel=payload.channel,
            candidate_count=len(payload.candidates),
            status=0,  # initiated
            dedup_key=dedup_key,
        )
        db.add(outreach)
        await db.flush()  # obtain `outreach.id` without committing yet

        # Bulk insert children (single round-trip regardless of count).
        if payload.candidates:
            db.add_all(
                [
                    CandidateOutreachCandidate(
                        outreach_id=outreach.id,
                        thh_candidate_id=c.thh_candidate_id,
                        first_name=c.first_name,
                        last_name=c.last_name,
                        email=c.email,
                        linkedin_url=c.linkedin_url,
                    )
                    for c in payload.candidates
                ]
            )

        await db.commit()
        await db.refresh(outreach)

        # Audit (separate transaction by AuditLogCRUD.record).
        await AuditLogCRUD.record(
            db,
            entity_type="candidate_outreach",
            entity_id=outreach.id,
            action="outreach_received",
            actor_user_id=None,  # system actor — pushed by THH
            after_json={
                "thh_job_id": outreach.thh_job_id,
                "thh_company_id": outreach.thh_company_id,
                "candidate_count": outreach.candidate_count,
                "channel": outreach.channel,
                "prospect_id": outreach.prospect_id,
            },
            ip_address=ip_address,
        )
        return outreach, True

    # ─── Reads ─────────────────────────────────────────────────────────

    @staticmethod
    async def get_by_id(
        db: AsyncSession, outreach_id: int
    ) -> Optional[CandidateOutreach]:
        result = await db.execute(
            select(CandidateOutreach).where(
                CandidateOutreach.id == outreach_id,
                CandidateOutreach.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_prospect(
        db: AsyncSession, prospect_id: int, limit: int = 50, offset: int = 0
    ) -> list[CandidateOutreach]:
        result = await db.execute(
            select(CandidateOutreach)
            .where(
                CandidateOutreach.prospect_id == prospect_id,
                CandidateOutreach.deleted_at.is_(None),
            )
            .order_by(CandidateOutreach.initiated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_recent(
        db: AsyncSession,
        *,
        status: Optional[int] = None,
        unattributed_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[CandidateOutreach]:
        stmt = select(CandidateOutreach).where(CandidateOutreach.deleted_at.is_(None))
        if status is not None:
            stmt = stmt.where(CandidateOutreach.status == status)
        if unattributed_only:
            stmt = stmt.where(CandidateOutreach.prospect_id.is_(None))
        stmt = (
            stmt.order_by(CandidateOutreach.initiated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_candidates(
        db: AsyncSession, outreach_id: int
    ) -> list[CandidateOutreachCandidate]:
        result = await db.execute(
            select(CandidateOutreachCandidate)
            .where(CandidateOutreachCandidate.outreach_id == outreach_id)
            .order_by(CandidateOutreachCandidate.id.asc())
        )
        return list(result.scalars().all())

    # ─── Mutations (admin) ─────────────────────────────────────────────

    @staticmethod
    async def update_status(
        db: AsyncSession,
        outreach: CandidateOutreach,
        *,
        new_status: int,
        actor_user_id: int,
        notes: Optional[str] = None,
    ) -> CandidateOutreach:
        """
        One-way ratchet: once status=hired (2), block any further changes
        — matches Arch-41-style intent (hired is a permanent positive
        signal). Dropped (3) is also terminal but admin can revive by
        setting back to engaged via SQL if needed (no UI path for safety).
        """
        if outreach.status == 2:
            return outreach  # already hired, no-op
        before = {"status": outreach.status, "notes": outreach.notes}
        outreach.status = new_status
        outreach.status_updated_at = datetime.now(timezone.utc)
        outreach.status_updated_by_user_id = actor_user_id
        if notes is not None:
            outreach.notes = notes
        await db.commit()
        await db.refresh(outreach)

        await AuditLogCRUD.record(
            db,
            entity_type="candidate_outreach",
            entity_id=outreach.id,
            action=f"outreach_status_{new_status}",
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"status": outreach.status, "notes": outreach.notes},
        )
        return outreach

    @staticmethod
    async def update_candidate_outcome(
        db: AsyncSession,
        candidate: CandidateOutreachCandidate,
        *,
        new_outcome: int,
        actor_user_id: int,
    ) -> CandidateOutreachCandidate:
        before = {"outcome": candidate.outcome}
        candidate.outcome = new_outcome
        candidate.outcome_at = datetime.now(timezone.utc)
        candidate.outcome_updated_by_user_id = actor_user_id
        await db.commit()
        await db.refresh(candidate)

        await AuditLogCRUD.record(
            db,
            entity_type="candidate_outreach_candidate",
            entity_id=candidate.id,
            action=f"candidate_outcome_{new_outcome}",
            actor_user_id=actor_user_id,
            before_json=before,
            after_json={"outcome": candidate.outcome},
        )
        return candidate

    @staticmethod
    async def soft_delete(
        db: AsyncSession, outreach: CandidateOutreach, *, actor_user_id: int
    ) -> None:
        """Soft delete (Arch-19). Admin-only. Children left in place;
        CASCADE applies on hard delete via future GDPR endpoint."""
        outreach.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await AuditLogCRUD.record(
            db,
            entity_type="candidate_outreach",
            entity_id=outreach.id,
            action="outreach_deleted",
            actor_user_id=actor_user_id,
        )

    @staticmethod
    async def get_candidate_by_id(
        db: AsyncSession, candidate_row_id: int
    ) -> Optional[CandidateOutreachCandidate]:
        result = await db.execute(
            select(CandidateOutreachCandidate).where(
                CandidateOutreachCandidate.id == candidate_row_id
            )
        )
        return result.scalar_one_or_none()
