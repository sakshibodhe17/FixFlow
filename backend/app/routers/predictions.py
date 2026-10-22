"""Failure prediction: run scoring, view risk, retrain/monitor the model, schedule preventive work."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import ml_engine
from ..database import get_db
from ..models import Asset, FailurePrediction, MaintenanceRequest, ModelRun, SLAPolicy, User
from ..schemas import PreventiveIn
from ..security import ADMIN, MANAGER, require_roles
from ..services.assignment import auto_assign
from ..services.audit import log_action
from ..services.serializers import asset_out, prediction_out, request_out
from .assets import latest_predictions

router = APIRouter(prefix="/api/predictions", tags=["Failure prediction"])
staff_only = require_roles(MANAGER, ADMIN)


@router.post("/run")
def run_predictions(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    result = ml_engine.predict_all(db)
    log_action(db, user.user_id, "ml.predicted", "model", None, result)
    db.commit()
    return result


@router.get("/latest")
def latest(risk_level: str | None = None, db: Session = Depends(get_db), _: User = Depends(staff_only)):
    """Latest score per asset with the features behind it and plain-language reasons."""
    preds = latest_predictions(db)
    assets = {a.asset_id: a for a in db.scalars(select(Asset).options(selectinload(Asset.location))
                                                 .where(Asset.status != "Retired"))}
    feats = ml_engine.current_features(db)
    feat_rows = {int(r.asset_id): r for _, r in feats.iterrows()} if not feats.empty else {}
    open_pm = set(db.scalars(select(MaintenanceRequest.asset_id).where(
        MaintenanceRequest.is_preventive.is_(True),
        MaintenanceRequest.status.in_(("Open", "Assigned", "In Progress", "On Hold")))))

    items = []
    for asset_id, p in preds.items():
        a = assets.get(asset_id)
        if not a or (risk_level and p.risk_level != risk_level):
            continue
        f = feat_rows.get(asset_id)
        items.append({
            **prediction_out(p),
            "asset": asset_out(a),
            "features": {k: float(f[k]) for k in ml_engine.NUMERIC_FEATURES} if f is not None else None,
            "reasons": ml_engine.explain(f, feats) if f is not None else [],
            "preventive_scheduled": asset_id in open_pm,
            "recommendation": "Schedule preventive maintenance" if p.risk_level == "High" else
                              "Monitor; inspect at next routine visit" if p.risk_level == "Medium" else
                              "No action needed",
        })
    items.sort(key=lambda x: -x["risk_score"])
    return items


@router.get("/asset/{asset_id}")
def asset_risk_history(asset_id: int, db: Session = Depends(get_db), _: User = Depends(staff_only)):
    rows = db.scalars(select(FailurePrediction).where(FailurePrediction.asset_id == asset_id)
                      .order_by(FailurePrediction.predicted_at.desc()).limit(90))
    return [prediction_out(p) for p in rows]


@router.post("/train")
def train(db: Session = Depends(get_db), user: User = Depends(require_roles(ADMIN))):
    try:
        info = ml_engine.train_model(db, trained_by=user.user_id)
    except ml_engine.InsufficientDataError as e:
        raise HTTPException(409, str(e))
    log_action(db, user.user_id, "ml.trained", "model", None,
               {"version": info["version"], "metrics": info["metrics"]})
    db.commit()
    return info


@router.get("/model")
def model_status(db: Session = Depends(get_db), _: User = Depends(staff_only)):
    runs = db.scalars(select(ModelRun).order_by(ModelRun.trained_at.desc()).limit(20)).all()
    bundle = ml_engine.load_bundle()
    return {
        "xgboost_available": ml_engine.HAS_XGBOOST,
        "active_version": bundle["version"] if bundle else "heuristic-v1",
        "active": {k: v for k, v in bundle.items() if k != "model"} if bundle else None,
        "feature_labels": ml_engine.FEATURE_LABELS,
        "horizon_days": ml_engine.HORIZON_DAYS,
        "runs": [{"run_id": r.run_id, "model_version": r.model_version, "algorithm": r.algorithm,
                  "n_samples": r.n_samples, "positive_rate": float(r.positive_rate) if r.positive_rate else None,
                  "metrics": r.metrics, "is_active": r.is_active, "trained_at": r.trained_at} for r in runs],
    }


@router.post("/preventive", status_code=201)
def schedule_preventive(body: PreventiveIn, db: Session = Depends(get_db), user: User = Depends(staff_only)):
    """Creates a preventive maintenance request due on the scheduled date and auto-assigns it."""
    asset = db.get(Asset, body.asset_id)
    if not asset or asset.status == "Retired":
        raise HTTPException(404, "Asset not found")
    due = body.scheduled_for if body.scheduled_for.tzinfo else body.scheduled_for.replace(tzinfo=timezone.utc)
    if due <= datetime.now(timezone.utc):
        raise HTTPException(400, "Pick a date in the future.")
    sla = db.scalar(select(SLAPolicy).where(SLAPolicy.severity == body.severity))
    pred = db.scalar(select(FailurePrediction).where(FailurePrediction.asset_id == asset.asset_id)
                     .order_by(FailurePrediction.predicted_at.desc()).limit(1))
    note = f"Predicted 30-day failure risk: {float(pred.risk_score):.0%} ({pred.risk_level}). " if pred else ""
    req = MaintenanceRequest(
        asset_id=asset.asset_id, reported_by=user.user_id, sla_id=sla.sla_id if sla else None,
        title=f"Preventive maintenance: {asset.asset_name}", description=note + (body.notes or ""),
        severity=body.severity, status="Open", is_preventive=True,
        reported_at=datetime.now(timezone.utc), resolution_due=due,
    )
    db.add(req)
    db.flush()
    db.refresh(req)
    log_action(db, user.user_id, "request.preventive_scheduled", "request", req.request_id,
               {"asset": asset.asset_name, "due": due})
    auto_assign(db, req, actor_id=user.user_id)
    db.commit()
    db.refresh(req)
    return request_out(req)
