"""
AWS SES email sender — slim port from thh-backend services/email/crud.py.

Single responsibility: deliver an HTML email (optionally with attachments)
via Amazon SES, using a shared boto3 client + env-configured From address.
No template DB, no Jinja rendering, no application logic — callers supply
the final rendered `subject` + `html_body` and we hand it to SES.

Why ported and not pip-install: HH-BE owns the SES sender + the
verified-identities config in their AWS account; reusing the EXACT same
shape means the LEADS-BE inherits identical send semantics (Source line,
Charset, multipart MIME for attachments) so SPF/DKIM still passes and
ops can debug both backends with one mental model.

Env vars (all already set in stage + prod Coolify per the deploy doc):

    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    AWS_REGION        (default ap-south-1)
    FROM_EMAIL        (default info@thehirehub.ai)
    FROM_NAME         (default AIRA)

Usage:

    from services.integrations.ses_email import ses_email

    ses_email.send(
        to="customer@example.com",
        subject="Welcome to the Hire Hub",
        html_body="<p>Hi there!</p>",
    )

    # Fire-and-forget (returns immediately, sends on a daemon thread):
    ses_email.send_async(
        to="customer@example.com",
        subject="Async greeting",
        html_body="<p>...</p>",
    )

Both `send` and `send_async` swallow failures internally — they log and
return False rather than raising — so callers never need a try/except
guard around them. This matches the HH-BE behaviour: an email outage
should never break the calling business flow.
"""

from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SesEmailClient:
    """Singleton-style SES sender. Lazy-imports boto3 so the rest of the
    app keeps booting even if boto3 isn't installed in a dev environment
    that doesn't need it."""

    def __init__(self) -> None:
        self._client = None  # lazy
        self._init_lock = threading.Lock()
        self.from_email = os.getenv("FROM_EMAIL", "info@thehirehub.ai")
        self.from_name = os.getenv("FROM_NAME", "AIRA")
        self.region = os.getenv("AWS_REGION", "ap-south-1")
        # No bounded thread-pool here — boto3 calls are short and rare.
        # If volume grows we'll swap for ARQ or an explicit pool.

    def _ensure_client(self) -> Optional[Any]:
        if self._client is not None:
            return self._client
        with self._init_lock:
            if self._client is not None:
                return self._client
            try:
                import boto3  # noqa: WPS433 — runtime import is intentional
            except ImportError:
                logger.error(
                    "[ses_email] boto3 not installed — email sends will be skipped. "
                    "Add boto3 to requirements.txt."
                )
                return None
            access = os.getenv("AWS_ACCESS_KEY_ID")
            secret = os.getenv("AWS_SECRET_ACCESS_KEY")
            if not access or not secret:
                logger.error(
                    "[ses_email] AWS credentials missing (AWS_ACCESS_KEY_ID / "
                    "AWS_SECRET_ACCESS_KEY) — sends will be skipped."
                )
                return None
            self._client = boto3.client(
                "ses",
                aws_access_key_id=access,
                aws_secret_access_key=secret,
                region_name=self.region,
            )
        return self._client

    def send(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        attachments: Optional[list[dict]] = None,
    ) -> bool:
        """Synchronous send. Returns True on success, False on any failure.

        `attachments` (optional) is a list of dicts each with keys:
            - filename: str
            - content:  str  (base64-encoded bytes)
        """
        client = self._ensure_client()
        if client is None:
            return False
        try:
            source = f"{self.from_name} <{self.from_email}>"
            if attachments:
                message = self._build_multipart(subject, html_body, attachments)
            else:
                message = {
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"}},
                }
            response = client.send_email(
                Source=source,
                Destination={"ToAddresses": [to]},
                Message=message,
            )
            msg_id = response.get("MessageId")
            if msg_id:
                logger.info("[ses_email] sent to=%s message_id=%s", to, msg_id)
                return True
            logger.error("[ses_email] no MessageId in response for to=%s", to)
            return False
        except Exception:
            logger.exception("[ses_email] send failed for to=%s", to)
            return False

    def send_async(
        self,
        *,
        to: str,
        subject: str,
        html_body: str,
        attachments: Optional[list[dict]] = None,
    ) -> None:
        """Fire-and-forget. Spawns a daemon thread that calls `send()`.
        Never raises — caller's request returns immediately."""
        try:
            t = threading.Thread(
                target=self.send,
                kwargs={
                    "to": to,
                    "subject": subject,
                    "html_body": html_body,
                    "attachments": attachments,
                },
                name="ses-email-send",
                daemon=True,
            )
            t.start()
        except Exception:
            logger.exception("[ses_email] failed to spawn async send thread")

    def _build_multipart(
        self, subject: str, html_body: str, attachments: list[dict]
    ) -> dict:
        """Build a SES Raw message envelope with attachments. Mirrors the
        HH-BE shape so DKIM signing on the receiving side stays identical."""
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        from email.mime.base import MIMEBase
        from email import encoders

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg.attach(MIMEText(html_body, "html"))
        for att in attachments:
            try:
                payload = base64.b64decode(att["content"])
                part = MIMEBase("application", "octet-stream")
                part.set_payload(payload)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename= {att["filename"]}',
                )
                msg.attach(part)
            except Exception:
                logger.exception(
                    "[ses_email] failed to attach %s — skipping that attachment",
                    att.get("filename", "<unknown>"),
                )
        return {"Raw": {"Data": msg.as_string()}}


# Module-level singleton. Import this from anywhere:
#   from services.integrations.ses_email import ses_email
ses_email = SesEmailClient()
