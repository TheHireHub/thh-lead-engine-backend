"""
SQLAlchemy models for prospect_company_jobs subsystem (§7.21-§7.24).

Tables:
- prospect_company_jobs                  — open jobs at prospect companies (sales hooks)
- prospect_company_job_candidates        — candidate matches per job
- prospect_company_job_history           — field-change audit per job
- prospect_company_job_boards            — junction: job × board, per-board posting state
- prospect_company_job_candidate_notes   — append-only notes per candidate
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


# -------------------------------------------------------------------- §7.21
class ProspectCompanyJob(Base):
    __tablename__ = "prospect_company_jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_external_id", name="uk_pcj_source_external"),
        Index("idx_pcj_company_id", "company_id"),
        Index("idx_pcj_status", "status"),
        Index("idx_pcj_paid_status", "paid_status"),
        Index("idx_pcj_confidentiality", "confidentiality"),
        Index("idx_pcj_department", "department"),
        Index("idx_pcj_seniority", "seniority"),
        Index("idx_pcj_source", "source"),
        Index("idx_pcj_no_linkedin_post", "no_linkedin_post"),
        Index("idx_pcj_at_risk_at", "at_risk_at"),
        Index("idx_pcj_target_met_at", "target_met_at"),
        Index("idx_pcj_assigned_csm", "assigned_to_csm_user_id"),
        Index("idx_pcj_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    company_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("companies.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seniority: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    employment_type: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    open_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    paid_status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    confidentiality: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    no_linkedin_post: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="1=block LinkedIn, 0=allowed")
    source: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source_external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    candidates_prepared: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="denormalised count")
    jd_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    posting_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="outreach destination URL (where the prospect should land after CR/email click); separate from jd_url which is the job description doc",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Job Distribution / At-Risk fields (Arch-40, 41)
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="when CSM clicked Post a Job")
    expectation_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="total applicants expected across boards")
    at_risk_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="posted_at + days threshold (one-way ratchet)")
    target_met_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="set on first time total>=target; never resets")
    total_applicants: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="aggregate across boards")
    assigned_to_csm_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )

    opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


# -------------------------------------------------------------------- §7.22
class ProspectCompanyJobCandidate(Base):
    __tablename__ = "prospect_company_job_candidates"
    __table_args__ = (
        Index("idx_pcjc_job_id", "prospect_company_job_id"),
        Index("idx_pcjc_thh_candidate_id", "thh_candidate_id"),
        Index("idx_pcjc_status", "status"),
        Index("idx_pcjc_presented_to", "presented_to_prospect_id"),
        Index("idx_pcjc_prepared_by", "prepared_by_user_id"),
        Index("idx_pcjc_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_company_job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospect_company_jobs.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    thh_candidate_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, comment="cross-DB pointer to thh-backend candidate; NULL if external"
    )
    candidate_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="denormalised snapshot")
    candidate_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    candidate_linkedin_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    candidate_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(Numeric(4, 3), nullable=True)
    match_method: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    match_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    presented_to_prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    presented_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    decision_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prepared_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


# -------------------------------------------------------------------- §7.23
class ProspectCompanyJobHistory(Base):
    __tablename__ = "prospect_company_job_history"
    __table_args__ = (
        Index("idx_pcjh_job_id", "prospect_company_job_id"),
        Index("idx_pcjh_changed_at", "changed_at"),
        Index("idx_pcjh_field_name", "field_name"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_company_job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospect_company_jobs.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    from_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    to_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    changed_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())


# -------------------------------------------------------------------- §7.24
class ProspectCompanyJobBoard(Base):
    """Junction: job × board, with per-board posting state and applicant counter."""

    __tablename__ = "prospect_company_job_boards"
    __table_args__ = (
        # Multiple rows per (job, board) are intentional: each row is one
        # posting attempt. After a halt, CSM can post the same board again
        # and a new row is created. Latest row's status drives the live
        # chip on the Performance table.
        Index("idx_pcjb_status", "status"),
        Index("idx_pcjb_board", "board"),
        Index("idx_pcjb_posted_at", "posted_at"),
        Index("idx_pcjb_deleted_at", "deleted_at"),
        Index("idx_pcjb_job_board", "prospect_company_job_id", "board"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_company_job_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospect_company_jobs.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    board: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see JOB_BOARDS §6.27")
    status: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="live posting URL")
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    removed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applicant_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="per-board applicants")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )


# ----------------------------- append-only notes per candidate (§7.22.1)
class ProspectCompanyJobCandidateNote(Base):
    """Append-only notes per candidate.

    Sibling to ProspectCompanyJobCandidate.decision_notes (a legacy single
    TEXT column kept for the Change-Status-with-note flow). New "Add Note"
    UX writes here so each note is preserved with author attribution and
    can be displayed back as a thread on the CSM candidate card.
    """

    __tablename__ = "prospect_company_job_candidate_notes"
    __table_args__ = (
        Index("idx_pcjcn_candidate_id", "candidate_id"),
        Index("idx_pcjcn_created_by", "created_by_user_id"),
        Index("idx_pcjcn_deleted_at", "deleted_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    candidate_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "prospect_company_job_candidates.id",
            ondelete="CASCADE",
            onupdate="CASCADE",
        ),
        nullable=False,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp(),
        server_onupdate=func.current_timestamp(),
    )
