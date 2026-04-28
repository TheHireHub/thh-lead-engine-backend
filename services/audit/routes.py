"""FastAPI routes for audit_log (read-only viewer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import AuditLogCRUD
from .schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("/by-entity/{entity_type}/{entity_id}")
async def for_entity(
    entity_type: str, entity_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)
) -> dict:
    rows = await AuditLogCRUD.list_for_entity(db, entity_type, entity_id, limit=limit)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])


@router.get("/by-actor/{actor_user_id}")
async def for_actor(actor_user_id: int, limit: int = 100, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await AuditLogCRUD.list_for_actor(db, actor_user_id, limit=limit)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])
