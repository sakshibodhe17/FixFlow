"""In-app notifications for the signed-in user."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Notification, User
from ..security import get_current_user

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("")
def list_notifications(unread_only: bool = False, limit: int = 30, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    stmt = select(Notification).where(Notification.user_id == user.user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = db.scalars(stmt.order_by(Notification.created_at.desc()).limit(min(limit, 200)))
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.user_id, Notification.is_read.is_(False)))
    return {"unread": unread, "items": [
        {"notification_id": n.notification_id, "title": n.title, "message": n.message, "link": n.link,
         "is_read": n.is_read, "created_at": n.created_at} for n in rows]}


@router.post("/{notification_id}/read", status_code=204)
def mark_read(notification_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.notification_id == notification_id,
                                          Notification.user_id == user.user_id).values(is_read=True))
    db.commit()


@router.post("/read-all", status_code=204)
def mark_all_read(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.execute(update(Notification).where(Notification.user_id == user.user_id).values(is_read=True))
    db.commit()
