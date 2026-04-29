"""
Variant picker for landing-page A/B testing (Schema doc Arch-31, §7.10).

Sticky per visitor: hash(visitor_id + landing_page_id) -> modulo total weight.
Same visitor always sees the same variant for the same page.

Pure function — no DB calls. Caller passes in active variants and a visitor_id;
caller is responsible for filtering out paused/archived variants.
"""

from __future__ import annotations

import hashlib
from typing import Iterable, Optional

from .models import LandingPageVariant


def pick_variant(
    variants: Iterable[LandingPageVariant], visitor_id: str
) -> Optional[LandingPageVariant]:
    """
    Pick a variant deterministically for a visitor.

    Skips variants where status != active (0) or weight == 0.
    Returns None if no eligible variants remain (caller falls back to
    landing_pages.default_content_json).
    """
    eligible = [v for v in variants if v.status == 0 and v.weight > 0]
    if not eligible:
        return None

    # Sort by id for stability — guarantees the same modulo bucketing across
    # processes regardless of input order.
    eligible.sort(key=lambda v: v.id)

    total_weight = sum(v.weight for v in eligible)
    if total_weight == 0:
        return None

    # Deterministic hash bucket per (visitor, page).
    page_id = eligible[0].landing_page_id
    digest = hashlib.sha256(f"{visitor_id}:{page_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:16], 16) % total_weight

    cursor = 0
    for v in eligible:
        cursor += v.weight
        if bucket < cursor:
            return v
    return eligible[-1]  # unreachable; defensive
