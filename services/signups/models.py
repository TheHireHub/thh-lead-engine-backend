"""SQLAlchemy model for signups (§7.12)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class Signup(Base):
    __tablename__ = "signups"
    __table_args__ = (
        Index("idx_signups_email", "email"),
        Index("idx_signups_landing_page_id", "landing_page_id"),
        Index("idx_signups_prospect_id", "prospect_id"),
        Index("idx_signups_visitor_id", "visitor_id"),
        Index("idx_signups_created_at", "created_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    landing_page_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("landing_pages.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    prospect_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="SET NULL", onupdate="CASCADE"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    domain: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    request_type: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, default=0, comment="see SIGNUP_REQUEST_TYPES §6.11")
    payload_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    visitor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    otp_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="set on OTP verify; triggers stage promote")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
