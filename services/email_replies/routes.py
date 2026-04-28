"""FastAPI routes for email_replies."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import EmailReplyCRUD
from .enums import REPLY_CLASSIFICATIONS, get_label
from .schemas import EmailReplyCreate, EmailReplyOut

router = APIRouter(prefix="/api/email-replies", tags=["email_replies"])


def _serialize(r) -> dict:
    out = EmailReplyOut.model_validate(r).model_dump()
    out["classification_label"] = get_label(REPLY_CLASSIFICATIONS, r.classification)
    return out


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await EmailReplyCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(r) for r in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def record_reply(payload: EmailReplyCreate, db: AsyncSession = Depends(get_db)) -> dict:
    reply = await EmailReplyCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(_serialize(reply), message="reply recorded")
