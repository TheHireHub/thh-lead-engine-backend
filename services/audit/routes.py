"""FastAPI routes for audit_log (read-only viewer)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import current_user
from services.admin_users.models import AdminUser
from services.common.envelope import ok

from .crud import AuditLogCRUD
from .schemas import AuditLogOut

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("/by-entity/{entity_type}/{entity_id}")
async def for_entity(
    entity_type: str,
    entity_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    rows = await AuditLogCRUD.list_for_entity(db, entity_type, entity_id, limit=limit)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])


@router.get("/by-actor/{actor_user_id}")
async def for_actor(
    actor_user_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    rows = await AuditLogCRUD.list_for_actor(db, actor_user_id, limit=limit)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])


@router.get("/by-action/{action}")
async def for_action(
    action: str,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    """Search by action string (e.g. auto_marked_not_interested, promote_to_thh, gdpr_erase)."""
    rows = await AuditLogCRUD.list_by_action(db, action, limit=limit, offset=offset)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])


@router.get("/recent")
async def recent(
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    """Last N audit events across all entities. Powers the future Audit Log admin page."""
    rows = await AuditLogCRUD.list_recent(db, limit=limit)
    return ok([AuditLogOut.model_validate(r).model_dump() for r in rows])
