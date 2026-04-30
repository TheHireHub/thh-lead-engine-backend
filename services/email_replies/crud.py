"""Async CRUD for email_replies (Schema doc §7.13, §6.8, §6.9, Arch-11)."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .classifier import BY_MANUAL, NEEDS_REVIEW_BELOW, classify_reply
from .models import EmailReply


class EmailReplyCRUD:
    @staticmethod
    async def get_by_id(db: AsyncSession, reply_id: int) -> Optional[EmailReply]:
        result = await db.execute(select(EmailReply).where(EmailReply.id == reply_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def list_for_prospect(
        db: AsyncSession, prospect_id: int, limit: int = 200
    ) -> list[EmailReply]:
        result = await db.execute(
            select(EmailReply)
            .where(EmailReply.prospect_id == prospect_id)
            .order_by(EmailReply.received_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_recent(
        db: AsyncSession,
        classification: Optional[int] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[EmailReply]:
        stmt = select(EmailReply)
        if classification is not None:
            stmt = stmt.where(EmailReply.classification == classification)
        stmt = stmt.order_by(EmailReply.received_at.desc()).limit(limit).offset(offset)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def list_needs_review(
        db: AsyncSession, limit: int = 100, offset: int = 0
    ) -> list[EmailReply]:
        """
        Replies the rule classifier punted on (low confidence OR explicitly
        flagged as `classified_by=manual` by the auto-fallback).
        """
        stmt = (
            select(EmailReply)
            .where(
                and_(
                    EmailReply.classified_by == BY_MANUAL,
                    EmailReply.classifier_confidence < NEEDS_REVIEW_BELOW,
                )
            )
            .order_by(EmailReply.received_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def create(
        db: AsyncSession,
        *,
        campaign_id: Optional[int],
        prospect_id: int,
        raw_body: str,
        subject: Optional[str] = None,
        classification: Optional[int] = None,
        classified_by: Optional[int] = None,
        classifier_confidence: Optional[float] = None,
    ) -> EmailReply:
        """
        Insert reply. If classification omitted, run rule classifier; if
        confidence < 0.6, the classifier itself flags it as manual so the
        needs-review queue catches it.
        """
        if classification is None:
            result = classify_reply(raw_body, subject)
            classification = result["classification"]
            classified_by = result["classified_by"]
            classifier_confidence = result["confidence"]
        elif classified_by is None:
            classified_by = BY_MANUAL
            if classifier_confidence is None:
                classifier_confidence = 1.0

        reply = EmailReply(
            campaign_id=campaign_id,
            prospect_id=prospect_id,
            raw_body=raw_body,
            subject=subject,
            classification=classification,
            classified_by=classified_by,
            classifier_confidence=classifier_confidence,
        )
        db.add(reply)
        await db.commit()
        await db.refresh(reply)
        return reply

    @staticmethod
    async def reclassify(
        db: AsyncSession, reply: EmailReply, *, classification: int
    ) -> EmailReply:
        """Manual override — sets classified_by=2 manual (§6.9)."""
        reply.classification = classification
        reply.classified_by = BY_MANUAL
        reply.classifier_confidence = 1.0
        await db.commit()
        await db.refresh(reply)
        return reply
