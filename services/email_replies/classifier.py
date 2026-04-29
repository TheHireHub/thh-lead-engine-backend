"""
Rule-based reply classifier (Schema doc Arch-11, "honor prateek").

DB-agnostic per CLAUDE.md "Services / integrations" rules — pure function
over primitives. Binary classification only (positive=0, negative=1) —
no neutral.

Returns a `ClassifyResult` dict:
    {classification: 0|1, classified_by: 0|2, confidence: float}

Confidence thresholds per DEV_A_INSTRUCTIONS:
    - keyword hit                 -> confidence 1.0, classified_by=0 rule
    - default fallback (no kw)    -> confidence 0.3, classified_by=2 manual
                                     (so it surfaces in `GET /needs-review`)
"""

from __future__ import annotations

from typing import Optional, TypedDict


# §6.8
POSITIVE = 0
NEGATIVE = 1

# §6.9
BY_RULE = 0
BY_LLM = 1
BY_MANUAL = 2

# Surface reviewer queue threshold per DEV_A_INSTRUCTIONS step 6.
NEEDS_REVIEW_BELOW = 0.6


_NEGATIVE_KEYWORDS: tuple[str, ...] = (
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
_POSITIVE_KEYWORDS: tuple[str, ...] = (
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


class ClassifyResult(TypedDict):
    classification: int
    classified_by: int
    confidence: float


def classify_reply(body: str, subject: Optional[str] = None) -> ClassifyResult:
    """Rule-based binary classifier."""
    haystack = ((subject or "") + " " + (body or "")).lower()
    for kw in _NEGATIVE_KEYWORDS:
        if kw in haystack:
            return {"classification": NEGATIVE, "classified_by": BY_RULE, "confidence": 1.0}
    for kw in _POSITIVE_KEYWORDS:
        if kw in haystack:
            return {"classification": POSITIVE, "classified_by": BY_RULE, "confidence": 1.0}
    # Default: positive low-confidence -> needs review.
    return {"classification": POSITIVE, "classified_by": BY_MANUAL, "confidence": 0.3}
