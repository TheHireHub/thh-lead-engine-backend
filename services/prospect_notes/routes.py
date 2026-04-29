"""FastAPI routes for prospect_notes (Schema doc §7.15, §6.10)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.admin_users.deps import current_user, require_role
from services.admin_users.models import AdminUser
from services.audit.crud import AuditLogCRUD
from services.common.envelope import ok

from .crud import ProspectNoteCRUD
from .enums import NOTE_STATUSES, get_label
from .schemas import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/api/prospect-notes", tags=["prospect_notes"])


def _serialize(n) -> dict:
    out = NoteOut.model_validate(n).model_dump(mode="json")
    out["status_label"] = get_label(NOTE_STATUSES, n.status)
    return out


@router.get("/")
async def list_notes(
    prospect_id: int | None = None,
    status: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    rows = await ProspectNoteCRUD.list_recent(
        db, prospect_id=prospect_id, status=status, limit=limit, offset=offset
    )
    return ok([_serialize(n) for n in rows])


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(
    prospect_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(current_user),
) -> dict:
    rows = await ProspectNoteCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(n) for n in rows])


@router.get("/tasks/open")
async def list_my_open_tasks(
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> dict:
    """Open tasks assigned to the calling user."""
    rows = await ProspectNoteCRUD.list_open_tasks_for_user(db, user.id)
    return ok([_serialize(n) for n in rows])


@router.get("/tasks/open/{user_id}")
async def list_open_tasks_for(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(require_role(0)),
) -> dict:
    """Admin-only — open tasks assigned to any user."""
    rows = await ProspectNoteCRUD.list_open_tasks_for_user(db, user_id)
    return ok([_serialize(n) for n in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> dict:
    note = await ProspectNoteCRUD.create(
        db, **payload.model_dump(exclude_none=True), created_by_user_id=user.id
    )
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_note",
        entity_id=note.id,
        action="create",
        after_json={"prospect_id": note.prospect_id, "status": note.status},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(note), message="note created")


@router.patch("/{note_id}")
async def update_note(
    note_id: int,
    payload: NoteUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> dict:
    note = await ProspectNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    before = {"status": note.status, "assigned_to_user_id": note.assigned_to_user_id}
    note = await ProspectNoteCRUD.update(db, note, **payload.model_dump(exclude_unset=True))
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_note",
        entity_id=note.id,
        action="update",
        before_json=before,
        after_json={"status": note.status, "assigned_to_user_id": note.assigned_to_user_id},
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(note), message="note updated")


@router.post("/{note_id}/complete")
async def complete_task(
    note_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> dict:
    """Flip status 1 (task_open) -> 2 (task_done). No-op if already done."""
    note = await ProspectNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    note = await ProspectNoteCRUD.complete_task(db, note)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_note",
        entity_id=note.id,
        action="complete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(_serialize(note), message="task completed")


@router.delete("/{note_id}")
async def delete_note(
    note_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: AdminUser = Depends(current_user),
) -> dict:
    note = await ProspectNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="note not found")
    await ProspectNoteCRUD.soft_delete(db, note)
    await AuditLogCRUD.record(
        db,
        actor_user_id=user.id,
        entity_type="prospect_note",
        entity_id=note.id,
        action="delete",
        ip_address=request.client.host if request.client else None,
    )
    return ok(message="note deleted")
