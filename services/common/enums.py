"""
Cross-service TINYINT enum mappings (Schema doc §6).

This is the single source of truth for every int -> label mapping the lead
engine writes to the database. Per Arch-29, we use TINYINT UNSIGNED columns
(NOT MySQL ENUM) and the application owns the labels.

Each service may re-export only the enums it owns. Adding a new value =
update this file + write code that handles it (no `ALTER TABLE`).
"""

from __future__ import annotations

# §6.1 Role
ADMIN_ROLES = {
    0: "admin",
    1: "growth",
    2: "bdr",
    3: "sales",
    4: "caller",
    5: "csm",
    6: "viewer",
}

# §6.2 Funnel stage (post 2026-04-28 restructure)
FUNNEL_STAGES = {
    0: "cold",
    1: "curious",
    2: "converted",
    3: "lost",
    4: "unsubscribed",
}

# §6.3 Channel
CHANNELS = {
    0: "cold_email",
    1: "linkedin",
    2: "paid",
    3: "seo",
    4: "geo",
    5: "brand",
    6: "remarketing",
    7: "social",
    8: "wom",
    9: "apollo",
    10: "warmly",
    11: "direct",
    12: "other",
}

# §6.4 Company source
COMPANY_SOURCES = {0: "apollo", 1: "manual", 2: "signup", 3: "inferred"}

# §6.5 Campaign status
CAMPAIGN_STATUSES = {
    0: "draft",
    1: "active",
    2: "paused",
    3: "completed",
    4: "archived",
}

# §6.6 Campaign-prospect status
CAMPAIGN_PROSPECT_STATUSES = {
    0: "queued",
    1: "sent",
    2: "skipped",
    3: "failed",
    4: "unsubscribed",
}

# §6.7 Campaign event type
CAMPAIGN_EVENT_TYPES = {
    0: "sent",
    1: "delivered",
    2: "opened",
    3: "clicked",
    4: "bounced",
    5: "replied_positive",
    6: "replied_negative",
    7: "unsubscribed",
    8: "demo_booked",
    9: "demo_attended",
    10: "demo_no_show",
    11: "meeting_scheduled",
    12: "landing_visit",
    13: "cr_sent",
    14: "linkedin_message_sent",
    15: "linkedin_reply_received",
    16: "otp_sent",
    17: "otp_verified",
}

# §6.8 Reply classification (binary per Prateek)
REPLY_CLASSIFICATIONS = {0: "positive", 1: "negative"}

# §6.9 Reply classified_by
REPLY_CLASSIFIED_BY = {0: "rule", 1: "llm", 2: "manual"}

# §6.10 Note status
NOTE_STATUSES = {0: "note", 1: "task_open", 2: "task_done"}

# §6.11 Signup request_type
SIGNUP_REQUEST_TYPES = {
    0: "demo",
    1: "audit",
    2: "signup",
    3: "report",
    4: "other",
}

# §6.12 Webhook provider
WEBHOOK_PROVIDERS = {0: "calendly", 1: "apollo", 2: "email_provider", 3: "other"}

# §6.13 Webhook status
WEBHOOK_STATUSES = {0: "received", 1: "processed", 2: "failed", 3: "duplicate"}

# §6.14 Merge match strategy
MERGE_MATCH_STRATEGIES = {
    0: "linkedin_exact",
    1: "email_exact",
    2: "phone_exact",
    3: "manual_review",
    4: "admin_override",
}

# §6.15 Merge review queue status
MERGE_REVIEW_STATUSES = {0: "pending", 1: "merged", 2: "rejected"}

# §6.16 Job seniority
JOB_SENIORITY = {
    0: "unknown",
    1: "intern",
    2: "junior",
    3: "mid",
    4: "senior",
    5: "lead",
    6: "principal",
    7: "exec",
}

# §6.17 Employment type
EMPLOYMENT_TYPES = {
    0: "unknown",
    1: "full_time",
    2: "part_time",
    3: "contract",
    4: "internship",
}

# §6.18 Job paid status
JOB_PAID_STATUSES = {0: "unknown", 1: "paid", 2: "non_paid"}

# §6.19 Job confidentiality
JOB_CONFIDENTIALITY = {0: "active", 1: "confidential"}

# §6.20 Job source
JOB_SOURCES = {
    0: "manual",
    1: "scraped",
    2: "apollo",
    3: "linkedin",
    4: "careers_page",
    5: "other",
}

# §6.21 Job status
JOB_STATUSES = {
    0: "open",
    1: "paused",
    2: "closed",
    3: "filled",
    4: "withdrawn",
}

# §6.22 Job-candidate match method
JOB_CANDIDATE_MATCH_METHODS = {0: "manual", 1: "auto", 2: "ai_matched"}

# §6.23 Job-candidate status
JOB_CANDIDATE_STATUSES = {
    0: "proposed",
    1: "presented",
    2: "accepted",
    3: "rejected",
    4: "withdrawn",
    5: "hired",
}

# §6.24 Landing page variant status
LANDING_VARIANT_STATUSES = {0: "active", 1: "paused", 2: "archived"}

# §6.25 Heat level
HEAT_LEVELS = {0: "cold", 1: "warm", 2: "hot"}

# §6.26 Call outcome
CALL_OUTCOMES = {
    0: "rnr",
    1: "not_interested",
    2: "call_back",
    3: "follow_up",
    4: "demo_scheduled",
    5: "demo_attended",
    6: "demo_no_show",
}

# §6.27 Job board
JOB_BOARDS = {
    0: "linkedin",
    1: "naukri",
    2: "indeed",
    3: "glassdoor",
    4: "monster",
    5: "angellist",
    6: "wellfound",
    7: "careers_page",
    8: "other",
}

# §6.28 Job board posting status
JOB_BOARD_POSTING_STATUSES = {0: "pending", 1: "posted", 2: "failed", 3: "removed"}


def reverse(mapping: dict[int, str]) -> dict[str, int]:
    """Build a label -> int reverse map for any of the above."""
    return {v: k for k, v in mapping.items()}


def get_label(mapping: dict[int, str], value: int | None, default: str = "unknown") -> str:
    """Lookup with safe default for unrecognised values."""
    if value is None:
        return default
    return mapping.get(value, default)


def get_value(mapping: dict[int, str], label: str | None) -> int | None:
    """Reverse lookup; returns None if label not found."""
    if label is None:
        return None
    for k, v in mapping.items():
        if v == label:
            return k
    return None
