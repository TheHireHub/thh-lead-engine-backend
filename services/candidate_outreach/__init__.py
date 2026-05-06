"""Candidate outreach activity ingest from thh-backend (THH → LEADS direction).

This is a NEW touch point not yet in SCHEMA.md (proposed §9.6 + Arch-45).
When a recruiter clicks "Initiate Outreach" on a candidate row in HH-FE,
HH-BE pushes one summary event here so CRM viewers can see which jobs at
which companies got candidate outreach, and admins can mutate status.

Not to be confused with `campaign_events` (§7.8) which logs outbound
sales-marketing activity LEADS itself runs against prospects. This table
records THH-product-side recruiter activity at our customers.
"""
