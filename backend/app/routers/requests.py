"""
Maintenance requests: reporting, photos, automated assignment and the lifecycle

    Open → Assigned → In Progress ⇄ On Hold → Resolved → Closed
                                                   ↘ Reopened → Assigned …
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..models import (
    ACTIVE_STATUSES, UNRESOLVED_STATUSES, Asset, AuditLog, Feedback, MaintenanceRequest, RepairLog,
    RequestPhoto, SLAPolicy, Technician, User,
)
from ..schemas import AssignIn, CompleteWork, FeedbackIn, ReopenIn, RepairLogIn, RequestCreate, StatusOverride
from ..security import ADMIN, MANAGER, REPORTER, STAFF, TECHNICIAN, get_current_user, require_roles
from ..services.assignment import assign_request, auto_assign, candidate_technicians, required_skill
from ..services.audit import log_action
from ..services.notify import notify, notify_roles
from ..services.serializers import (
    escalation_out, feedback_out, photo_out, repair_log_out, request_out, technician_out,
)
from ..services.settings_store import get_setting

router = APIRouter(prefix="/api/requests", tags=["Maintenance requests"])

ALLOWED_IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _load_options():
    return (
        selectinload(MaintenanceRequest.asset).selectinload(Asset.location),
        selectinload(MaintenanceRequest.reporter),
        selectinload(MaintenanceRequest.technician).selectinload(Technician.user),
        selectinload(MaintenanceRequest.sla),
        selectinload(MaintenanceRequest.feedback),
    )


def _get(db: Session, request_id: int) -> MaintenanceRequest:
    r = db.scalar(select(MaintenanceRequest).options(*_load_options())
                  .where(MaintenanceRequest.request_id == request_id))
    if not r:
        raise HTTPException(404, "Request not found")
    return r


def _tech(user: User) -> Technician:
    if user.role != TECHNICIAN or user.technician is None:
        raise HTTPException(403, "Only technicians can do this.")
    return user.technician


def _ensure_assigned(req: MaintenanceRequest, user: User) -> Technician:
    tech = _tech(user)
    if req.assigned_to != tech.technician_id:
        raise HTTPException(403, "This request is not assigned to you.")
    return tech


def _can_view(req: MaintenanceRequest, user: User, db: Session) -> bool:
    if user.role in STAFF or req.reported_by == user.user_id:
        return True
    if user.role == TECHNICIAN and user.technician:
        tid = user.technician.technician_id
        if req.assigned_to == tid:
            return True
        return bool(db.scalar(select(func.count()).select_from(RepairLog)
                              .where(RepairLog.request_id == req.request_id, RepairLog.technician_id == tid)))
    return False


def _transition(req: MaintenanceRequest, allowed_from: tuple[str, ...], to: str) -> str:
    if req.status not in allowed_from:
        raise HTTPException(409, f"Can't move a request from {req.status} to {to}.")
    old = req.status
    req.status = to
    return old


def _stop_timer(req: MaintenanceRequest) -> None:
    if req.work_started_at:
        req.work_seconds = (req.work_seconds or 0) + int((now() - req.work_started_at).total_seconds())
        req.work_started_at = None


def _refresh_asset_status(db: Session, asset: Asset) -> None:
    """Asset is Working unless it has unresolved non-preventive requests."""
    if asset.status == "Retired":
        return
    active = db.scalars(select(MaintenanceRequest.status).where(
        MaintenanceRequest.asset_id == asset.asset_id,
        MaintenanceRequest.status.in_(UNRESOLVED_STATUSES),
        MaintenanceRequest.is_preventive.is_(False),
    )).all()
    if not active:
        asset.status = "Working"
    elif "In Progress" in active:
        asset.status = "Under Repair"
    else:
        asset.status = "Faulty"


def _status_notice(db: Session, req: MaintenanceRequest, message: str) -> None:
    if get_setting(db, "notify_reporter_on_status"):
        notify(db, req.reporter, f"Request #{req.request_id}: {req.status}", message,
               link=f"/requests/{req.request_id}")


# =============================================================================
# Create & list
# =============================================================================
@router.post("", status_code=201)
def create_request(body: RequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    asset = None
    if body.asset_id:
        asset = db.get(Asset, body.asset_id)
    elif body.qr_code:
        asset = db.scalar(select(Asset).where(Asset.qr_code == body.qr_code.strip()))
    if not asset:
        raise HTTPException(400, "Choose the asset that has the problem, or scan its QR code.")
    if asset.status == "Retired":
        raise HTTPException(400, "This asset has been retired.")
    sla = db.scalar(select(SLAPolicy).where(SLAPolicy.severity == body.severity))
    if not sla:
        raise HTTPException(400, f"No SLA policy exists for {body.severity} severity. Ask a manager to add one.")

    t = now()
    req = MaintenanceRequest(
        asset_id=asset.asset_id, reported_by=user.user_id, sla_id=sla.sla_id, title=body.title.strip(),
        description=body.description, severity=body.severity, status="Open", reported_at=t,
        resolution_due=t + timedelta(hours=sla.resolution_hours),
    )
    db.add(req)
    db.flush()
    db.refresh(req)
    if asset.status == "Working":
        asset.status = "Faulty"
    log_action(db, user.user_id, "request.created", "request", req.request_id,
               {"severity": req.severity, "asset": asset.asset_name})

    tech = auto_assign(db, req, actor_id=None)
    notify(db, user, f"Request #{req.request_id} received",
           f"We logged \"{req.title}\". " + (f"{tech.user.full_name} is assigned." if tech
                                              else "A manager will assign a technician shortly."),
           link=f"/requests/{req.request_id}", email=False)
    if req.severity == "Critical":
        notify_roles(db, (MANAGER,), f"Critical request #{req.request_id}",
                     f"{req.title} — {asset.asset_name}", link=f"/requests/{req.request_id}")
    db.commit()
    return request_out(_get(db, req.request_id), get_setting(db, "sla_warning_pct"))


@router.get("")
def list_requests(
    status: str | None = None, severity: str | None = None, asset_id: int | None = None,
    technician_id: int | None = None, q: str | None = None, overdue: bool = False,
    preventive: bool | None = None, mine: bool = False, limit: int = 100, offset: int = 0,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
):
    """Role-scoped: reporters see their own requests, technicians their assignments,
    managers/admins everything. `status` accepts a comma-separated list."""
    stmt = select(MaintenanceRequest).options(*_load_options())
    if user.role == REPORTER or mine:
        stmt = stmt.where(MaintenanceRequest.reported_by == user.user_id)
    elif user.role == TECHNICIAN:
        tid = user.technician.technician_id if user.technician else -1
        stmt = stmt.where(MaintenanceRequest.assigned_to == tid)
    elif technician_id:
        stmt = stmt.where(MaintenanceRequest.assigned_to == technician_id)

    if status:
        stmt = stmt.where(MaintenanceRequest.status.in_([s.strip() for s in status.split(",")]))
    if severity:
        stmt = stmt.where(MaintenanceRequest.severity.in_([s.strip() for s in severity.split(",")]))
    if asset_id:
        stmt = stmt.where(MaintenanceRequest.asset_id == asset_id)
    if preventive is not None:
        stmt = stmt.where(MaintenanceRequest.is_preventive.is_(preventive))
    if overdue:
        stmt = stmt.where(MaintenanceRequest.status.in_(UNRESOLVED_STATUSES),
                          MaintenanceRequest.resolution_due < now())
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.join(Asset).where(or_(func.lower(MaintenanceRequest.title).like(like),
                                          func.lower(Asset.asset_name).like(like)))

    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = db.scalars(stmt.order_by(MaintenanceRequest.reported_at.desc())
                      .limit(min(limit, 500)).offset(offset)).all()
    warn = get_setting(db, "sla_warning_pct")
    return {"total": total, "items": [request_out(r, warn) for r in rows]}


@router.get("/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    if not _can_view(req, user, db):
        raise HTTPException(403, "You don't have access to this request.")
    data = request_out(req, get_setting(db, "sla_warning_pct"))
    data["photos"] = [photo_out(p) for p in sorted(req.photos, key=lambda p: p.uploaded_at)]
    data["repair_logs"] = [repair_log_out(l) for l in sorted(req.repair_logs, key=lambda l: l.log_id)]
    data["feedback"] = feedback_out(req.feedback)

    timeline = db.execute(
        select(AuditLog, User.full_name).outerjoin(User, AuditLog.user_id == User.user_id)
        .where(AuditLog.entity == "request", AuditLog.entity_id == request_id)
        .order_by(AuditLog.created_at)
    ).all()
    data["timeline"] = [{"action": a.action, "at": a.created_at, "by": name or "System",
                         "details": json.loads(a.details) if a.details and a.details.startswith("{") else a.details}
                        for a, name in timeline]

    if user.role != REPORTER:
        past = db.scalars(select(MaintenanceRequest)
                          .where(MaintenanceRequest.asset_id == req.asset_id,
                                 MaintenanceRequest.request_id != req.request_id)
                          .order_by(MaintenanceRequest.reported_at.desc()).limit(10)).all()
        data["asset_history"] = [{"request_id": p.request_id, "title": p.title, "status": p.status,
                                  "severity": p.severity, "reported_at": p.reported_at,
                                  "resolved_at": p.resolved_at} for p in past]
    if user.role in STAFF:
        data["escalations"] = [escalation_out(e) for e in req.escalations]
    return data


# =============================================================================
# Photos
# =============================================================================
@router.post("/{request_id}/photos", status_code=201)
async def upload_photos(request_id: int, files: list[UploadFile] = File(...), photo_type: str = Form("Before"),
                        db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    if photo_type not in ("Before", "After"):
        raise HTTPException(400, "photo_type must be Before or After")
    allowed = (user.role in STAFF or req.reported_by == user.user_id or
               (user.role == TECHNICIAN and user.technician and req.assigned_to == user.technician.technician_id))
    if not allowed:
        raise HTTPException(403, "You can't add photos to this request.")
    if len(files) > 6:
        raise HTTPException(400, "Upload up to 6 photos at a time.")

    saved = []
    for f in files:
        ext = ALLOWED_IMAGE_TYPES.get(f.content_type or "")
        if not ext:
            raise HTTPException(400, f"{f.filename}: only JPG, PNG, WEBP or GIF images are accepted.")
        content = await f.read()
        if len(content) > settings.MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(400, f"{f.filename} is larger than {settings.MAX_UPLOAD_MB} MB.")
        name = f"req{request_id}_{photo_type.lower()}_{uuid.uuid4().hex[:12]}{ext}"
        Path(settings.UPLOAD_DIR / name).write_bytes(content)
        photo = RequestPhoto(request_id=request_id, photo_url=f"/uploads/{name}", photo_type=photo_type)
        db.add(photo)
        saved.append(photo)
    db.flush()
    log_action(db, user.user_id, "request.photos_added", "request", request_id,
               {"count": len(saved), "type": photo_type})
    db.commit()
    return [photo_out(p) for p in saved]


# =============================================================================
# Technician actions: accept → start ⇄ pause → complete
# =============================================================================
@router.post("/{request_id}/accept")
def accept(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    _ensure_assigned(req, user)
    if req.status != "Assigned":
        raise HTTPException(409, "Only newly assigned requests can be accepted.")
    req.accepted_at = now()
    log_action(db, user.user_id, "request.accepted", "request", request_id)
    _status_notice(db, req, f"{user.full_name} accepted your request and will start soon.")
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/start")
def start(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    _ensure_assigned(req, user)
    old = _transition(req, ("Assigned", "On Hold"), "In Progress")
    req.accepted_at = req.accepted_at or now()
    req.work_started_at = now()
    _refresh_asset_status(db, req.asset)
    log_action(db, user.user_id, "request.started" if old == "Assigned" else "request.resumed", "request", request_id)
    if old == "Assigned":
        _status_notice(db, req, f"{user.full_name} has started work.")
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/pause")
def pause(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    _ensure_assigned(req, user)
    _transition(req, ("In Progress",), "On Hold")
    _stop_timer(req)
    log_action(db, user.user_id, "request.paused", "request", request_id)
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/repair-logs", status_code=201)
def add_repair_log(request_id: int, body: RepairLogIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)):
    """Record interim work (parts, labour, cost) without resolving the request."""
    req = _get(db, request_id)
    tech = _ensure_assigned(req, user)
    if req.status not in ACTIVE_STATUSES:
        raise HTTPException(409, "Logs can only be added while the job is active.")
    log = RepairLog(request_id=request_id, technician_id=tech.technician_id, work_notes=body.work_notes,
                    parts_used=body.parts_used,
                    labour_hours=Decimal(str(body.labour_hours)) if body.labour_hours is not None else None,
                    repair_cost=Decimal(str(body.repair_cost)) if body.repair_cost is not None else None,
                    completed_at=now())
    db.add(log)
    db.flush()
    log_action(db, user.user_id, "request.log_added", "request", request_id)
    db.commit()
    db.refresh(log)
    return repair_log_out(log)


@router.post("/{request_id}/complete")
def complete(request_id: int, body: CompleteWork, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    tech = _ensure_assigned(req, user)
    _transition(req, ("In Progress", "On Hold"), "Resolved")
    _stop_timer(req)
    t = now()
    labour = body.labour_hours if body.labour_hours is not None else round((req.work_seconds or 0) / 3600, 2)
    downtime = body.downtime_hours if body.downtime_hours is not None else \
        round((t - req.reported_at).total_seconds() / 3600, 2)
    db.add(RepairLog(
        request_id=request_id, technician_id=tech.technician_id, work_notes=body.work_notes,
        parts_used=body.parts_used, labour_hours=Decimal(str(labour)), repair_cost=Decimal(str(body.repair_cost)),
        downtime_hours=Decimal(str(min(downtime, 9999))), completed_at=t,
    ))
    req.resolved_at = t
    tech.current_workload = max(0, (tech.current_workload or 0) - 1)
    _refresh_asset_status(db, req.asset)
    log_action(db, user.user_id, "request.resolved", "request", request_id,
               {"labour_hours": labour, "repair_cost": body.repair_cost})
    notify(db, req.reporter, f"Request #{request_id} resolved",
           f"{user.full_name} marked \"{req.title}\" as fixed. Please confirm and rate the repair, "
           f"or reopen it if the problem is still there.", link=f"/requests/{request_id}")
    db.commit()
    return request_out(_get(db, request_id))


# =============================================================================
# Reporter actions: feedback/close, reopen
# =============================================================================
def _ensure_owner_or_staff(req: MaintenanceRequest, user: User) -> None:
    if not (req.reported_by == user.user_id or user.role in STAFF):
        raise HTTPException(403, "Only the person who reported this can do that.")


@router.post("/{request_id}/feedback")
def give_feedback(request_id: int, body: FeedbackIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    if req.reported_by != user.user_id:
        raise HTTPException(403, "Only the person who reported this can rate it.")
    if req.status not in ("Resolved", "Closed"):
        raise HTTPException(409, "You can rate a repair once it's resolved.")
    if req.feedback:
        req.feedback.rating, req.feedback.comment = body.rating, body.comment
    else:
        db.add(Feedback(request_id=request_id, user_id=user.user_id, rating=body.rating, comment=body.comment))
    if req.status == "Resolved":
        req.status = "Closed"
        req.closed_at = now()
    log_action(db, user.user_id, "request.rated", "request", request_id, {"rating": body.rating})
    if req.technician:
        notify(db, req.technician.user, f"You got a {body.rating}★ rating on #{request_id}",
               body.comment or "", link=f"/requests/{request_id}", email=False)
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/close")
def close(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    _ensure_owner_or_staff(req, user)
    _transition(req, ("Resolved",), "Closed")
    req.closed_at = now()
    log_action(db, user.user_id, "request.closed", "request", request_id)
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/reopen")
def reopen(request_id: int, body: ReopenIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    req = _get(db, request_id)
    _ensure_owner_or_staff(req, user)
    _transition(req, ("Resolved", "Closed"), "Reopened")
    t = now()
    req.resolved_at = None
    req.closed_at = None
    req.reopen_count = (req.reopen_count or 0) + 1
    if req.sla:  # the SLA clock restarts
        req.resolution_due = t + timedelta(hours=req.sla.resolution_hours)
    _refresh_asset_status(db, req.asset)
    log_action(db, user.user_id, "request.reopened", "request", request_id, {"reason": body.reason})
    notify_roles(db, (MANAGER,), f"Request #{request_id} reopened", f"{user.full_name}: {body.reason}",
                 link=f"/requests/{request_id}")

    # Prefer the original technician if still available, otherwise run the engine again.
    prev = req.technician
    if prev and prev.is_available and prev.user.is_active:
        assign_request(db, req, prev, actor_id=None, reason="reopen")
    else:
        auto_assign(db, req)
    db.commit()
    return request_out(_get(db, request_id))


# =============================================================================
# Manager actions: review/override assignment, status override
# =============================================================================
@router.get("/{request_id}/candidates")
def candidates(request_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGER, ADMIN))):
    """Technicians for the reassign dialog, best match first."""
    req = _get(db, request_id)
    skill = required_skill(db, req.asset)
    matching = {t.technician_id for t in candidate_technicians(db, skill, only_available=False)} if skill else set()
    everyone = candidate_technicians(db, None, only_available=False)
    everyone.sort(key=lambda t: (t.technician_id not in matching, not t.is_available, t.current_workload))
    return {
        "required_skill": skill.skill_name if skill else None,
        "technicians": [technician_out(t, {"skill_match": t.technician_id in matching}) for t in everyone],
    }


@router.put("/{request_id}/assign")
def manual_assign(request_id: int, body: AssignIn, db: Session = Depends(get_db),
                  user: User = Depends(require_roles(MANAGER, ADMIN))):
    req = _get(db, request_id)
    if req.status in ("Resolved", "Closed"):
        raise HTTPException(409, "Reopen the request before reassigning it.")
    tech = db.get(Technician, body.technician_id)
    if not tech or not tech.user.is_active:
        raise HTTPException(404, "Technician not found")
    assign_request(db, req, tech, actor_id=user.user_id, reason="manual")
    db.commit()
    return request_out(_get(db, request_id))


@router.post("/{request_id}/auto-assign")
def rerun_auto_assign(request_id: int, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(MANAGER, ADMIN))):
    req = _get(db, request_id)
    if req.status in ("Resolved", "Closed"):
        raise HTTPException(409, "Reopen the request before reassigning it.")
    if not auto_assign(db, req, actor_id=user.user_id):
        db.commit()
        raise HTTPException(409, "No available technician has the required skill.")
    db.commit()
    return request_out(_get(db, request_id))


@router.patch("/{request_id}/status")
def override_status(request_id: int, body: StatusOverride, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(MANAGER, ADMIN))):
    req = _get(db, request_id)
    old, new = req.status, body.status
    if old == new:
        return request_out(req)
    if new in ("Assigned", "In Progress", "On Hold") and not req.assigned_to:
        raise HTTPException(400, "Assign a technician first.")
    tech = db.get(Technician, req.assigned_to) if req.assigned_to else None
    if tech:  # keep workload consistent
        if old in ACTIVE_STATUSES and new not in ACTIVE_STATUSES:
            tech.current_workload = max(0, tech.current_workload - 1)
        elif old not in ACTIVE_STATUSES and new in ACTIVE_STATUSES:
            tech.current_workload += 1
    if new != "In Progress":
        _stop_timer(req)
    t = now()
    if new == "Resolved":
        req.resolved_at = t
    elif new == "Closed":
        req.resolved_at = req.resolved_at or t
        req.closed_at = t
    elif new in UNRESOLVED_STATUSES:
        req.resolved_at = None
        req.closed_at = None
    req.status = new
    _refresh_asset_status(db, req.asset)
    log_action(db, user.user_id, "request.status_override", "request", request_id,
               {"from": old, "to": new, "note": body.note})
    _status_notice(db, req, body.note or f"Status changed from {old} to {new} by a manager.")
    db.commit()
    return request_out(_get(db, request_id))
