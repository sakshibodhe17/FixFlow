"""Audit trail helper. Every important action is written to audit_logs; request
timelines in the UI are built from these rows."""
import json

from sqlalchemy.orm import Session

from ..models import AuditLog


def log_action(db: Session, user_id: int | None, action: str, entity: str | None = None,
               entity_id: int | None = None, details: dict | str | None = None) -> None:
    if isinstance(details, dict):
        details = json.dumps(details, default=str)
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, details=details))
