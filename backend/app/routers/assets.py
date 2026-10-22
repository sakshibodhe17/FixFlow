"""Asset register, QR codes and repair history."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Asset, FailurePrediction, Location, MaintenanceRequest, RepairLog, User
from ..schemas import AssetIn, AssetUpdate
from ..security import ADMIN, MANAGER, STAFF, get_current_user, require_roles
from ..services.audit import log_action
from ..services.qr import new_qr_code, qr_data_uri, scan_url
from ..services.serializers import asset_out, feedback_out, repair_log_out

router = APIRouter(prefix="/api/assets", tags=["Assets"])
staff_only = require_roles(MANAGER, ADMIN)


def latest_predictions(db: Session) -> dict[int, FailurePrediction]:
    """Most recent prediction per asset (DISTINCT ON is PostgreSQL-specific)."""
    stmt = (select(FailurePrediction)
            .distinct(FailurePrediction.asset_id)
            .order_by(FailurePrediction.asset_id, FailurePrediction.predicted_at.desc()))
    return {p.asset_id: p for p in db.scalars(stmt)}


def _get_asset(db: Session, asset_id: int) -> Asset:
    a = db.get(Asset, asset_id)
    if not a:
        raise HTTPException(404, "Asset not found")
    return a


@router.get("")
def list_assets(q: str | None = None, category: str | None = None, location_id: int | None = None,
                building: str | None = None, status: str | None = None, include_retired: bool = False,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    stmt = select(Asset).options(selectinload(Asset.location)).order_by(Asset.asset_name)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Asset.asset_name).like(like), func.lower(Asset.qr_code).like(like)))
    if category:
        stmt = stmt.where(Asset.category == category)
    if location_id:
        stmt = stmt.where(Asset.location_id == location_id)
    if building:
        stmt = stmt.join(Location).where(Location.building == building)
    if status:
        stmt = stmt.where(Asset.status == status)
    elif not include_retired:
        stmt = stmt.where(Asset.status != "Retired")
    preds = latest_predictions(db) if user.role in STAFF else {}
    return [asset_out(a, preds.get(a.asset_id)) for a in db.scalars(stmt)]


@router.get("/by-qr/{code}")
def get_by_qr(code: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    code = code.strip()
    if "qr=" in code:  # accept the full scanned URL as well as the bare code
        code = code.split("qr=", 1)[1].split("&", 1)[0]
    a = db.scalar(select(Asset).where(Asset.qr_code == code))
    if not a:
        raise HTTPException(404, "No asset matches that QR code.")
    if a.status == "Retired":
        raise HTTPException(410, "This asset has been retired. Report it to your facility manager.")
    return asset_out(a)


@router.get("/{asset_id}")
def get_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    a = _get_asset(db, asset_id)
    pred = None
    if user.role in STAFF:
        pred = db.scalar(select(FailurePrediction).where(FailurePrediction.asset_id == asset_id)
                         .order_by(FailurePrediction.predicted_at.desc()).limit(1))
    return asset_out(a, pred)


@router.post("", status_code=201)
def create_asset(body: AssetIn, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    if body.location_id and not db.get(Location, body.location_id):
        raise HTTPException(400, "Unknown location")
    a = Asset(**body.model_dump(), qr_code=new_qr_code(db))
    db.add(a)
    db.flush()
    log_action(db, user.user_id, "asset.created", "asset", a.asset_id, {"name": a.asset_name, "qr": a.qr_code})
    db.commit()
    db.refresh(a)
    return asset_out(a)


@router.put("/{asset_id}")
def update_asset(asset_id: int, body: AssetUpdate, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    a = _get_asset(db, asset_id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("location_id") and not db.get(Location, changes["location_id"]):
        raise HTTPException(400, "Unknown location")
    for k, v in changes.items():
        setattr(a, k, v)
    log_action(db, user.user_id, "asset.updated", "asset", a.asset_id, changes)
    db.commit()
    db.refresh(a)
    return asset_out(a)


@router.delete("/{asset_id}")
def delete_asset(asset_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    """Assets with maintenance history are retired rather than deleted."""
    a = _get_asset(db, asset_id)
    has_history = db.scalar(select(func.count()).select_from(MaintenanceRequest)
                            .where(MaintenanceRequest.asset_id == asset_id))
    if has_history:
        a.status = "Retired"
        log_action(db, user.user_id, "asset.retired", "asset", asset_id)
        db.commit()
        return {"result": "retired"}
    db.delete(a)
    log_action(db, user.user_id, "asset.deleted", "asset", asset_id)
    db.commit()
    return {"result": "deleted"}


@router.get("/{asset_id}/qr")
def get_qr(asset_id: int, db: Session = Depends(get_db), _: User = Depends(staff_only)):
    a = _get_asset(db, asset_id)
    if not a.qr_code:
        a.qr_code = new_qr_code(db)
        db.commit()
    return {"asset_id": a.asset_id, "asset_name": a.asset_name, "qr_code": a.qr_code,
            "scan_url": scan_url(a.qr_code), "image": qr_data_uri(a.qr_code)}


@router.post("/{asset_id}/qr/regenerate")
def regenerate_qr(asset_id: int, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    a = _get_asset(db, asset_id)
    old = a.qr_code
    a.qr_code = new_qr_code(db)
    log_action(db, user.user_id, "asset.qr_regenerated", "asset", a.asset_id, {"old": old, "new": a.qr_code})
    db.commit()
    return {"asset_id": a.asset_id, "asset_name": a.asset_name, "qr_code": a.qr_code,
            "scan_url": scan_url(a.qr_code), "image": qr_data_uri(a.qr_code)}


@router.get("/{asset_id}/history")
def asset_history(asset_id: int, db: Session = Depends(get_db),
                  user: User = Depends(require_roles("Technician", MANAGER, ADMIN))):
    """Complete repair history of an asset with totals."""
    a = _get_asset(db, asset_id)
    reqs = db.scalars(
        select(MaintenanceRequest)
        .options(selectinload(MaintenanceRequest.repair_logs).selectinload(RepairLog.technician),
                 selectinload(MaintenanceRequest.feedback))
        .where(MaintenanceRequest.asset_id == asset_id)
        .order_by(MaintenanceRequest.reported_at.desc())
    ).all()
    items, total_cost, total_down, total_labour = [], 0.0, 0.0, 0.0
    for r in reqs:
        logs = [repair_log_out(l) for l in r.repair_logs]
        total_cost += sum(l["repair_cost"] or 0 for l in logs)
        total_down += sum(l["downtime_hours"] or 0 for l in logs)
        total_labour += sum(l["labour_hours"] or 0 for l in logs)
        items.append({"request_id": r.request_id, "title": r.title, "severity": r.severity, "status": r.status,
                      "is_preventive": r.is_preventive, "reported_at": r.reported_at, "resolved_at": r.resolved_at,
                      "repair_logs": logs, "feedback": feedback_out(r.feedback)})
    failures = [r for r in reqs if not r.is_preventive]
    return {
        "asset": asset_out(a),
        "summary": {"total_requests": len(reqs), "failures": len(failures),
                    "total_repair_cost": round(total_cost, 2), "total_downtime_hours": round(total_down, 2),
                    "total_labour_hours": round(total_labour, 2),
                    "last_failure_at": failures[0].reported_at if failures else None},
        "history": items,
    }
