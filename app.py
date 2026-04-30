"""
THH Lead Engine — FastAPI application entrypoint.

Mirrors the role of thh-backend's `app.py`: single entrypoint that wires up
the framework, loads env, and registers every service's router.

Architecture rules (see CLAUDE.md):
- Routes (`services/<domain>/routes.py`) are the only HTTP entrypoints.
- CRUD (`services/<domain>/crud.py`) is the only layer that touches the DB.
- Services are DB-agnostic helpers for heavy work / external API wrappers.
- Workers (`workers/`) are ARQ tasks; same orchestration rights as routes.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)
for noisy in ("httpx", "httpcore", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development")).lower()
IS_PROD = APP_ENV == "production"


def _validate_env() -> None:
    """
    Fail fast in production if required secrets are unset or still hold
    obvious dev placeholders. Dev/test envs skip this and lean on defaults
    so local bootstrap stays painless.
    """
    if not IS_PROD:
        return

    required = [
        "JWT_SECRET_KEY",
        "VISITOR_IP_HASH_SECRET",
        "UNSUBSCRIBE_TOKEN_SECRET",
        "MYSQL_PASSWORD",
        "CORS_ALLOWED_ORIGINS",
        "SESSION_COOKIE_SECURE",
    ]
    bad: list[str] = []
    for key in required:
        val = (os.getenv(key) or "").strip()
        if not val or "change-me" in val.lower() or val.lower().startswith("dev-"):
            bad.append(key)
    if os.getenv("SESSION_COOKIE_SECURE", "False").lower() != "true":
        bad.append("SESSION_COOKIE_SECURE (must be True in production)")
    if bad:
        raise RuntimeError(
            "Production startup blocked. These env vars are unset or use "
            f"dev defaults: {', '.join(bad)}. See env.example for guidance."
        )


_validate_env()


# ---------------------------------------------------------------------------
# Service router imports
# ---------------------------------------------------------------------------
# Each service exposes a single `router` object from its routes.py.
from services.admin_users.routes import router as admin_users_router
from services.audit.routes import router as audit_router
from services.call_logs.routes import router as call_logs_router
from services.campaigns.routes import router as campaigns_router
from services.companies.routes import router as companies_router
from services.email_replies.routes import router as email_replies_router
from services.funnel_snapshots.routes import router as funnel_snapshots_router
from services.landing_pages.routes import router as landing_pages_router
from services.prospect_company_jobs.routes import router as prospect_jobs_router
from services.prospect_notes.routes import router as prospect_notes_router
from services.prospects.routes import router as prospects_router
from services.signups.routes import router as signups_router
from services.unsubscribes.routes import router as unsubscribes_router
from services.webhooks.routes import router as webhooks_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run on startup / shutdown — wire up Sentry, warm caches, etc."""
    sentry_dsn = os.getenv("SENTRY_DSN")
    if sentry_dsn:
        import sentry_sdk

        sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.1)
        logger.info("Sentry initialized")
    logger.info("THH Lead Engine starting up")
    yield
    logger.info("THH Lead Engine shutting down")


app = FastAPI(
    title="THH Lead Engine API",
    version="0.1.0",
    description="Outbound growth / prospect-conversion system for The HireHub.",
    lifespan=lifespan,
    # /docs, /redoc, /openapi.json are off in prod unless EXPOSE_DOCS=true.
    # Override locally with EXPOSE_DOCS=true in your .env if you need them.
    docs_url=None if IS_PROD and os.getenv("EXPOSE_DOCS", "false").lower() != "true" else "/docs",
    redoc_url=None if IS_PROD and os.getenv("EXPOSE_DOCS", "false").lower() != "true" else "/redoc",
    openapi_url=None if IS_PROD and os.getenv("EXPOSE_DOCS", "false").lower() != "true" else "/openapi.json",
    # No silent 307 between with/without trailing slash. Either the route
    # matches exactly (and returns 200) or it 404s — much easier to debug
    # than a redirect loop bouncing between Next.js and FastAPI (BUG-020).
    redirect_slashes=False,
)


# ---------------------------------------------------------------------------
# CORS — frontend lives on a separate Vercel custom domain (try-thehirehub.com)
# ---------------------------------------------------------------------------
allowed_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:3001",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
async def health() -> dict:
    return {"success": True, "message": "ok", "data": {"service": "thh-lead-engine"}}


# ---------------------------------------------------------------------------
# Standard error envelope
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Internal server error",
            "data": None,
            "error": None if IS_PROD else str(exc),
        },
    )


# ---------------------------------------------------------------------------
# Service routers
# ---------------------------------------------------------------------------
app.include_router(admin_users_router)
app.include_router(companies_router)
app.include_router(prospects_router)
app.include_router(campaigns_router)
app.include_router(landing_pages_router)
app.include_router(signups_router)
app.include_router(email_replies_router)
app.include_router(unsubscribes_router)
app.include_router(prospect_notes_router)
app.include_router(prospect_jobs_router)
app.include_router(call_logs_router)
app.include_router(funnel_snapshots_router)
app.include_router(audit_router)
app.include_router(webhooks_router)
