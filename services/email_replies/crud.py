"""
Async CRUD for email_replies (Schema doc §7.13, §6.8, §6.9, Arch-11).

Rule-based binary classifier inlined here per "honor prateek" lock —
keyword rules give ~70% accuracy free; LLM is v2 per §10 cuts.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import EmailReply


# §6.8 classifications
_POSITIVE = 0
_NEGATIVE = 1

# §6.9 classified_by
_BY_RULE = 0
_BY_LLM = 1
_BY_MANUAL = 2

# Keyword rules (Prateek line 1572): "Don't send me" / "I am interested".
_NEGATIVE_KEYWORDS = (
    "don't send",
    "do not send",
    "unsubscribe",
    "remove me",
    "stop sending",
    "stop emailing",
    "not interested",
    "do not contact",
    "leave me alone",
    "take me off",
)
_POSITIVE_KEYWORDS = (
    "interested",
    "tell me more",
    "schedule",
    "book a",
    "demo",
    "let's talk",
    "lets talk",
    "sounds good",
    "yes please",
    "more info",
    "happy to chat",
)


def classify_text(raw_body: str, subject: Optional[str] = None) -> tuple[int, float]:
    """
    Rule-based binary classifier (Arch-11). Returns (classification, confidence).

    Priority: explicit negative keywords > positive keywords > default negative.
    Conservative default: when in doubt, classify negative + low confidence so
    a human reviewer (or LLM v2) can manually flip if needed.
    """
    haystack = ((subject or "") + " " + (raw_body or "")).lower()
    for kw in _NEGATIVE_KEYWORDS:
        if kw in haystack:
            return _NEGATIVE, 1.0
    for kw in _POSITIVE_KEYWORDS:
        if kw in haystack:
            return _POSITIVE, 1.0
    # Default: negative low-confidence (operator can override).
    return _NEGATIVE, 0.3


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
        Insert reply. If classification omitted, run rule classifier.

        - explicit classification + classified_by NULL  -> classified_by=manual(2)
        - omitted classification                        -> rule classifier, classified_by=rule(0)
        """
        if classification is None:
            classification, classifier_confidence = classify_text(raw_body, subject)
            classified_by = _BY_RULE
        elif classified_by is None:
            classified_by = _BY_MANUAL

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
    async def update_classification(
        db: AsyncSession,
        reply: EmailReply,
        *,
        classification: int,
    ) -> EmailReply:
        """Manual override — sets classified_by=2 manual (§6.9)."""
        reply.classification = classification
        reply.classified_by = _BY_MANUAL
        reply.classifier_confidence = 1.0
        await db.commit()
        await db.refresh(reply)
        return reply
