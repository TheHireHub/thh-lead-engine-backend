#!/usr/bin/env python3
"""
THH Lead Engine — fake data seeder.

Bootstraps a single admin user (direct DB, since the admin-create endpoint
itself needs an admin to call it), logs in via the public auth API, then
seeds companies, prospects, landing pages, visits, signups, campaigns,
jobs, candidates, call logs through the public/admin HTTP surface.

Useful for:
- Populating an empty DB so the frontend admin pages have something to show.
- Smoke-testing every DEV_B endpoint end-to-end (the script's HTTP traffic
  exercises the same routes the FE will hit).

Usage
-----
    # First run on an empty DB:
    python scripts/seed_fake_data.py

    # Custom api host / admin creds:
    python scripts/seed_fake_data.py \\
        --api-base http://127.0.0.1:5050 \\
        --admin-email seed@thehirehub.io \\
        --admin-password "ChangeMe123!"

    # Skip the admin bootstrap if one already exists:
    python scripts/seed_fake_data.py --no-bootstrap

The script is idempotent in spirit: re-running creates fresh entities each
time (no upsert), so volumes grow on each run. Use --reset to truncate
seed-owned tables first (CAUTION: destructive).

Reads MYSQL_* env (same as setup_database.py) for the bootstrap step only.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path when run from any cwd.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import requests
except ImportError:
    print("ERROR: `requests` is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None  # type: ignore


# ---------------------------------------------------------------------------
# Static seed pools — kept inline so the script has no extra runtime deps.
# ---------------------------------------------------------------------------
COMPANIES = [
    ("Razorpay", "razorpay.com", "Fintech", 1),
    ("Swiggy", "swiggy.com", "Foodtech", 1),
    ("Meesho", "meesho.com", "E-Commerce", 1),
    ("CoinDCX", "coindcx.com", "Crypto", 1),
    ("Zepto", "zepto.com", "Q-Commerce", 1),
    ("PhonePe", "phonepe.com", "Fintech", 1),
    ("CRED", "cred.club", "Fintech", 1),
    ("Cult.fit", "cult.fit", "HealthTech", 1),
    ("Postman", "postman.com", "DevTools", 1),
    ("Freshworks", "freshworks.com", "SaaS", 1),
]

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh",
    "Krishna", "Ishaan", "Rohan", "Kabir", "Aanya", "Ananya", "Diya",
    "Aadhya", "Kiara", "Saanvi", "Myra", "Sara", "Anika",
]
LAST_NAMES = [
    "Sharma", "Verma", "Iyer", "Patel", "Kapoor", "Khanna", "Mehta",
    "Reddy", "Nair", "Bose", "Joshi", "Pillai", "Chowdhury", "Rao",
]
TITLES = [
    "Engineering Manager", "Head of Talent", "VP Engineering", "Director of HR",
    "CTO", "Senior Recruiter", "Talent Acquisition Lead", "Founder",
    "Co-Founder", "People Ops Lead",
]
JOB_TITLES = [
    "Senior Backend Engineer", "Frontend Engineer", "Staff Platform Engineer",
    "Engineering Manager", "Data Scientist", "DevOps Engineer", "Mobile Engineer",
    "ML Engineer", "Site Reliability Engineer", "Product Designer",
]

# UTM source distribution we want — bucketed via backend's utm_mapping.py.
# seo bucket: organic, google, bing
# paid bucket: google_ads, facebook_ads, linkedin_ads
# outreach bucket: cold_email, linkedin_outreach
UTM_SOURCES = (
    ["organic"] * 25
    + ["google"] * 5
    + ["google_ads"] * 15
    + ["facebook_ads"] * 5
    + ["linkedin_ads"] * 5
    + ["cold_email"] * 30
    + ["linkedin_outreach"] * 15
)

FUNNEL_STAGES = {"cold": 0, "curious": 1, "converted": 2, "lost": 3, "unsubscribed": 4}
CHANNELS = {
    "cold_email": 0, "linkedin": 1, "paid": 2, "seo": 3, "geo": 4, "brand": 5,
    "remarketing": 6, "social": 7, "wom": 8, "apollo": 9, "warmly": 10,
    "direct": 11, "other": 12,
}
JOB_BOARDS = {
    "linkedin": 0, "naukri": 1, "indeed": 2, "glassdoor": 3, "monster": 4,
    "angellist": 5, "wellfound": 6, "careers_page": 7, "other": 8,
}
CALL_OUTCOMES = {
    "rnr": 0, "not_interested": 1, "call_back": 2, "follow_up": 3, "demo_scheduled": 4,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def info(msg: str) -> None:
    print(f"[seed] {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"[seed] WARN: {msg}", file=sys.stderr, flush=True)


def err(msg: str) -> None:
    print(f"[seed] ERROR: {msg}", file=sys.stderr, flush=True)


def jitter_dt(days_back_max: int = 30) -> datetime:
    """A datetime within the last `days_back_max` days, in UTC."""
    delta = timedelta(
        days=random.randint(0, days_back_max),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return datetime.now(timezone.utc) - delta


# ---------------------------------------------------------------------------
# Step 1 — bootstrap a single admin via direct DB (chicken-and-egg).
# ---------------------------------------------------------------------------
def bootstrap_admin(email: str, password: str, reset: bool) -> None:
    """
    If no admin user exists with the given email, insert one directly. Uses
    the backend's own jwt_utils.hash_password so the bcrypt format matches
    what /api/auth/login expects.
    """
    if load_dotenv:
        load_dotenv(BACKEND_DIR / ".env")

    try:
        import pymysql
        from services.admin_users.jwt_utils import hash_password
    except ImportError as e:
        err(f"bootstrap requires backend deps installed (pymysql, bcrypt): {e}")
        sys.exit(2)

    host = os.getenv("MYSQL_HOST", "localhost")
    port = int(os.getenv("MYSQL_PORT", "3306"))
    user = os.getenv("MYSQL_USER", "root")
    db_password = os.getenv("MYSQL_PASSWORD", "")
    db_name = os.getenv("MYSQL_DB", "thh_lead_engine")

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=db_password,
        database=db_name,
        charset="utf8mb4",
    )
    try:
        with conn.cursor() as cursor:
            if reset:
                # Truncate tables this seeder writes to (or that have FK back to them).
                # Order matters: leaf tables first.
                tables = [
                    "audit_log",
                    "campaign_events",
                    "campaign_prospects",
                    "campaigns",
                    "call_logs",
                    "prospect_company_job_history",
                    "prospect_company_job_candidates",
                    "prospect_company_job_boards",
                    "prospect_company_jobs",
                    "signups",
                    "landing_page_visits",
                    "landing_page_variants",
                    "landing_pages",
                    "prospect_channels",
                    "prospect_stage_history",
                    "prospects",
                    "companies",
                ]
                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                for t in tables:
                    cursor.execute(f"TRUNCATE TABLE `{t}`")
                cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                info(f"reset: truncated {len(tables)} tables")

            cursor.execute(
                "SELECT id FROM admin_users WHERE email=%s AND deleted_at IS NULL",
                (email,),
            )
            if cursor.fetchone():
                info(f"admin '{email}' already exists; skipping bootstrap")
                conn.commit()
                return

            cursor.execute(
                """
                INSERT INTO admin_users
                  (email, password_hash, first_name, last_name, role,
                   daily_call_target, avatar_color, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 0, 0, '#0EA5E9', NOW(), NOW())
                """,
                (email, hash_password(password), "Seed", "Admin"),
            )
        conn.commit()
        info(f"bootstrapped admin '{email}' (role=admin)")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Step 2 — API client (cookie session).
# ---------------------------------------------------------------------------
class Api:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.session = requests.Session()

    def login(self, email: str, password: str) -> dict[str, Any]:
        r = self.session.post(
            f"{self.base}/api/auth/login",
            json={"email": email, "password": password},
            timeout=10,
        )
        if r.status_code != 200:
            err(f"login failed: {r.status_code} {r.text[:200]}")
            r.raise_for_status()
        return r.json()["data"]["user"]

    def post(self, path: str, body: dict | None = None, expect: tuple[int, ...] = (200, 201)) -> Any:
        r = self.session.post(f"{self.base}{path}", json=body, timeout=10)
        if r.status_code not in expect:
            warn(f"POST {path} -> {r.status_code} {r.text[:200]}")
            return None
        return (r.json() or {}).get("data")

    def get(self, path: str, params: dict | None = None) -> Any:
        r = self.session.get(f"{self.base}{path}", params=params, timeout=10)
        if r.status_code != 200:
            warn(f"GET {path} -> {r.status_code} {r.text[:200]}")
            return None
        return (r.json() or {}).get("data")

    def patch(self, path: str, body: dict | None = None) -> Any:
        r = self.session.patch(f"{self.base}{path}", json=body, timeout=10)
        if r.status_code not in (200, 201):
            warn(f"PATCH {path} -> {r.status_code} {r.text[:200]}")
            return None
        return (r.json() or {}).get("data")


# ---------------------------------------------------------------------------
# Seeders — each returns the list of created entity dicts (for cross-refs).
# ---------------------------------------------------------------------------
def seed_companies(api: Api) -> list[dict]:
    out: list[dict] = []
    for name, domain, industry, source in COMPANIES:
        c = api.post(
            "/api/companies/",
            {"name": name, "domain": domain, "industry": industry, "source": source},
        )
        if c:
            out.append(c)
    info(f"companies: {len(out)} created")
    return out


def seed_prospects(api: Api, companies: list[dict], n: int = 80) -> list[dict]:
    """
    Create prospects via the API, then push a slice of them to non-cold
    stages via /api/prospects/{id}/stage. Schema doc §6.2: stage isn't
    accepted on create — it always starts at cold and is moved via the
    stage-change endpoint (which writes prospect_stage_history).
    """
    # Distribute target stage roughly: 50% cold, 30% curious, 12% converted, 5% lost, 3% unsub.
    stage_pool = (
        [FUNNEL_STAGES["cold"]] * 50
        + [FUNNEL_STAGES["curious"]] * 30
        + [FUNNEL_STAGES["converted"]] * 12
        + [FUNNEL_STAGES["lost"]] * 5
        + [FUNNEL_STAGES["unsubscribed"]] * 3
    )
    out: list[dict] = []
    targets: list[tuple[int, int]] = []  # (prospect_id, target_stage)

    for i in range(n):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        company = random.choice(companies) if companies else None
        domain = company["domain"] if company else "example.com"
        email = f"{first.lower()}.{last.lower()}{i}@{domain}"
        target_stage = random.choice(stage_pool)
        channel = random.choice(list(CHANNELS.values()))

        p = api.post(
            "/api/prospects/",
            {
                "email": email,
                "first_name": first,
                "last_name": last,
                "title": random.choice(TITLES),
                "phone": f"+91{random.randint(7000000000, 9999999999)}",
                "company_id": company["id"] if company else None,
                "source_channel": channel,
            },
        )
        if p:
            out.append(p)
            if target_stage != FUNNEL_STAGES["cold"]:
                targets.append((p["id"], target_stage))

    moved = 0
    for prospect_id, to_stage in targets:
        if api.post(
            f"/api/prospects/{prospect_id}/stage",
            {"to_stage": to_stage, "reason": "seed"},
        ):
            moved += 1
    info(f"prospects: {len(out)} created  ({moved} moved off cold)")
    return out


def seed_landing_pages(api: Api) -> list[dict]:
    pages: list[dict] = []
    for slug, template, hero in [
        ("phonepe-vikram", "classic", "Hi Vikram — let's hire faster."),
        ("razorpay-priya", "classic", "Priya, your next hire is one click away."),
        ("swiggy-arjun", "classic", "Arjun — built for hiring teams like yours."),
    ]:
        p = api.post(
            "/api/landing-pages/",
            {
                "slug": slug,
                "template_key": template,
                "default_content_json": {
                    "hero": hero,
                    "subtitle": "Verified candidates, on-demand.",
                },
            },
        )
        if not p:
            continue
        pages.append(p)
        # 2 variants per page (A/B).
        for variant_key, weight in [("hero_v1", 100), ("hero_v2", 100)]:
            api.post(
                "/api/landing-pages/variants",
                {
                    "landing_page_id": p["id"],
                    "variant_key": variant_key,
                    "content_json": {"hero": f"{hero} (variant {variant_key})"},
                    "weight": weight,
                    "status": 0,
                },
            )
    info(f"landing pages: {len(pages)} created (with 2 variants each)")
    return pages


def seed_visits(api: Api, pages: list[dict], n: int = 400) -> int:
    """Visit recording is public — no auth needed. Drop the cookie for these."""
    if not pages:
        return 0
    pub = requests.Session()
    base = api.base
    created = 0
    for _ in range(n):
        page = random.choice(pages)
        utm_source = random.choice(UTM_SOURCES)
        visitor_id = f"seed-{random.randint(1, 9999)}"
        body = {
            "landing_page_id": page["id"],
            "visitor_id": visitor_id,
            "utm_source": utm_source,
            "utm_medium": "seed",
            "utm_campaign": f"seed-{random.choice(['oct','nov','dec'])}",
        }
        try:
            r = pub.post(f"{base}/api/landing-pages/visits", json=body, timeout=10)
            if r.status_code in (200, 201):
                created += 1
        except requests.RequestException as e:
            warn(f"visit failed: {e}")
    info(f"landing visits: {created}/{n} recorded")
    return created


def seed_signups(api: Api, pages: list[dict], n: int = 25) -> int:
    """
    Public endpoint. NOTE: OTP send hits thh-backend; if it's not running
    the signup is still created (just without OTP). otp-verify will fail
    without a real OTP, so we leave them unverified — they still show up
    on the admin signups list.
    """
    pub = requests.Session()
    base = api.base
    created = 0
    for i in range(n):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}.signup{i}@example.com"
        body = {
            "email": email,
            "name": f"{first} {last}",
            "company_name": random.choice(COMPANIES)[0],
            "phone": f"+91{random.randint(7000000000, 9999999999)}",
            "request_type": random.randint(0, 4),
            "visitor_id": f"seed-signup-{i}",
            "landing_page_id": random.choice(pages)["id"] if pages else None,
        }
        try:
            r = pub.post(f"{base}/api/signups/", json=body, timeout=10)
            if r.status_code in (200, 201):
                created += 1
        except requests.RequestException as e:
            warn(f"signup failed: {e}")
    info(f"signups: {created}/{n} created (otp left unverified)")
    return created


def seed_campaigns(api: Api, prospects: list[dict]) -> list[dict]:
    if not prospects:
        return []
    campaigns: list[dict] = []
    for name in ["Oct-Cold-Outbound", "Linkedin-Warmup", "Q4-Reactivation"]:
        c = api.post(
            "/api/campaigns/",
            {
                "name": name,
                "channel": random.choice([0, 1, 2]),  # cold_email | linkedin | paid
                "status": 1,  # active
            },
        )
        if not c:
            continue
        campaigns.append(c)
        # Add a slice of prospects to each.
        slice_ids = [p["id"] for p in random.sample(prospects, k=min(20, len(prospects)))]
        api.post(
            f"/api/campaigns/{c['id']}/prospects",
            {"prospect_ids": slice_ids},
        )
        # Record a few events per prospect. Note: events are POSTed to
        # /api/campaigns/events (not nested under /campaigns/{id}/events),
        # with campaign_id in the body (Schema doc §7.8).
        for pid in slice_ids:
            for ev_type in random.sample([0, 1, 2, 3, 5], k=random.randint(1, 3)):
                api.post(
                    "/api/campaigns/events",
                    {
                        "campaign_id": c["id"],
                        "prospect_id": pid,
                        "event_type": ev_type,
                    },
                )
    info(f"campaigns: {len(campaigns)} created")
    return campaigns


def seed_jobs(api: Api, companies: list[dict]) -> list[dict]:
    if not companies:
        return []
    jobs: list[dict] = []
    for company in companies:
        for _ in range(random.randint(1, 3)):
            j = api.post(
                "/api/prospect-company-jobs/",
                {
                    "company_id": company["id"],
                    "title": random.choice(JOB_TITLES),
                    "department": random.choice(["Engineering", "Product", "Design"]),
                    "seniority": random.randint(2, 6),
                    "location": random.choice(["Bengaluru", "Remote", "Mumbai", "Hyderabad"]),
                    "employment_type": 1,
                    "open_count": random.randint(1, 4),
                    "paid_status": random.choice([0, 1, 2]),
                    "confidentiality": random.choice([0, 0, 0, 1]),  # mostly active
                    "no_linkedin_post": random.choice([0, 0, 0, 1]),
                    "source": random.choice([0, 2, 3, 4]),
                },
            )
            if not j:
                continue
            jobs.append(j)

            # ~50% of jobs are distributed (posted to boards).
            if random.random() < 0.5:
                board_picks = random.sample(list(JOB_BOARDS.values()), k=random.randint(1, 3))
                api.post(
                    f"/api/prospect-company-jobs/{j['id']}/distribute",
                    {
                        "boards": board_picks,
                        "expectation_target": random.randint(20, 80),
                        "days_threshold": random.choice([7, 14, 21]),
                    },
                )
                # Mark some boards posted.
                boards = api.get(f"/api/prospect-company-jobs/{j['id']}/boards") or []
                for b in boards:
                    if random.random() < 0.7:
                        api.post(
                            f"/api/prospect-company-jobs/boards/{b['id']}/mark-posted",
                            {"external_url": f"https://example.com/job/{j['id']}"},
                        )
                # Some jobs get applicants recorded.
                if random.random() < 0.6:
                    for board_id in board_picks[:2]:
                        api.post(
                            f"/api/prospect-company-jobs/{j['id']}/applicants",
                            {"board": board_id, "applicant_count": random.randint(5, 60)},
                        )
    info(f"jobs: {len(jobs)} created")
    return jobs


def seed_candidates(api: Api, jobs: list[dict]) -> int:
    created = 0
    for j in jobs:
        for _ in range(random.randint(0, 4)):
            c = api.post(
                "/api/prospect-company-jobs/candidates",
                {
                    "prospect_company_job_id": j["id"],
                    "candidate_name": f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}",
                    "candidate_title": random.choice(TITLES),
                    "match_score": round(random.uniform(0.55, 0.98), 2),
                    "match_method": random.choice([0, 1, 2]),
                },
            )
            if c:
                created += 1
                # Some get a status update.
                if random.random() < 0.4:
                    api.patch(
                        f"/api/prospect-company-jobs/candidates/{c['id']}/status",
                        {"status": random.choice([1, 2, 3])},
                    )
    info(f"candidates: {created} created")
    return created


def seed_call_logs(api: Api, prospects: list[dict], n: int = 60) -> int:
    if not prospects:
        return 0
    created = 0
    for _ in range(n):
        prospect = random.choice(prospects)
        outcome = random.choices(
            list(CALL_OUTCOMES.values()),
            weights=[40, 15, 20, 15, 10],
            k=1,
        )[0]
        body: dict[str, Any] = {
            "prospect_id": prospect["id"],
            "outcome": outcome,
            "notes": random.choice(["", "Left voicemail", "Quick chat", "Asked to call back"]),
        }
        if outcome == CALL_OUTCOMES["call_back"]:
            future = datetime.now(timezone.utc) + timedelta(days=random.randint(1, 7))
            body["callback_at"] = future.isoformat()
        if api.post("/api/call-logs/", body):
            created += 1
    info(f"call logs: {created}/{n} recorded")
    return created


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", default="http://127.0.0.1:5050")
    parser.add_argument("--admin-email", default="seed@thehirehub.io")
    parser.add_argument("--admin-password", default="ChangeMe123!")
    parser.add_argument(
        "--no-bootstrap",
        action="store_true",
        help="skip the direct-DB admin insert (an admin must already exist)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="DESTRUCTIVE: truncate seed-owned tables before seeding",
    )
    parser.add_argument(
        "--prospects", type=int, default=80, help="number of prospects to create"
    )
    parser.add_argument(
        "--visits", type=int, default=400, help="number of landing visits to record"
    )
    parser.add_argument(
        "--signups", type=int, default=25, help="number of signups to create"
    )
    parser.add_argument(
        "--call-logs", type=int, default=60, help="number of call logs to record"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="random seed for reproducibility"
    )
    args = parser.parse_args()

    random.seed(args.seed)
    info(f"target: {args.api_base}  (random seed: {args.seed})")
    started = time.monotonic()

    if not args.no_bootstrap:
        bootstrap_admin(args.admin_email, args.admin_password, reset=args.reset)
    elif args.reset:
        warn("--reset ignored because --no-bootstrap was set (reset path uses DB directly)")

    api = Api(args.api_base)
    try:
        user = api.login(args.admin_email, args.admin_password)
    except Exception as e:
        err(f"could not log in as {args.admin_email}: {e}")
        return 2
    info(f"logged in as {user['email']} (role_label={user.get('role_label')})")

    companies = seed_companies(api)
    prospects = seed_prospects(api, companies, n=args.prospects)
    pages = seed_landing_pages(api)
    seed_visits(api, pages, n=args.visits)
    seed_signups(api, pages, n=args.signups)
    seed_campaigns(api, prospects)
    jobs = seed_jobs(api, companies)
    seed_candidates(api, jobs)
    seed_call_logs(api, prospects, n=args.call_logs)

    elapsed = time.monotonic() - started
    info(f"done in {elapsed:.1f}s")
    info("hint: log in to the FE with the admin creds you just bootstrapped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
