"""
Telegram alert wrapper (Schema doc Arch-28).

Phase 2 STATUS: stub. Logs every alert; doesn't actually send.
Phase 9 (post-MVP) wires real Telegram bot calls.

Reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from env.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def send_alert(text: str, chat_id: str | None = None) -> bool:
    """
    Send a Telegram alert to the configured chat (or override).

    TODO Phase 9: replace stub with real httpx POST to
    https://api.telegram.org/bot<TOKEN>/sendMessage.
    Returns True on success, False on failure.
    """
    target = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")

    if not (target and token):
        logger.info("[STUB telegram] (no token/chat configured) %s", text)
        return False

    logger.info("[STUB telegram] -> %s :: %s", target, text)
    return True
