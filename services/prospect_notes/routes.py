"""FastAPI routes for prospect_notes (notes + tasks)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database_connection.connection import get_db
from services.common.envelope import ok

from .crud import ProspectNoteCRUD
from .enums import NOTE_STATUSES, get_label
from .schemas import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/api/prospect-notes", tags=["prospect_notes"])


def _serialize(n) -> dict:
    out = NoteOut.model_validate(n).model_dump()
    out["status_label"] = get_label(NOTE_STATUSES, n.status)
    return out


@router.get("/by-prospect/{prospect_id}")
async def list_for_prospect(prospect_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await ProspectNoteCRUD.list_for_prospect(db, prospect_id)
    return ok([_serialize(n) for n in rows])


@router.get("/tasks/open/{user_id}")
async def list_open_tasks(user_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    rows = await ProspectNoteCRUD.list_open_tasks_for_user(db, user_id)
    return ok([_serialize(n) for n in rows])


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreate, created_by_user_id: int, db: AsyncSession = Depends(get_db)
) -> dict:
    # TODO: replace `created_by_user_id` query param with current-user dep once auth lands.
    note = await ProspectNoteCRUD.create(
        db, **payload.model_dump(), created_by_user_id=created_by_user_id
    )
    return ok(_serialize(note), message="note created")


@router.patch("/{note_id}")
async def update_note(note_id: int, payload: NoteUpdate, db: AsyncSession = Depends(get_db)) -> dict:
    note = await ProspectNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    note = await ProspectNoteCRUD.update(db, note, **payload.model_dump(exclude_unset=True))
    return ok(_serialize(note), message="note updated")


@router.delete("/{note_id}")
async def delete_note(note_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    note = await ProspectNoteCRUD.get_by_id(db, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="note not found")
    await ProspectNoteCRUD.soft_delete(db, note)
    return ok(message="note deleted")
