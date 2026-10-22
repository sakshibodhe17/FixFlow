"""Key/value system settings (notification + escalation configuration) stored in the DB."""
from sqlalchemy.orm import Session

from ..models import SystemSetting

# key -> (default value, type, description)
DEFAULTS: dict[str, tuple[object, type, str]] = {
    "email_notifications": (True, bool, "Send email in addition to in-app notifications"),
    "sla_warning_pct": (75, int, "Warn managers once this % of the resolution time has passed"),
    "escalate_to_admins": (False, bool, "Also send SLA escalations to administrators"),
    "notify_reporter_on_status": (True, bool, "Notify reporters on every status change"),
    "risk_medium_threshold": (0.40, float, "Risk score at or above which an asset is Medium risk"),
    "risk_high_threshold": (0.70, float, "Risk score at or above which an asset is High risk"),
    "auto_retrain_weekly": (True, bool, "Retrain the failure model every Sunday at 03:00 UTC"),
    "nightly_predictions": (True, bool, "Score every asset every night at 02:00 UTC"),
}


def _cast(raw, typ: type):
    if typ is bool:
        return str(raw).lower() in ("1", "true", "yes", "on")
    return typ(raw)


def get_setting(db: Session, key: str):
    default, typ, _ = DEFAULTS[key]
    row = db.get(SystemSetting, key)
    if row is None:
        return default
    try:
        return _cast(row.value, typ)
    except (TypeError, ValueError):
        return default


def all_settings(db: Session) -> list[dict]:
    return [
        {"key": k, "value": get_setting(db, k), "type": t.__name__, "description": d}
        for k, (_, t, d) in DEFAULTS.items()
    ]


def set_setting(db: Session, key: str, value) -> None:
    if key not in DEFAULTS:
        raise KeyError(key)
    _, typ, _ = DEFAULTS[key]
    value = _cast(value, typ)  # raises ValueError on bad input
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=str(value)))
    else:
        row.value = str(value)
