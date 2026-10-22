"""In-app notifications + email (SMTP, or written to the log when SMTP is disabled)."""
import logging
import smtplib
import threading
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Notification, User
from .settings_store import get_setting

log = logging.getLogger("fixflow.notify")


def _send_email_now(to: str, subject: str, body: str) -> None:
    if not settings.SMTP_ENABLED:
        log.info("EMAIL (SMTP disabled) to=%s subject=%s | %s", to, subject, body.replace("\n", " "))
        return
    msg = EmailMessage()
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg["Subject"] = f"[FixFlow] {subject}"
    msg.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        log.info("Email sent to %s: %s", to, subject)
    except Exception:  # an email failure must never break an API call
        log.exception("Failed to send email to %s", to)


def send_email(to: str, subject: str, body: str) -> None:
    """Send in a background thread so API calls stay fast."""
    threading.Thread(target=_send_email_now, args=(to, subject, body), daemon=True).start()


def notify(db: Session, user: User | int | None, title: str, message: str = "",
           link: str | None = None, email: bool = True) -> None:
    if isinstance(user, int):
        user = db.get(User, user)
    if user is None or not user.is_active:
        return
    db.add(Notification(user_id=user.user_id, title=title[:200], message=message, link=link))
    if email and get_setting(db, "email_notifications"):
        url = f"{settings.FRONTEND_URL}{link}" if link else settings.FRONTEND_URL
        send_email(user.email, title, f"Hi {user.full_name},\n\n{message}\n\nOpen in FixFlow: {url}\n")


def users_with_roles(db: Session, *roles: str) -> list[User]:
    return list(db.scalars(select(User).where(User.role.in_(roles), User.is_active.is_(True))))


def notify_roles(db: Session, roles: tuple[str, ...], title: str, message: str = "",
                 link: str | None = None, email: bool = True) -> None:
    for u in users_with_roles(db, *roles):
        notify(db, u, title, message, link, email)
