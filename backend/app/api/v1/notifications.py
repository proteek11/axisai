"""
User Notifications API

GET    /api/v1/me/notifications           → list notifications (unread first)
PATCH  /api/v1/me/notifications/{id}/read → mark one as read
POST   /api/v1/me/notifications/read-all  → mark all as read
DELETE /api/v1/me/notifications/{id}      → dismiss notification

Internal helper: create_notification(user_id, title, body, link, notif_type, db)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from .auth import get_current_user

router = APIRouter(prefix="/me", tags=["Notifications"])
_bearer = HTTPBearer(auto_error=True)


# ── Schemas ────────────────────────────────────────────────────────────────────

class NotificationOut(BaseModel):
    id: str
    title: str
    body: Optional[str]
    link: Optional[str]
    notif_type: Optional[str]
    is_read: bool
    created_at: datetime


class NotificationsResponse(BaseModel):
    notifications: list[NotificationOut]
    unread_count: int


# ── Internal helper (called from other routers) ────────────────────────────────

async def create_notification(
    user_id: str,
    title: str,
    db: AsyncSession,
    body: Optional[str] = None,
    link: Optional[str] = None,
    notif_type: Optional[str] = None,
) -> str:
    """Create a notification for a user. Returns the new notification id."""
    notif_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.execute(
        text("""
            INSERT INTO user_notifications (id, user_id, title, body, link, notif_type, is_read, created_at)
            VALUES (:id, :uid, :title, :body, :link, :ntype, false, :now)
        """),
        {
            "id": notif_id, "uid": user_id, "title": title,
            "body": body, "link": link, "ntype": notif_type, "now": now,
        },
    )
    # Note: caller must commit
    return notif_id


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/notifications", response_model=NotificationsResponse)
async def list_notifications(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    result = await db.execute(
        text("""
            SELECT * FROM user_notifications
            WHERE user_id = :uid
            ORDER BY is_read ASC, created_at DESC
            LIMIT 50
        """),
        {"uid": str(user.id)},
    )
    rows = result.mappings().all()
    notifications = [NotificationOut(**dict(r)) for r in rows]
    unread = sum(1 for n in notifications if not n.is_read)
    return NotificationsResponse(notifications=notifications, unread_count=unread)


@router.patch("/notifications/{notif_id}/read", response_model=NotificationOut)
async def mark_read(
    notif_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    result = await db.execute(
        text("SELECT * FROM user_notifications WHERE id = :id AND user_id = :uid"),
        {"id": notif_id, "uid": str(user.id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(404, "Notification not found")
    await db.execute(
        text("UPDATE user_notifications SET is_read = true WHERE id = :id"),
        {"id": notif_id},
    )
    await db.commit()
    return NotificationOut(**{**dict(row), "is_read": True})


@router.post("/notifications/read-all")
async def mark_all_read(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    await db.execute(
        text("UPDATE user_notifications SET is_read = true WHERE user_id = :uid AND is_read = false"),
        {"uid": str(user.id)},
    )
    await db.commit()
    return {"ok": True}


@router.delete("/notifications/{notif_id}", status_code=204)
async def delete_notification(
    notif_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
):
    user = await get_current_user(credentials.credentials, db)
    result = await db.execute(
        text("DELETE FROM user_notifications WHERE id = :id AND user_id = :uid RETURNING id"),
        {"id": notif_id, "uid": str(user.id)},
    )
    if not result.rowcount:
        raise HTTPException(404, "Notification not found")
    await db.commit()
