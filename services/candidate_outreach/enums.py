"""
Candidate-outreach TINYINT enum mappings.

Per Arch-29: TINYINT UNSIGNED columns + dict maps. Helpers (`get_label`,
`get_value`, `reverse`) re-exported from `services.common.enums` to keep
behavior identical to every other service.

These three enums are NOT yet in `services/common/enums.py` because the
feature pre-dates the schema doc update (proposed §6.29-6.31). Once
Ishank locks the schema addition we move them into common and update
this file to re-export, matching the pattern in `call_logs/enums.py`.
"""

from __future__ import annotations

from services.common.enums import get_label, get_value, reverse

# Channel the recruiter used to send outreach (proposed §6.29).
OUTREACH_CHANNELS: dict[int, str] = {
    0: "email",
    1: "linkedin",
    2: "mixed",
}

# Status of the overall outreach event — admin-mutable on LEADS-FE
# (proposed §6.30). One-way ratchet: once `hired`, never revert. CSM
# uses this for product-engagement signal at the company prospect level.
OUTREACH_STATUSES: dict[int, str] = {
    0: "initiated",
    1: "engaged",
    2: "hired",
    3: "dropped",
}

# Per-candidate outcome inside an outreach event (proposed §6.31).
# Optional — outcomes populate as the recruiter learns them; a candidate
# with no outcome yet stays NULL (interpreted as "no_response" in UI).
CANDIDATE_OUTCOMES: dict[int, str] = {
    0: "no_response",
    1: "replied",
    2: "interview",
    3: "hired",
    4: "rejected",
}


# Reverse maps for label → int conversion at API boundary.
OUTREACH_CHANNELS_REVERSE = reverse(OUTREACH_CHANNELS)
OUTREACH_STATUSES_REVERSE = reverse(OUTREACH_STATUSES)
CANDIDATE_OUTCOMES_REVERSE = reverse(CANDIDATE_OUTCOMES)


__all__ = [
    "OUTREACH_CHANNELS",
    "OUTREACH_CHANNELS_REVERSE",
    "OUTREACH_STATUSES",
    "OUTREACH_STATUSES_REVERSE",
    "CANDIDATE_OUTCOMES",
    "CANDIDATE_OUTCOMES_REVERSE",
    "get_label",
    "get_value",
    "reverse",
]
