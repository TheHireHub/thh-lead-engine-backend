"""SQLAlchemy models for candidate_outreach (proposed §7.26-§7.27, Arch-45).

Tables:
- candidate_outreach              — one row per recruiter "Initiate Outreach" click
- candidate_outreach_candidates   — one row per candidate inside a click

Why two tables: candidate count grows linearly per click (10-15 today,
30-40+ later). Keeping per-candidate rows indexable lets us answer
"show every outreach this candidate appears in" without unpacking JSON.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import SMALLINT, TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


# -------------------------------------------------------------------- §7.26
class CandidateOutreach(Base):
    __tablename__ = "candidate_outreach"
    __table_args__ = (
        # Idempotency: HH-BE generates `dedup_key` per click. If the push
        # is retried we UPDATE-or-skip instead of double-inserting.
        UniqueConstraint("dedup_key", name="uk_co_dedup_key"),
        Index("idx_co_prospect_id", "prospect_id"),
        Index("idx_co_thh_job_id", "thh_job_id"),
        Index("idx_co_thh_company_id", "thh_company_id"),
        Index("idx_co_status", "status"),
        Index("idx_co_initiated_at", "initiated_at"),
        Index("idx_co_deleted_at", "deleted_at"),
        # Composite — powers prospect-detail "outreach activity" feed.
        Index("idx_co_prospect_initiated", "prospect_id", "initiated_at"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Resolved on receive (LEADS resolves THH company → prospect via
    # `prospects.thh_user_id` then `companies.website` domain match).
    # NULLable: events with no resolvable prospect land in the
    # "Unattributed" admin queue rather than getting dropped.
    prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )
    # If the THH job is also tracked in `prospect_company_jobs` (§7.21),
    # link it. Otherwise NULL — the THH job lives outside our DB.
    prospect_company_job_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("prospect_company_jobs.id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
    )

    # THH-side identifiers — no FK because they live in the THH database.
    # Stored as raw ints/strings; cross-system joins happen in the BFF.
    thh_job_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thh_job_title: Mapped[str] = mapped_column(String(255), nullable=False)
    thh_company_id: Mapped[int] = mapped_column(Integer, nullable=False)
    thh_company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    thh_company_domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Recruiter who clicked. NULL if HH-BE failed to attach actor info.
    initiated_by_thh_user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initiated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    initiated_by_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    initiated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    channel: Mapped[int] = mapped_column(
        TINYINT(unsigned=True),
        nullable=False,
        default=1,
        comment="see OUTREACH_CHANNELS proposed §6.29 (0=email, 1=linkedin, 2=mixed)",
    )
    candidate_count: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)

    status: Mapped[int] = mapped_column(
        TINYINT(unsigned=True),
        nullable=False,
        default=0,
        comment="see OUTREACH_STATUSES proposed §6.30 (0=initiated, 1=engaged, 2=hired, 3=dropped)",
    )
    status_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # Admin who flipped status. RESTRICT so deleting an admin user with
    # outstanding status changes is blocked (preserve attribution).
    status_updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # HH-BE-supplied idempotency key. Format suggestion:
    # `{thh_job_id}:{initiated_by_thh_user_id}:{epoch_seconds}`. Anything
    # 64 bytes works as long as HH-BE keeps it stable across retries.
    dedup_key: Mapped[str] = mapped_column(String(64), nullable=False)

    # Soft delete (Arch-19). Hard delete only via future GDPR endpoint.
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


# -------------------------------------------------------------------- §7.27
class CandidateOutreachCandidate(Base):
    __tablename__ = "candidate_outreach_candidates"
    __table_args__ = (
        # A given candidate appears at most once per outreach event.
        UniqueConstraint("outreach_id", "thh_candidate_id", name="uk_coc_event_candidate"),
        Index("idx_coc_outreach_id", "outreach_id"),
        Index("idx_coc_thh_candidate_id", "thh_candidate_id"),
        Index("idx_coc_outcome", "outcome"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    outreach_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("candidate_outreach.id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
    )

    # THH-side candidate ID. UUID-like string per HH-FE source.
    thh_candidate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    outcome: Mapped[Optional[int]] = mapped_column(
        TINYINT(unsigned=True),
        nullable=True,
        comment="see CANDIDATE_OUTCOMES proposed §6.31 (NULL = unknown / no_response yet)",
    )
    outcome_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    outcome_updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
