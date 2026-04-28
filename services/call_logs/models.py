"""SQLAlchemy model for call_logs (§7.25)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, func
from sqlalchemy.dialects.mysql import TINYINT
from sqlalchemy.orm import Mapped, mapped_column

from database_connection.connection import Base


class CallLog(Base):
    __tablename__ = "call_logs"
    __table_args__ = (
        Index("idx_cl_prospect_id", "prospect_id"),
        Index("idx_cl_caller_user_id", "caller_user_id"),
        Index("idx_cl_outcome", "outcome"),
        Index("idx_cl_callback_at", "callback_at"),
        Index("idx_cl_called_at", "called_at"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    prospect_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("prospects.id", ondelete="CASCADE", onupdate="CASCADE"), nullable=False
    )
    caller_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("admin_users.id", ondelete="RESTRICT", onupdate="CASCADE"), nullable=False
    )
    outcome: Mapped[int] = mapped_column(TINYINT(unsigned=True), nullable=False, comment="see CALL_OUTCOMES §6.26")
    callback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="set when outcome=call_back")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    called_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.current_timestamp())
