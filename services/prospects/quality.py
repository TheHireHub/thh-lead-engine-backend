"""
Quality score (ICP fit) computation (Schema doc Arch-22, §7.3 quality_score 0-10).

Pure DB-agnostic helper. Takes a `Prospect` (or its raw fields) and an
optional `Company` row, returns an int 0-10.

Scoring rules (tunable):

    Title keywords (capped at +5):
        ceo / founder / cofounder              +5
        cto / cmo / cfo / coo / chief          +4
        vp / vice president / head / director  +3
        manager / lead / principal             +2
        senior                                 +1

    Company funding stage (capped at +3):
        public / ipo / series_d / series_c     +3
        series_b                               +2
        series_a                               +1
        seed / pre_seed                        +0

    Company size (estimated employees if numeric, else 0):
        > 200                                  +2
        51-200                                 +1
        <= 50                                  +0

Total clamped to [0, 10].
"""

from __future__ import annotations

from typing import Optional


_TITLE_TIERS: list[tuple[int, tuple[str, ...]]] = [
    (5, ("ceo", "founder", "cofounder", "co-founder")),
    (4, ("cto", "cmo", "cfo", "coo", "chief ")),
    (3, ("vp ", "vice president", "head ", "head of", "director")),
    (2, ("manager", "principal", "lead ")),
    (1, ("senior",)),
]

_FUNDING_TIERS: dict[str, int] = {
    "public": 3, "ipo": 3, "series_d": 3, "series_c": 3,
    "series_b": 2,
    "series_a": 1,
    "seed": 0, "pre_seed": 0, "preseed": 0,
}


def _title_score(title: Optional[str]) -> int:
    if not title:
        return 0
    t = title.lower()
    for score, kws in _TITLE_TIERS:
        if any(kw in t for kw in kws):
            return score
    return 0


def _funding_score(funding_stage: Optional[str]) -> int:
    if not funding_stage:
        return 0
    return _FUNDING_TIERS.get(funding_stage.lower().strip(), 0)


def _size_score(size: Optional[str]) -> int:
    if not size:
        return 0
    raw = str(size).strip().lower()
    # numeric forms ("200", "51-200")
    if "-" in raw:
        try:
            high = int(raw.split("-")[1].strip())
        except ValueError:
            high = 0
    else:
        try:
            high = int(raw)
        except ValueError:
            high = 0
    if high > 200:
        return 2
    if high > 50:
        return 1
    return 0


def compute_quality_score(
    *,
    title: Optional[str] = None,
    company_size: Optional[str] = None,
    company_funding_stage: Optional[str] = None,
) -> int:
    """Return ICP-fit score in [0, 10]."""
    total = (
        _title_score(title)
        + _funding_score(company_funding_stage)
        + _size_score(company_size)
    )
    if total < 0:
        return 0
    if total > 10:
        return 10
    return total
