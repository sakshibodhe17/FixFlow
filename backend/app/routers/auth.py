"""Authentication: register, login (JSON + OAuth2 form for Swagger), profile."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import LoginIn, PasswordChange, ProfileUpdate, RegisterIn
from ..security import create_access_token, get_current_user, hash_password, verify_password
from ..services.audit import log_action
from ..services.serializers import user_out

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _token_response(user: User) -> dict:
    return {"access_token": create_access_token(user), "token_type": "bearer", "user": user_out(user)}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    """Self-registration always creates a Reporter. Other roles are granted by an Admin."""
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists. Sign in instead.")
    user = User(full_name=body.full_name.strip(), email=email, phone=body.phone,
                password_hash=hash_password(body.password), role="Reporter")
    db.add(user)
    db.flush()
    log_action(db, user.user_id, "user.registered", "user", user.user_id)
    db.commit()
    db.refresh(user)
    return _token_response(user)


def _authenticate(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is deactivated. Contact your administrator.")
    log_action(db, user.user_id, "user.login", "user", user.user_id)
    db.commit()
    return user


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    return _token_response(_authenticate(db, body.email, body.password))


@router.post("/token", include_in_schema=True, summary="OAuth2 form login (used by the Swagger 'Authorize' button)")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = _authenticate(db, form.username, form.password)
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_out(user)


@router.put("/me")
def update_me(body: ProfileUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if body.full_name is not None:
        user.full_name = body.full_name.strip()
    if body.phone is not None:
        user.phone = body.phone or None
    log_action(db, user.user_id, "user.profile_updated", "user", user.user_id)
    db.commit()
    return user_out(user)


@router.post("/me/password", status_code=204)
def change_password(body: PasswordChange, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    user.password_hash = hash_password(body.new_password)
    log_action(db, user.user_id, "user.password_changed", "user", user.user_id)
    db.commit()
