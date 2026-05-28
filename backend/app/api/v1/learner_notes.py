"""
Learner Notes & Bookmarks API

Notes (L-05):
  GET    /api/v1/me/notes?content_item_id=X   → list notes for content item
  POST   /api/v1/me/notes                      → create note
  PUT    /api/v1/me/notes/{note_id}            → update note body
  DELETE /api/v1/me/notes/{note_id}            → delete note

Bookmarks (L-06):
  GET    /api/v1/me/bookmarks                  → list all bookmarks (optionally filter by content_item_id)
  POST   /api/v1/me/bookmarks                  → add bookmark
  DELETE /api/v1/me/bookmarks/{bookmark_id}    → remove bookmark
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/me", tags=["Learner Notes & Bookmarks"])
_bearer = HTTPBearer(auto_error=True)


# ── Schemas ────────────────────────────────────────────────────────────────────

class NoteCreate(BaseModel):
    content_item_id: Optional[str] = None
    space_id: Optional[str] = None
    body: str

class NoteUpdate(BaseModel):
    body: str

class NoteOut(BaseModel):
    id: str
    content_item_id: Optional[str]
    space_id: Optional[str]
    body: str
    created_at: datetime
    updated_at: datetime

class BookmarkCreate(BaseModel):
    content_item_id: Optional[str] = None
    space_id: Optional[str] = None
    output_type: Optional[str] = None
    label: Optional[str] = None

class BookmarkOut(BaseModel):
    id: str
    content_item_id: Optional[str]
    space_id: Optional[str]
    output_type: Optional[str]
    label: Optional[str]
    created_at: datetime


# ── Notes ──────────────────────────────────────────────────────────────────────

@router.get("/notes", response_model=list[NoteOut])
async def list_notes(
    content_item_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    conditions = "user_id = :uid"
    params: dict = {"uid": str(user.id)}
    if content_item_id:
        conditions += " AND content_item_id = :cid"
        params["cid"] = content_item_id
    if space_id:
        conditions += " AND space_id = :sid"
        params["sid"] = space_id
    result = await db.execute(
        text(f"SELECT * FROM learner_notes WHERE {conditions} ORDER BY created_at DESC"),
        params,
    )
    rows = result.mappings().all()
    return [NoteOut(**dict(r)) for r in rows]


@router.post("/notes", response_model=NoteOut, status_code=201)
async def create_note(
    body: NoteCreate,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    note_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            INSERT INTO learner_notes (id, user_id, content_item_id, space_id, body, created_at, updated_at)
            VALUES (:id, :uid, :cid, :sid, :body, :now, :now)
        """),
        {
            "id": note_id, "uid": str(user.id),
            "cid": body.content_item_id, "sid": body.space_id,
            "body": body.body, "now": now,
        },
    )
    await db.commit()
    return NoteOut(
        id=note_id,
        content_item_id=body.content_item_id,
        space_id=body.space_id,
        body=body.body,
        created_at=now, updated_at=now,
    )


@router.put("/notes/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    body: NoteUpdate,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    now = datetime.now(timezone.utc)
    result = await db.execute(
        text("SELECT * FROM learner_notes WHERE id = :id AND user_id = :uid"),
        {"id": note_id, "uid": str(user.id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Note not found")
    await db.execute(
        text("UPDATE learner_notes SET body = :body, updated_at = :now WHERE id = :id"),
        {"body": body.body, "now": now, "id": note_id},
    )
    await db.commit()
    return NoteOut(**{**dict(row), "body": body.body, "updated_at": now})


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(
    note_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    result = await db.execute(
        text("DELETE FROM learner_notes WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": note_id, "uid": str(user.id)},
    )
    if not result.rowcount:
        raise HTTPException(404, "Note not found")
    await db.commit()


# ── Bookmarks ──────────────────────────────────────────────────────────────────

@router.get("/bookmarks", response_model=list[BookmarkOut])
async def list_bookmarks(
    content_item_id: Optional[str] = Query(None),
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    conditions = "user_id = :uid"
    params: dict = {"uid": str(user.id)}
    if content_item_id:
        conditions += " AND content_item_id = :cid"
        params["cid"] = content_item_id
    result = await db.execute(
        text(f"SELECT * FROM learner_bookmarks WHERE {conditions} ORDER BY created_at DESC"),
        params,
    )
    rows = result.mappings().all()
    return [BookmarkOut(**dict(r)) for r in rows]


@router.post("/bookmarks", response_model=BookmarkOut, status_code=201)
async def create_bookmark(
    body: BookmarkCreate,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    bm_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            INSERT INTO learner_bookmarks (id, user_id, content_item_id, space_id, output_type, label, created_at)
            VALUES (:id, :uid, :cid, :sid, :otype, :label, :now)
        """),
        {
            "id": bm_id, "uid": str(user.id),
            "cid": body.content_item_id, "sid": body.space_id,
            "otype": body.output_type, "label": body.label, "now": now,
        },
    )
    await db.commit()
    return BookmarkOut(
        id=bm_id,
        content_item_id=body.content_item_id,
        space_id=body.space_id,
        output_type=body.output_type,
        label=body.label,
        created_at=now,
    )


@router.delete("/bookmarks/{bookmark_id}", status_code=204)
async def delete_bookmark(
    bookmark_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    result = await db.execute(
        text("DELETE FROM learner_bookmarks WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": bookmark_id, "uid": str(user.id)},
    )
    if not result.rowcount:
        raise HTTPException(404, "Bookmark not found")
    await db.commit()
