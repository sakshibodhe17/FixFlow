"""
Analytics for managers: open-request metrics, SLA compliance, technician performance,
recurring faults, and repair cost / downtime trends.

Aggregation is done in Python over filtered rows — simple to read and fast enough for
tens of thousands of requests. Move hot paths to SQL GROUP BY if data grows further.
"""
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import (
    UNRESOLVED_STATUSES, Asset, Escalation, Feedback, MaintenanceRequest, RepairLog, Technician, User,
)
from ..security import ADMIN, MANAGER, require_roles
from .assets import latest_predictions

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])
staff_only = require_roles(MANAGER, ADMIN)


def _now():
    return datetime.now(timezone.utc)


def _hours(a, b):
    return (b - a).total_seconds() / 3600


def _requests_since(db: Session, since: datetime) -> list[MaintenanceRequest]:
    return list(db.scalars(
        select(MaintenanceRequest)
        .options(selectinload(MaintenanceRequest.asset).selectinload(Asset.location),
                 selectinload(MaintenanceRequest.repair_logs), selectinload(MaintenanceRequest.feedback))
        .where(MaintenanceRequest.reported_at >= since)))


def _compliance(reqs) -> float | None:
    done = [r for r in reqs if r.resolved_at and r.resolution_due]
    if not done:
        return None
    return round(100 * sum(r.resolved_at <= r.resolution_due for r in done) / len(done), 1)


@router.get("/overview")
def overview(days: int = Query(30, ge=1, le=730), db: Session = Depends(get_db), _: User = Depends(staff_only)):
    now = _now()
    since = now - timedelta(days=days)
    status_counts = dict(db.execute(select(MaintenanceRequest.status, func.count())
                                    .group_by(MaintenanceRequest.status)).all())
    open_count = sum(status_counts.get(s, 0) for s in UNRESOLVED_STATUSES)
    overdue = db.scalar(select(func.count()).select_from(MaintenanceRequest).where(
        MaintenanceRequest.status.in_(UNRESOLVED_STATUSES), MaintenanceRequest.resolution_due < now)) or 0
    unassigned = db.scalar(select(func.count()).select_from(MaintenanceRequest).where(
        MaintenanceRequest.status.in_(("Open", "Reopened")), MaintenanceRequest.assigned_to.is_(None))) or 0

    window = _requests_since(db, since)
    resolved_window = list(db.scalars(select(MaintenanceRequest).where(MaintenanceRequest.resolved_at >= since)))
    res_times = [_hours(r.reported_at, r.resolved_at) for r in resolved_window]
    logs = list(db.scalars(select(RepairLog).where(RepairLog.completed_at >= since)))
    ratings = [f.rating for f in db.scalars(select(Feedback).where(Feedback.created_at >= since))]
    preds = latest_predictions(db)
    esc_open = db.scalar(select(func.count(func.distinct(Escalation.request_id)))
                         .where(Escalation.is_acknowledged.is_(False))) or 0

    return {
        "days": days,
        "open_requests": open_count,
        "overdue_requests": overdue,
        "unassigned_requests": unassigned,
        "new_requests": len(window),
        "resolved_requests": len(resolved_window),
        "status_counts": status_counts,
        "severity_counts": dict(Counter(r.severity for r in window)),
        "sla_compliance_pct": _compliance(resolved_window),
        "avg_resolution_hours": round(mean(res_times), 1) if res_times else None,
        "total_repair_cost": round(sum(float(l.repair_cost or 0) for l in logs), 2),
        "total_downtime_hours": round(sum(float(l.downtime_hours or 0) for l in logs), 1),
        "total_labour_hours": round(sum(float(l.labour_hours or 0) for l in logs), 1),
        "avg_rating": round(mean(ratings), 2) if ratings else None,
        "ratings_count": len(ratings),
        "high_risk_assets": sum(1 for p in preds.values() if p.risk_level == "High"),
        "unacknowledged_escalations": esc_open,
    }


@router.get("/trends")
def trends(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db), _: User = Depends(staff_only)):
    """Monthly requests, resolutions, cost, downtime and SLA compliance."""
    now = _now()
    first = (now.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    keys = []
    d = first
    while d <= now:
        keys.append(d.strftime("%Y-%m"))
        d = (d + timedelta(days=32)).replace(day=1)
    buckets = {k: {"month": k, "requests": 0, "resolved": 0, "repair_cost": 0.0, "downtime_hours": 0.0,
                   "labour_hours": 0.0, "_met": 0, "_due": 0, "preventive": 0} for k in keys}

    for r in db.scalars(select(MaintenanceRequest).where(MaintenanceRequest.reported_at >= first)):
        b = buckets.get(r.reported_at.strftime("%Y-%m"))
        if b:
            b["requests"] += 1
            b["preventive"] += int(r.is_preventive)
    for r in db.scalars(select(MaintenanceRequest).where(MaintenanceRequest.resolved_at >= first)):
        b = buckets.get(r.resolved_at.strftime("%Y-%m"))
        if b:
            b["resolved"] += 1
            if r.resolution_due:
                b["_due"] += 1
                b["_met"] += int(r.resolved_at <= r.resolution_due)
    for l in db.scalars(select(RepairLog).where(RepairLog.completed_at >= first)):
        b = buckets.get(l.completed_at.strftime("%Y-%m"))
        if b:
            b["repair_cost"] += float(l.repair_cost or 0)
            b["downtime_hours"] += float(l.downtime_hours or 0)
            b["labour_hours"] += float(l.labour_hours or 0)

    out = []
    for k in keys:
        b = buckets[k]
        b["sla_compliance_pct"] = round(100 * b["_met"] / b["_due"], 1) if b["_due"] else None
        b["repair_cost"] = round(b["repair_cost"], 2)
        b["downtime_hours"] = round(b["downtime_hours"], 1)
        b["labour_hours"] = round(b["labour_hours"], 1)
        b["label"] = datetime.strptime(k, "%Y-%m").strftime("%b %y")
        del b["_met"], b["_due"]
        out.append(b)
    return out


@router.get("/technicians")
def technician_performance(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db),
                           _: User = Depends(staff_only)):
    since = _now() - timedelta(days=days)
    techs = list(db.scalars(select(Technician).join(User).options(selectinload(Technician.user))
                            .where(User.role == "Technician")))
    reqs = list(db.scalars(select(MaintenanceRequest).options(selectinload(MaintenanceRequest.feedback))
                           .where(MaintenanceRequest.assigned_to.is_not(None),
                                  MaintenanceRequest.reported_at >= since)))
    logs = list(db.scalars(select(RepairLog).where(RepairLog.completed_at >= since)))
    by_tech = defaultdict(list)
    for r in reqs:
        by_tech[r.assigned_to].append(r)
    labour = defaultdict(float)
    cost = defaultdict(float)
    for l in logs:
        labour[l.technician_id] += float(l.labour_hours or 0)
        cost[l.technician_id] += float(l.repair_cost or 0)

    out = []
    for t in techs:
        rs = by_tech.get(t.technician_id, [])
        resolved = [r for r in rs if r.resolved_at]
        times = [_hours(r.reported_at, r.resolved_at) for r in resolved]
        ratings = [r.feedback.rating for r in rs if r.feedback]
        out.append({
            "technician_id": t.technician_id, "full_name": t.user.full_name, "is_available": t.is_available,
            "current_workload": t.current_workload, "assigned": len(rs), "resolved": len(resolved),
            "reopened": sum(1 for r in rs if r.reopen_count),
            "avg_resolution_hours": round(mean(times), 1) if times else None,
            "sla_compliance_pct": _compliance(resolved),
            "avg_rating": round(mean(ratings), 2) if ratings else None,
            "labour_hours": round(labour[t.technician_id], 1),
            "repair_cost": round(cost[t.technician_id], 2),
        })
    out.sort(key=lambda x: -x["resolved"])
    return out


@router.get("/recurring-faults")
def recurring_faults(days: int = Query(180, ge=7, le=730), min_count: int = Query(3, ge=2),
                     db: Session = Depends(get_db), _: User = Depends(staff_only)):
    """Assets, categories and locations that keep failing."""
    reqs = [r for r in _requests_since(db, _now() - timedelta(days=days)) if not r.is_preventive]
    by_asset: dict[int, dict] = {}
    by_cat: dict[str, dict] = defaultdict(lambda: {"count": 0, "cost": 0.0, "downtime": 0.0})
    by_loc: dict[str, dict] = defaultdict(lambda: {"count": 0, "cost": 0.0})
    for r in reqs:
        cost = sum(float(l.repair_cost or 0) for l in r.repair_logs)
        down = sum(float(l.downtime_hours or 0) for l in r.repair_logs)
        a = r.asset
        e = by_asset.setdefault(a.asset_id, {
            "asset_id": a.asset_id, "asset_name": a.asset_name, "category": a.category,
            "location": a.location.label if a.location else None, "count": 0, "cost": 0.0,
            "downtime_hours": 0.0, "last_reported": r.reported_at, "titles": Counter()})
        e["count"] += 1
        e["cost"] += cost
        e["downtime_hours"] += down
        e["last_reported"] = max(e["last_reported"], r.reported_at)
        e["titles"][r.title.lower()] += 1
        by_cat[a.category]["count"] += 1
        by_cat[a.category]["cost"] += cost
        by_cat[a.category]["downtime"] += down
        building = a.location.building if a.location else "Unassigned"
        by_loc[building]["count"] += 1
        by_loc[building]["cost"] += cost

    assets = sorted(by_asset.values(), key=lambda x: (-x["count"], -x["cost"]))
    for e in assets:
        e["most_common_issue"] = e.pop("titles").most_common(1)[0][0]
        e["cost"] = round(e["cost"], 2)
        e["downtime_hours"] = round(e["downtime_hours"], 1)
        e["is_recurring"] = e["count"] >= min_count
    return {
        "days": days, "min_count": min_count,
        "assets": assets[:20],
        "categories": sorted([{"category": k, "count": v["count"], "cost": round(v["cost"], 2),
                               "downtime_hours": round(v["downtime"], 1)} for k, v in by_cat.items()],
                             key=lambda x: -x["count"]),
        "locations": sorted([{"building": k, "count": v["count"], "cost": round(v["cost"], 2)}
                             for k, v in by_loc.items()], key=lambda x: -x["count"]),
    }


@router.get("/sla")
def sla_breakdown(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db), _: User = Depends(staff_only)):
    since = _now() - timedelta(days=days)
    resolved = list(db.scalars(select(MaintenanceRequest).where(MaintenanceRequest.resolved_at >= since)))
    out = []
    for sev in ("Critical", "High", "Medium", "Low"):
        rs = [r for r in resolved if r.severity == sev]
        times = [_hours(r.reported_at, r.resolved_at) for r in rs]
        out.append({"severity": sev, "resolved": len(rs), "compliance_pct": _compliance(rs),
                    "avg_resolution_hours": round(mean(times), 1) if times else None})
    return out


@router.get("/risk-distribution")
def risk_distribution(db: Session = Depends(get_db), _: User = Depends(staff_only)):
    preds = latest_predictions(db)
    counts = Counter(p.risk_level for p in preds.values())
    buckets = [0] * 10
    for p in preds.values():
        buckets[min(int(float(p.risk_score) * 10), 9)] += 1
    return {"levels": [{"level": l, "count": counts.get(l, 0)} for l in ("Low", "Medium", "High")],
            "histogram": [{"range": f"{i*10}-{i*10+10}%", "count": c} for i, c in enumerate(buckets)]}
