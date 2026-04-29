"""
utm_source → marketing channel bucket mapping (powers the Funnel Board's
Visits-by-source split: SEO / Paid / Outreach).

Single source of truth — both the visits aggregate endpoint and any
worker that needs a bucket should import from here. Adding a new
utm_source value = edit `_BUCKETS` (no migration, no API change).

Buckets are intentionally coarse — the FE Funnel Board only renders
three bars. If a UTM string isn't in the table, it falls into `outreach`
(matches the legacy "everything else is reach-out" classification).
"""

from __future__ import annotations

from typing import Final

# Bucket names match the FE Funnel Board legend.
SEO: Final = "seo"
PAID: Final = "paid"
OUTREACH: Final = "outreach"

# Lowercase keys; lookup is case-insensitive.
_BUCKETS: dict[str, str] = {
    # SEO / organic
    "google": SEO,
    "google_organic": SEO,
    "organic": SEO,
    "bing": SEO,
    "duckduckgo": SEO,
    "seo": SEO,
    # Paid acquisition
    "google_ads": PAID,
    "googleads": PAID,
    "adwords": PAID,
    "facebook_ads": PAID,
    "fb_ads": PAID,
    "instagram_ads": PAID,
    "linkedin_ads": PAID,
    "linkedinads": PAID,
    "twitter_ads": PAID,
    "x_ads": PAID,
    "youtube_ads": PAID,
    "paid": PAID,
    # Outreach (cold email, LinkedIn DM, sequencer, etc.)
    "cold_email": OUTREACH,
    "outreach": OUTREACH,
    "apollo": OUTREACH,
    "warmly": OUTREACH,
    "lemlist": OUTREACH,
    "instantly": OUTREACH,
    "linkedin": OUTREACH,
    "linkedin_dm": OUTREACH,
    "linkedin_msg": OUTREACH,
    "email": OUTREACH,
}


def bucket_for(utm_source: str | None) -> str:
    """Return one of {SEO, PAID, OUTREACH}. Unknown / NULL → OUTREACH."""
    if not utm_source:
        return OUTREACH
    return _BUCKETS.get(utm_source.strip().lower(), OUTREACH)
