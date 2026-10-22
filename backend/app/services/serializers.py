"""Turn ORM objects into JSON-friendly dicts (Decimals become floats)."""
from decimal import Decimal

from ..models import (
    Asset, Escalation, Feedback, FailurePrediction, Location, MaintenanceRequest,
    RepairLog, RequestPhoto, Technician, User,
)
from .sla import sla_snapshot


def num(v):
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else v


def user_out(u: User | None) -> dict | None:
    if u is None:
        return None
    return {
        "user_id": u.user_id, "full_name": u.full_name, "email": u.email, "phone": u.phone,
        "role": u.role, "is_active": u.is_active, "created_at": u.created_at,
        "technician_id": u.technician.technician_id if u.technician else None,
    }


def user_brief(u: User | None) -> dict | None:
    if u is None:
        return None
    return {"user_id": u.user_id, "full_name": u.full_name, "email": u.email, "phone": u.phone}


def location_out(l: Location | None) -> dict | None:
    if l is None:
        return None
    return {"location_id": l.location_id, "building": l.building, "floor": l.floor, "room": l.room, "label": l.label}


def asset_out(a: Asset, latest_prediction: FailurePrediction | None = None) -> dict:
    d = {
        "asset_id": a.asset_id, "asset_name": a.asset_name, "category": a.category, "qr_code": a.qr_code,
        "purchase_date": a.purchase_date, "warranty_expiry": a.warranty_expiry, "status": a.status,
        "created_at": a.created_at, "location_id": a.location_id, "location": location_out(a.location),
    }
    if latest_prediction is not None:
        d["risk"] = prediction_out(latest_prediction)
    return d


def prediction_out(p: FailurePrediction) -> dict:
    return {
        "prediction_id": p.prediction_id, "asset_id": p.asset_id, "risk_score": num(p.risk_score),
        "risk_level": p.risk_level, "model_version": p.model_version, "predicted_at": p.predicted_at,
    }


def technician_out(t: Technician | None, extra: dict | None = None) -> dict | None:
    if t is None:
        return None
    d = {
        "technician_id": t.technician_id, "user_id": t.user_id,
        "full_name": t.user.full_name if t.user else None,
        "email": t.user.email if t.user else None,
        "phone": t.user.phone if t.user else None,
        "is_available": t.is_available, "current_workload": t.current_workload,
        "skills": [{"skill_id": s.skill_id, "skill_name": s.skill_name} for s in t.skills],
    }
    if extra:
        d.update(extra)
    return d


def photo_out(p: RequestPhoto) -> dict:
    return {"photo_id": p.photo_id, "photo_url": p.photo_url, "photo_type": p.photo_type, "uploaded_at": p.uploaded_at}


def repair_log_out(r: RepairLog) -> dict:
    return {
        "log_id": r.log_id, "request_id": r.request_id, "technician_id": r.technician_id,
        "technician_name": r.technician.user.full_name if r.technician and r.technician.user else None,
        "work_notes": r.work_notes, "parts_used": r.parts_used, "labour_hours": num(r.labour_hours),
        "repair_cost": num(r.repair_cost), "downtime_hours": num(r.downtime_hours), "completed_at": r.completed_at,
    }


def feedback_out(f: Feedback | None) -> dict | None:
    if f is None:
        return None
    return {"feedback_id": f.feedback_id, "rating": f.rating, "comment": f.comment, "created_at": f.created_at,
            "user_id": f.user_id}


def escalation_out(e: Escalation, include_request: bool = False) -> dict:
    d = {
        "escalation_id": e.escalation_id, "request_id": e.request_id, "escalated_to": e.escalated_to,
        "recipient_name": e.recipient.full_name if e.recipient else None, "reason": e.reason,
        "level": e.level, "is_acknowledged": e.is_acknowledged, "escalated_at": e.escalated_at,
    }
    if include_request and e.request:
        r = e.request
        d["request"] = {"request_id": r.request_id, "title": r.title, "severity": r.severity, "status": r.status,
                        "asset_name": r.asset.asset_name if r.asset else None, "resolution_due": r.resolution_due}
    return d


def request_out(r: MaintenanceRequest, warn_pct: int = 75) -> dict:
    tech = r.technician
    return {
        "request_id": r.request_id, "title": r.title, "description": r.description,
        "severity": r.severity, "status": r.status, "is_preventive": r.is_preventive,
        "reported_at": r.reported_at, "resolution_due": r.resolution_due, "resolved_at": r.resolved_at,
        "closed_at": r.closed_at, "assigned_at": r.assigned_at, "accepted_at": r.accepted_at,
        "work_started_at": r.work_started_at, "work_seconds": r.work_seconds, "reopen_count": r.reopen_count,
        "asset": {
            "asset_id": r.asset.asset_id, "asset_name": r.asset.asset_name, "category": r.asset.category,
            "qr_code": r.asset.qr_code, "status": r.asset.status, "location": location_out(r.asset.location),
        } if r.asset else None,
        "reporter": user_brief(r.reporter),
        "technician": {"technician_id": tech.technician_id, "full_name": tech.user.full_name,
                       "phone": tech.user.phone} if tech else None,
        "sla_policy": {"sla_id": r.sla.sla_id, "severity": r.sla.severity, "response_hours": r.sla.response_hours,
                       "resolution_hours": r.sla.resolution_hours} if r.sla else None,
        "sla": sla_snapshot(r, warn_pct),
        "rating": r.feedback.rating if r.feedback else None,
    }
