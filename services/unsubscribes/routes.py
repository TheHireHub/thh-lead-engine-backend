"""FastAPI routes for unsubscribes (CAN-SPAM / GDPR compliance, Arch-26)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import UnsubscribeCRUD
from .schemas import UnsubscribeCreate, UnsubscribeOut

router = APIRouter(prefix="/api/unsubscribes", tags=["unsubscribes"])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def unsubscribe(payload: UnsubscribeCreate, db: AsyncSession = Depends(get_db)) -> dict:
    if existing := await UnsubscribeCRUD.get_by_email(db, payload.email):
        return ok(UnsubscribeOut.model_validate(existing).model_dump(), message="already unsubscribed")
    row = await UnsubscribeCRUD.create(db, **payload.model_dump(exclude_none=True))
    return ok(UnsubscribeOut.model_validate(row).model_dump(), message="unsubscribed")


@router.get("/check/{email}")
async def check(email: str, db: AsyncSession = Depends(get_db)) -> dict:
    return ok({"unsubscribed": await UnsubscribeCRUD.is_unsubscribed(db, email)})
