"""Administrator: manage user accounts and roles."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Technician, User
from ..schemas import PasswordReset, UserCreate, UserUpdate
from ..security import ADMIN, hash_password, require_roles
from ..services.audit import log_action
from ..services.serializers import user_out

router = APIRouter(prefix="/api/users", tags=["Users (Admin)"])
admin_only = require_roles(ADMIN)


def _ensure_technician_row(db: Session, user: User) -> None:
    if user.role == "Technician" and user.technician is None:
        db.add(Technician(user_id=user.user_id))
    elif user.role != "Technician" and user.technician is not None:
        user.technician.is_available = False  # keep the row for history; take them off the roster


@router.get("")
def list_users(role: str | None = None, q: str | None = None, db: Session = Depends(get_db), _=Depends(admin_only)):
    stmt = select(User).options(selectinload(User.technician)).order_by(User.created_at.desc())
    if role:
        stmt = stmt.where(User.role == role)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(User.full_name).like(like), func.lower(User.email).like(like)))
    return [user_out(u) for u in db.scalars(stmt)]


@router.post("", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")
    user = User(full_name=body.full_name.strip(), email=email, phone=body.phone,
                password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.flush()
    _ensure_technician_row(db, user)
    log_action(db, admin.user_id, "user.created", "user", user.user_id, {"role": body.role})
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.put("/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.user_id == admin.user_id and (body.role not in (None, ADMIN) or body.is_active is False):
        raise HTTPException(400, "You can't remove your own admin access.")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(user, k, v)
    db.flush()
    db.refresh(user)
    _ensure_technician_row(db, user)
    log_action(db, admin.user_id, "user.updated", "user", user.user_id, changes)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.post("/{user_id}/reset-password", status_code=204)
def reset_password(user_id: int, body: PasswordReset, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.password_hash = hash_password(body.new_password)
    log_action(db, admin.user_id, "user.password_reset", "user", user.user_id)
    db.commit()


@router.delete("/{user_id}", status_code=204)
def deactivate_user(user_id: int, db: Session = Depends(get_db), admin: User = Depends(admin_only)):
    """Soft delete: accounts are deactivated so their request history stays intact."""
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    if user.user_id == admin.user_id:
        raise HTTPException(400, "You can't deactivate your own account.")
    user.is_active = False
    if user.technician:
        user.technician.is_available = False
    log_action(db, admin.user_id, "user.deactivated", "user", user.user_id)
    db.commit()
