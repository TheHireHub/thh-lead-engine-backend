"""FastAPI routes for signups (Schema doc §7.12, §9.3-9.4 OTP via thh-backend)."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import require_admin, require_internal
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.campaigns.crud import CampaignEventCRUD
from services.candidate_outreach.auth import require_service_token
from services.common.envelope import ok
from services.companies.crud import CompanyCRUD
from services.companies.models import Company
from services.integrations import telegram, thh_backend
from services.landing_pages.crud import (
    LandingPageVariantCRUD,
    LandingPageVisitCRUD,
)
from services.prospect_company_jobs.crud import JobCRUD
from services.prospect_company_jobs.models import ProspectCompanyJob
from services.prospects.crud import ProspectCRUD
from services.prospects.dedupe import find_existing
from services.prospects.models import Prospect
from services.webhooks.crud import WebhookDeliveryCRUD

from .crud import SignupCRUD
from .models import Signup
from .enums import SIGNUP_REQUEST_TYPES, get_label
from .schemas import InboundLeadEvent, OtpVerifyPayload, SignupCreate, SignupOut

router = APIRouter(prefix="/api/signups", tags=["signups"])

# Constants for inbound-leads ingest (docs/INBOUND_LEADS.md §3).
_CHANNEL_HH_SIGNUP = 13           # §6.3 CHANNELS
_REQTYPE_HH_SIGNUP = 5            # §6.11 SIGNUP_REQUEST_TYPES
_WEBHOOK_PROVIDER_THH = 4         # §6.12 WEBHOOK_PROVIDERS
_STAGE_CURIOUS = 1                # §6.2 FUNNEL_STAGES
_COMPANY_SOURCE_SIGNUP = 2        # §6.4 COMPANY_SOURCES (2=signup)
# Event types that signal L3 (OTP verified / company onboarded).
_L3_EVENTS = {"otp_verified", "company_onboarded"}
# L4 events — user published a job. Bumps prospects.first_job_created_at +
# jobs_created_count via set_first_job_created. Only `job_published` fires
# now (draft + step events were removed per telegram-parity rule). The set
# stays a set so a future telegram-paired event can be added without
# rewriting the membership check.
_L4_EVENTS = {"job_published"}


def _extract_domain(url_or_domain: Optional[str]) -> Optional[str]:
    """Best-effort domain extraction.

    Accepts 'https://acme.com/about', 'acme.com', 'www.acme.com', 'user@acme.com'.
    Returns lowercased bare domain or None.
    """
    if not url_or_domain:
        return None
    raw = url_or_domain.strip().lower()
    if not raw:
        return None
    if "@" in raw and "://" not in raw:
        raw = raw.split("@", 1)[1]
    if "://" in raw:
        raw = raw.split("://", 1)[1]
    raw = raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if raw.startswith("www."):
        raw = raw[4:]
    return raw or None

# In-memory rate limiter for resend-otp.
# TODO: swap for redis-backed limiter in prod (gunicorn workers don't share dicts).
# Keyed by signup_id -> last send unix timestamp.
_RESEND_TS: dict[int, float] = {}
_RESEND_COOLDOWN_S = 60


def _serialize(s) -> dict:
    out = SignupOut.model_validate(s).model_dump()
    out["request_type_label"] = get_label(SIGNUP_REQUEST_TYPES, s.request_type)
    return out


@router.get("")
async def list_signups(
    request_type: Optional[int] = None,
    otp_verified: Optional[bool] = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    rows = await SignupCRUD.list_filtered(
        db,
        request_type=request_type,
        otp_verified=otp_verified,
        limit=limit,
        offset=offset,
    )
    return ok([_serialize(s) for s in rows])


@router.get("/{signup_id}")
async def get_signup_detail(
    signup_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_internal),
) -> dict:
    """Detail view used by the FE drawer.

    Joins the signup -> prospect -> company chain so the FE renders a full
    lead picture in one fetch: contact info, milestone timestamps, company
    profile, and the original event payload (touch count, source slug,
    enrichment overflow). Returns 404 if the signup row is missing.
    """
    row = await SignupCRUD.get_by_id(db, signup_id)
    if row is None:
        raise HTTPException(status_code=404, detail="signup not found")

    prospect: Optional[Prospect] = None
    if row.prospect_id:
        prospect_result = await db.execute(
            select(Prospect).where(Prospect.id == row.prospect_id)
        )
        prospect = prospect_result.scalar_one_or_none()

    company: Optional[Company] = None
    if prospect and prospect.company_id:
        company_result = await db.execute(
            select(Company).where(Company.id == prospect.company_id)
        )
        company = company_result.scalar_one_or_none()

    signup_dict = _serialize(row)
    # Full event series for this lead — drawer Timeline shows every recorded
    # touch (partial_signup → OTP requested → verified → onboarded → published),
    # not just the latest. Cap at 200 — anything past that is noise.
    events_rows = await SignupCRUD.list_for_lead(
        db, prospect_id=row.prospect_id, email=row.email, limit=200
    )

    # Resolve the company for the "Linked Jobs" section. Primary: prospect's
    # own company_id. Fallback: lookup company by the lead's email domain so
    # leads whose `company_id` was never backfilled (e.g. partial_signup that
    # never reached company_onboarded, or a dropped L4 push) still see the
    # job that exists under their company. Without this fallback, Sales sees
    # a "Partial" lead with no hint that a job is already live for the same
    # company.
    target_company: Optional[Company] = company
    if target_company is None and row.email and "@" in row.email:
        candidate_domain = row.email.split("@", 1)[1].strip().lower()
        if candidate_domain:
            target_company = await CompanyCRUD.get_by_domain(db, candidate_domain)

    jobs_payload: list[dict] = []
    if target_company is not None:
        jobs_rows = await JobCRUD.list_for_company(db, target_company.id)
        for j in jobs_rows:
            jobs_payload.append({
                "id": j.id,
                "title": j.title,
                "status": j.status,
                "paid_status": j.paid_status,
                "source": j.source,
                "posted_at": j.posted_at.isoformat() if j.posted_at else None,
                "opened_at": j.opened_at.isoformat() if j.opened_at else None,
                "total_applicants": j.total_applicants,
                "expectation_target": j.expectation_target,
                "company_id": j.company_id,
            })

    detail = {
        "signup": signup_dict,
        "events": [_serialize(e) for e in events_rows],
        "jobs": jobs_payload,
        "prospect": None,
        "company": None,
    }
    if prospect:
        detail["prospect"] = {
            "id": prospect.id,
            "first_name": prospect.first_name,
            "last_name": prospect.last_name,
            "email": prospect.email,
            "phone": prospect.phone,
            "linkedin_url": prospect.linkedin_url,
            "stage": prospect.stage,
            "source_channel": prospect.source_channel,
            "thh_user_id": prospect.thh_user_id,
            "company_id": prospect.company_id,
            "registered_at": prospect.registered_at.isoformat() if prospect.registered_at else None,
            "first_job_created_at": prospect.first_job_created_at.isoformat() if prospect.first_job_created_at else None,
            "jobs_created_count": prospect.jobs_created_count,
            "demo_booked_at": prospect.demo_booked_at.isoformat() if prospect.demo_booked_at else None,
            "first_applicant_received_at": prospect.first_applicant_received_at.isoformat() if prospect.first_applicant_received_at else None,
            "applicants_received_count": prospect.applicants_received_count,
            "created_at": prospect.created_at.isoformat() if prospect.created_at else None,
        }
    if company:
        detail["company"] = {
            "id": company.id,
            "name": company.name,
            "domain": company.domain,
            "linkedin_url": company.linkedin_url,
            "industry": company.industry,
            "size": company.size,
            "revenue_range": company.revenue_range,
            "funding_stage": company.funding_stage,
            "source": company.source,
            "enriched_at": company.enriched_at.isoformat() if company.enriched_at else None,
        }
    return ok(detail)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_signup(payload: SignupCreate, db: AsyncSession = Depends(get_db)) -> dict:
    """
    Public endpoint. Called when a prospect submits the landing page form.

    Side effects:
    1. If visitor_id is provided, attach landing_page_id from the most recent
       visit (denormalised onto the signup for analytics).
    2. Insert signups row with otp_verified_at=NULL.
    3. Call thh-backend POST /api/auth/login-otp/send (md §9.3).
    4. Audit row.

    NOTE: campaign_events.otp_sent (16) is deferred until otp-verify because
    campaign_events.prospect_id is NOT NULL and the prospect doesn't exist
    yet. Both events get written once the prospect is upserted.
    """
    signup_fields = payload.model_dump(exclude_none=True)

    if payload.visitor_id:
        visit = await LandingPageVisitCRUD.latest_for_visitor(db, payload.visitor_id)
        if visit:
            signup_fields.setdefault("landing_page_id", visit.landing_page_id)

    signup = await SignupCRUD.create(db, **signup_fields)

    # OTP send is best-effort — the signup row is already persisted, and the
    # admin signups list / resend-otp endpoint can recover from a missed
    # send. Treat THH backend being unreachable (network error, 4xx, 5xx) as
    # a soft failure: audit it and let the response succeed (BUG-022).
    # Without this guard, any THH downtime caused every public LP signup to
    # 500, even though the signup row itself was already created.
    otp_failed_reason: dict | None = None
    try:
        otp_resp = await thh_backend.send_otp(email=payload.email)
    except Exception as exc:  # noqa: BLE001 — wrap upstream failures
        otp_failed_reason = {"exception": type(exc).__name__, "detail": str(exc)[:255]}
        otp_resp = {"success": False}

    if not otp_resp.get("success"):
        await AuditLogCRUD.record(
            db,
            entity_type="signup",
            entity_id=signup.id,
            action="otp_send_failed",
            after_json=otp_failed_reason or {"reason": otp_resp},
        )
    else:
        _RESEND_TS[signup.id] = time.time()

    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="create",
        after_json={"email": signup.email, "visitor_id": signup.visitor_id},
    )
    return ok(_serialize(signup), message="signup recorded")


@router.post("/{signup_id}/resend-otp")
async def resend_otp(signup_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    """Rate-limited to 1 send per 60s per signup_id."""
    signup = await SignupCRUD.get_by_id(db, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="signup not found")
    if signup.otp_verified_at:
        raise HTTPException(status_code=409, detail="signup already verified")

    last = _RESEND_TS.get(signup_id, 0.0)
    elapsed = time.time() - last
    if elapsed < _RESEND_COOLDOWN_S:
        retry_after = int(_RESEND_COOLDOWN_S - elapsed)
        raise HTTPException(
            status_code=429,
            detail=f"please wait {retry_after}s before requesting another OTP",
            headers={"Retry-After": str(retry_after)},
        )

    otp_resp = await thh_backend.send_otp(email=signup.email)
    _RESEND_TS[signup_id] = time.time()
    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="otp_resend",
        after_json=otp_resp,
    )
    return ok({"sent": otp_resp.get("success", False)}, message="otp resent")


@router.post("/{signup_id}/otp-verify")
async def verify_otp(
    signup_id: int,
    payload: OtpVerifyPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Verify OTP and complete signup. Per md §9.4 side effects:

    - Mark signup.otp_verified_at = now.
    - Attribute signup to landing_page_variant (bump signup_count).
    - Upsert prospect via Arch-6 dedupe priority (linkedin > email > phone).
      If new, create with email + name + phone from the signup row.
    - Attach signup -> prospect, set prospects.registered_at (md §3 milestone).
    - Write campaign_events otp_sent (16) + otp_verified (17) — deferred from
      signup creation because campaign_events.prospect_id is NOT NULL.
    - Telegram alert + audit row.
    """
    signup = await SignupCRUD.get_by_id(db, signup_id)
    if not signup:
        raise HTTPException(status_code=404, detail="signup not found")
    if signup.otp_verified_at:
        return ok(_serialize(signup), message="already verified")

    verify_resp = await thh_backend.verify_otp(
        email=signup.email, otp_code=payload.otp_code
    )
    if not verify_resp.get("success"):
        await AuditLogCRUD.record(
            db,
            entity_type="signup",
            entity_id=signup.id,
            action="otp_verify_failed",
            after_json=verify_resp,
        )
        raise HTTPException(status_code=400, detail=verify_resp.get("reason", "otp invalid"))

    signup = await SignupCRUD.mark_otp_verified(db, signup)

    # Attribute to variant.
    if signup.visitor_id:
        visit = await LandingPageVisitCRUD.latest_for_visitor(db, signup.visitor_id)
        if visit and visit.landing_page_variant_id:
            variant = await LandingPageVariantCRUD.get_by_id(
                db, visit.landing_page_variant_id
            )
            if variant:
                await LandingPageVariantCRUD.bump_signup(db, variant)

    # md Arch-6 dedupe priority + §9.4 upsert.
    if not signup.prospect_id:
        prospect = await find_existing(
            db, email=signup.email, phone=signup.phone
        )
        if prospect is None:
            first_name, last_name = (None, None)
            if signup.name:
                parts = signup.name.strip().split(" ", 1)
                first_name = parts[0]
                last_name = parts[1] if len(parts) > 1 else None
            prospect = await ProspectCRUD.create(
                db,
                email=signup.email,
                phone=signup.phone,
                first_name=first_name,
                last_name=last_name,
            )
        await SignupCRUD.attach_prospect(db, signup, prospect.id)
        # md §3 — registered_at is the OTP-verified milestone.
        await ProspectCRUD.set_registered(db, prospect)

    # Write the deferred campaign_events (md §9.3 otp_sent=16, §9.4 otp_verified=17).
    if signup.prospect_id:
        for ev_type in (16, 17):
            await CampaignEventCRUD.record(
                db,
                prospect_id=signup.prospect_id,
                event_type=ev_type,
                payload_json={"signup_id": signup.id},
            )

    await telegram.send_alert(
        f"OTP verified: {signup.email} (signup #{signup.id})"
    )
    await AuditLogCRUD.record(
        db,
        entity_type="signup",
        entity_id=signup.id,
        action="otp_verified",
        after_json={"email": signup.email},
    )
    return ok(_serialize(signup), message="otp verified")


# ─── Inbound webhook (HH-BE → LEADS, X-Service-Token) ───────────────────
# docs/INBOUND_LEADS.md §5.1. One push per fire-point in HH-BE signup flow.
# Mirrors candidate_outreach.routes:ingest_outreach idempotency pattern.


@router.post("/inbound", status_code=status.HTTP_200_OK)
async def inbound_lead_event(
    payload: InboundLeadEvent,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(require_service_token),
) -> dict:
    """
    HH-BE pushes one lead event here. Idempotent on `dedup_key` via
    webhook_deliveries(provider=4, external_event_id=dedup_key).

    Behaviour by event_type:
      - partial_signup / enquiry_form / calendly_booked / otp_requested
        → upsert prospect (by email), record_touch on channel=13, insert
          signups row (otp_verified_at=NULL).
      - otp_verified / company_onboarded
        → same as above PLUS set_registered + set_thh_user_id, signups
          row gets otp_verified_at=NOW.
    """
    if not payload.email and not payload.thh_user_id:
        raise HTTPException(status_code=400, detail="email or thh_user_id required")

    # 1) Idempotency check via webhook_deliveries.
    wd_row, was_duplicate = await WebhookDeliveryCRUD.record(
        db,
        provider=_WEBHOOK_PROVIDER_THH,
        external_event_id=payload.dedup_key,
        payload_json=payload.model_dump(mode="json"),
    )
    if was_duplicate:
        return ok(
            {"created": False, "prospect_id": None, "signup_id": None, "dedup_key": payload.dedup_key},
            message="already_received",
        )

    try:
        # 2) Find or create prospect.
        # Priority: thh_user_id (verified-user truth) → email → phone (via find_existing).
        email = (payload.email or "").strip().lower() or None
        prospect: Prospect | None = None

        if payload.thh_user_id:
            result = await db.execute(
                select(Prospect).where(Prospect.thh_user_id == payload.thh_user_id)
            )
            prospect = result.scalar_one_or_none()

        if prospect is None and email:
            prospect = await find_existing(db, email=email, phone=payload.phone)

        if prospect is None and email:
            prospect = await ProspectCRUD.create(
                db,
                email=email,
                phone=payload.phone,
                first_name=payload.first_name,
                last_name=payload.last_name,
                source_channel=_CHANNEL_HH_SIGNUP,
                stage=_STAGE_CURIOUS,
            )
        elif prospect is not None:
            # Enrich blanks; never overwrite non-null fields.
            updates = {}
            if payload.first_name and not prospect.first_name:
                updates["first_name"] = payload.first_name
            if payload.last_name and not prospect.last_name:
                updates["last_name"] = payload.last_name
            if payload.phone and not prospect.phone:
                updates["phone"] = payload.phone
            if updates:
                prospect = await ProspectCRUD.update(db, prospect, **updates)

        if prospect is None:
            # Should not happen given the validation above, but guard.
            raise HTTPException(status_code=400, detail="cannot resolve prospect")

        # 3) Upsert + enrich the company row when L3 supplies enough to identify it.
        # Keyed by domain (extracted from company_website or signup email). The
        # `companies` table has a UNIQUE(domain) so re-pushes are idempotent. We
        # enrich blanks only — never overwrite the rightful owner's fields. The
        # prospect's company_id pointer is set if currently null.
        company_domain = _extract_domain(payload.company_website) or _extract_domain(email)
        if company_domain and (payload.company_name or payload.company_website):
            company, _ = await CompanyCRUD.get_or_create_by_domain(
                db,
                domain=company_domain,
                name=payload.company_name or company_domain,
                source=_COMPANY_SOURCE_SIGNUP,
                linkedin_url=payload.company_linkedin_url,
                industry=payload.company_industry,
                size=payload.company_size,
            )
            # Enrich blanks on subsequent pushes (e.g. L1 dropped a domain, L3
            # later supplies linkedin + industry).
            company_updates = {}
            if payload.company_name and not company.name:
                company_updates["name"] = payload.company_name
            if payload.company_linkedin_url and not company.linkedin_url:
                company_updates["linkedin_url"] = payload.company_linkedin_url
            if payload.company_industry and not company.industry:
                company_updates["industry"] = payload.company_industry
            if payload.company_size and not company.size:
                company_updates["size"] = payload.company_size
            if company_updates:
                company = await CompanyCRUD.update(db, company, **company_updates)
            if not prospect.company_id:
                prospect.company_id = company.id
                await db.commit()
                await db.refresh(prospect)

        # 4) Bump touch counters + prospect_channels junction.
        await ProspectCRUD.record_touch(db, prospect, channel=_CHANNEL_HH_SIGNUP)

        # 5) L3-specific milestones.
        is_l3 = payload.event_type in _L3_EVENTS
        if is_l3:
            await ProspectCRUD.set_registered(db, prospect)
            if payload.thh_user_id and not prospect.thh_user_id:
                await ProspectCRUD.set_thh_user_id(db, prospect, payload.thh_user_id)

        # 5b) L4 milestones — bump first_job_created_at + jobs_created_count.
        # The setter NULL-guards first_job_created_at (only sets first time),
        # and updates count to whatever HH-BE supplies in source_meta.jobs_total.
        is_l4 = payload.event_type in _L4_EVENTS
        if is_l4:
            _meta = payload.source_meta or {}
            _count = int(_meta.get("jobs_total") or 1)
            await ProspectCRUD.set_first_job_created(db, prospect, count=_count)
            # Backfill thh_user_id if the L4 fire arrives before any L3 (e.g. a
            # user who was created via google-signup with no separate OTP step).
            if payload.thh_user_id and not prospect.thh_user_id:
                await ProspectCRUD.set_thh_user_id(db, prospect, payload.thh_user_id)

        # 6) Append signups row (one per touch — full event fidelity).
        signup_fields = dict(
            prospect_id=prospect.id,
            # Use the real prospect email when the event itself didn't carry
            # one (typical for L4 job_step_advanced fires that arrive with
            # only thh_user_id). Falls back to a synthetic email only when
            # the prospect has no email either (anon calendly case).
            email=email or (prospect.email if prospect and prospect.email else f"unknown+{payload.dedup_key}@thh.internal"),
            name=" ".join(p for p in (payload.first_name, payload.last_name) if p) or None,
            company_name=payload.company_name,
            phone=payload.phone,
            request_type=_REQTYPE_HH_SIGNUP,
            payload_json={
                "event_type": payload.event_type,
                "slug": payload.slug,
                "thh_user_id": payload.thh_user_id,
                "thh_company_id": payload.thh_company_id,
                "signup_source": payload.signup_source,
                "source_meta": payload.source_meta,
                "touch": payload.touch,
                "anonymous": payload.anonymous,
                "event_occurred_at": payload.event_occurred_at.isoformat(),
                "company_website": payload.company_website,
                "company_linkedin_url": payload.company_linkedin_url,
                "company_industry": payload.company_industry,
                "company_size": payload.company_size,
                "company_founded_year": payload.company_founded_year,
            },
        )
        if is_l3:
            signup_fields["otp_verified_at"] = datetime.now(timezone.utc)
        signup = await SignupCRUD.create(db, **signup_fields)

        # 7) Audit + mark webhook processed.
        await AuditLogCRUD.record(
            db,
            entity_type="signup",
            entity_id=signup.id,
            action=f"inbound_{payload.event_type}",
            after_json={"email": email, "prospect_id": prospect.id, "dedup_key": payload.dedup_key},
        )
        await WebhookDeliveryCRUD.mark_processed(db, wd_row)

        return ok(
            {
                "created": True,
                "prospect_id": prospect.id,
                "signup_id": signup.id,
                "is_l3": is_l3,
                "dedup_key": payload.dedup_key,
            },
            message="ingested",
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        await WebhookDeliveryCRUD.mark_failed(db, wd_row, str(exc)[:1000])
        raise HTTPException(status_code=500, detail=f"ingest failed: {exc}")


@router.delete("/lead/{signup_id}")
async def delete_lead(
    signup_id: int,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(require_admin),
) -> dict:
    """Admin-only nuke for the entire lead grouping behind one signup row.

    Test data cleanup affordance — Sales asked for a one-click "remove this
    lead so it stops cluttering the list" button. Deletes every signup
    event that the /signups page would group under this row (same
    prospect_id, else same email when prospect_id is NULL), then
    soft-deletes the prospect if attached. No undo.
    """
    anchor = await SignupCRUD.get_by_id(db, signup_id)
    if anchor is None:
        raise HTTPException(status_code=404, detail="signup not found")

    # Resolve every signup row that belongs to this lead, matching the FE
    # grouping rule exactly.
    if anchor.prospect_id is not None:
        stmt = delete(Signup).where(Signup.prospect_id == anchor.prospect_id)
        bound = {"prospect_id": anchor.prospect_id}
    else:
        stmt = delete(Signup).where(
            Signup.email == anchor.email,
            Signup.prospect_id.is_(None),
        )
        bound = {"email": anchor.email}

    result = await db.execute(stmt)
    deleted_signups = int(result.rowcount or 0)

    deleted_prospect_id: int | None = None
    if anchor.prospect_id is not None:
        from services.prospects.models import Prospect
        p_result = await db.execute(
            select(Prospect).where(Prospect.id == anchor.prospect_id)
        )
        prospect = p_result.scalar_one_or_none()
        if prospect is not None and prospect.deleted_at is None:
            from services.prospects.crud import ProspectCRUD
            await ProspectCRUD.soft_delete(db, prospect)
            deleted_prospect_id = prospect.id

    await db.commit()

    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="signup",
        entity_id=signup_id,
        action="lead_delete",
        after_json={
            **bound,
            "deleted_signups": deleted_signups,
            "deleted_prospect_id": deleted_prospect_id,
        },
    )

    return ok(
        {
            "deleted_signups": deleted_signups,
            "deleted_prospect_id": deleted_prospect_id,
        },
        message="lead deleted",
    )
