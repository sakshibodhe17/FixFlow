"""SLA math shared by the API, the scheduler and analytics."""
from datetime import datetime, timedelta, timezone

from ..models import MaintenanceRequest

RESOLVED = ("Resolved", "Closed")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def sla_window_start(req: MaintenanceRequest) -> datetime:
    """Start of the current SLA window. After a reopen the window restarts, so it is
    derived from the due date rather than reported_at."""
    if req.sla and req.resolution_due:
        return req.resolution_due - timedelta(hours=req.sla.resolution_hours)
    return req.reported_at


def response_due(req: MaintenanceRequest) -> datetime | None:
    if not req.sla:
        return None
    return sla_window_start(req) + timedelta(hours=req.sla.response_hours)


def sla_snapshot(req: MaintenanceRequest, warn_pct: int = 75, now: datetime | None = None) -> dict | None:
    """Returns where a request stands against its SLA:
    on_track / at_risk / breached for open work, met / missed for resolved work."""
    if not req.resolution_due:
        return None
    now = now or _now()
    start = sla_window_start(req)
    due = req.resolution_due
    total = max((due - start).total_seconds(), 1)
    end = req.resolved_at if (req.status in RESOLVED and req.resolved_at) else now
    pct = round((end - start).total_seconds() / total * 100, 1)

    if req.status in RESOLVED and req.resolved_at:
        state = "met" if req.resolved_at <= due else "missed"
    elif now > due:
        state = "breached"
    elif pct >= warn_pct:
        state = "at_risk"
    else:
        state = "on_track"

    rd = response_due(req)
    return {
        "state": state,
        "pct_elapsed": max(pct, 0),
        "window_start": start,
        "resolution_due": due,
        "response_due": rd,
        "responded": req.accepted_at is not None or req.status not in ("Open", "Assigned", "Reopened"),
        "seconds_remaining": int((due - now).total_seconds()) if req.status not in RESOLVED else None,
    }
