"""SLA policies, live SLA monitor and escalations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import UNRESOLVED_STATUSES, Asset, Escalation, MaintenanceRequest, SLAPolicy, Technician, User
from ..schemas import SLAPolicyIn, SLAPolicyUpdate
from ..security import ADMIN, MANAGER, get_current_user, require_roles
from ..services.audit import log_action
from ..services.serializers import escalation_out, request_out
from ..services.settings_store import get_setting

router = APIRouter(prefix="/api/sla", tags=["SLA & escalations"])
staff_only = require_roles(MANAGER, ADMIN)
SEVERITY_ORDER = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}


def _policy_out(p: SLAPolicy) -> dict:
    return {"sla_id": p.sla_id, "severity": p.severity, "response_hours": p.response_hours,
            "resolution_hours": p.resolution_hours}


@router.get("/policies")
def list_policies(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.scalars(select(SLAPolicy)).all()
    return [_policy_out(p) for p in sorted(rows, key=lambda p: SEVERITY_ORDER.get(p.severity, 9))]


@router.post("/policies", status_code=201)
def create_policy(body: SLAPolicyIn, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    if db.scalar(select(SLAPolicy).where(SLAPolicy.severity == body.severity)):
        raise HTTPException(409, f"A {body.severity} policy already exists. Edit it instead.")
    p = SLAPolicy(**body.model_dump())
    db.add(p)
    db.flush()
    log_action(db, user.user_id, "sla.created", "sla", p.sla_id, body.model_dump())
    db.commit()
    return _policy_out(p)


@router.put("/policies/{sla_id}")
def update_policy(sla_id: int, body: SLAPolicyUpdate, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    p = db.get(SLAPolicy, sla_id)
    if not p:
        raise HTTPException(404, "Policy not found")
    if body.resolution_hours < body.response_hours:
        raise HTTPException(400, "Resolution time must be at least the response time.")
    p.response_hours, p.resolution_hours = body.response_hours, body.resolution_hours
    log_action(db, user.user_id, "sla.updated", "sla", p.sla_id, body.model_dump())
    db.commit()
    # Existing requests keep their original due dates; only new requests use the new rule.
    return _policy_out(p)


@router.get("/monitor")
def sla_monitor(db: Session = Depends(get_db), _: User = Depends(staff_only)):
    """All unresolved requests with live SLA state, most urgent first."""
    rows = db.scalars(
        select(MaintenanceRequest)
        .options(selectinload(MaintenanceRequest.asset).selectinload(Asset.location),
                 selectinload(MaintenanceRequest.technician).selectinload(Technician.user),
                 selectinload(MaintenanceRequest.reporter), selectinload(MaintenanceRequest.sla),
                 selectinload(MaintenanceRequest.feedback))
        .where(MaintenanceRequest.status.in_(UNRESOLVED_STATUSES))
    ).all()
    warn = get_setting(db, "sla_warning_pct")
    items = [request_out(r, warn) for r in rows]
    items.sort(key=lambda r: (r["sla"]["seconds_remaining"] if r["sla"] else 10**12))
    counts = {"breached": 0, "at_risk": 0, "on_track": 0}
    for r in items:
        if r["sla"]:
            counts[r["sla"]["state"]] = counts.get(r["sla"]["state"], 0) + 1
    return {"counts": counts, "warning_pct": warn, "items": items}


@router.get("/escalations")
def list_escalations(acknowledged: bool | None = None, mine: bool = False, limit: int = 100,
                     db: Session = Depends(get_db), user: User = Depends(staff_only)):
    stmt = (select(Escalation)
            .options(selectinload(Escalation.request).selectinload(MaintenanceRequest.asset),
                     selectinload(Escalation.recipient))
            .order_by(Escalation.escalated_at.desc()).limit(min(limit, 500)))
    if acknowledged is not None:
        stmt = stmt.where(Escalation.is_acknowledged.is_(acknowledged))
    if mine:
        stmt = stmt.where(Escalation.escalated_to == user.user_id)
    return [escalation_out(e, include_request=True) for e in db.scalars(stmt)]


@router.post("/escalations/{escalation_id}/acknowledge")
def acknowledge(escalation_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    e = db.get(Escalation, escalation_id)
    if not e:
        raise HTTPException(404, "Escalation not found")
    # acknowledging clears the same alert for every manager who received it
    for other in db.scalars(select(Escalation).where(Escalation.request_id == e.request_id,
                                                     Escalation.level == e.level)):
        other.is_acknowledged = True
    log_action(db, user.user_id, "escalation.acknowledged", "request", e.request_id, {"level": e.level})
    db.commit()
    return {"ok": True}


@router.post("/check-now")
def check_now(_: User = Depends(staff_only)):
    from ..scheduler import check_sla_deadlines
    return check_sla_deadlines()


@router.get("/escalations/count")
def escalation_count(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    n = db.scalar(select(func.count(func.distinct(Escalation.request_id)))
                  .where(Escalation.is_acknowledged.is_(False)))
    return {"unacknowledged": n or 0}
