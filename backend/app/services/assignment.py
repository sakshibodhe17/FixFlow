"""
Automated technician assignment engine.

Matching rule (from the spec): skill match → availability → lowest current workload.
1. The asset's category is mapped to a required skill (asset_categories.skill_id, or a
   skill with the same name as the category).
2. Candidates = active, available technicians who have that skill.
3. Pick the one with the lowest current_workload (ties broken by technician_id).
If nobody matches, the request stays Open and managers are told it needs manual assignment.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ACTIVE_STATUSES, Asset, AssetCategory, MaintenanceRequest, Skill, Technician, User
from .audit import log_action
from .notify import notify, notify_roles


def required_skill(db: Session, asset: Asset) -> Skill | None:
    cat = db.scalar(select(AssetCategory).where(func.lower(AssetCategory.name) == asset.category.lower()))
    if cat and cat.skill:
        return cat.skill
    return db.scalar(select(Skill).where(func.lower(Skill.skill_name) == asset.category.lower()))


def candidate_technicians(db: Session, skill: Skill | None, only_available: bool = True) -> list[Technician]:
    q = select(Technician).join(User, Technician.user_id == User.user_id).where(
        User.is_active.is_(True), User.role == "Technician"
    )
    if only_available:
        q = q.where(Technician.is_available.is_(True))
    if skill is not None:
        q = q.where(Technician.skills.any(Skill.skill_id == skill.skill_id))
    q = q.order_by(Technician.current_workload.asc(), Technician.technician_id.asc())
    return list(db.scalars(q))


def _release(db: Session, req: MaintenanceRequest) -> None:
    """Remove the request from its current technician's workload."""
    if req.assigned_to and req.status in ACTIVE_STATUSES:
        old = db.get(Technician, req.assigned_to)
        if old:
            old.current_workload = max(0, (old.current_workload or 0) - 1)


def assign_request(db: Session, req: MaintenanceRequest, tech: Technician, actor_id: int | None,
                   reason: str = "auto") -> None:
    now = datetime.now(timezone.utc)
    if req.work_started_at:  # stop a running timer before handing over
        req.work_seconds = (req.work_seconds or 0) + int((now - req.work_started_at).total_seconds())
        req.work_started_at = None
    _release(db, req)
    req.assigned_to = tech.technician_id
    req.status = "Assigned"
    req.assigned_at = now
    req.accepted_at = None
    tech.current_workload = (tech.current_workload or 0) + 1

    log_action(db, actor_id, "request.assigned", "request", req.request_id,
               {"technician_id": tech.technician_id, "technician": tech.user.full_name, "mode": reason})
    notify(db, tech.user, f"New job #{req.request_id}: {req.title}",
           f"{req.severity} severity · {req.asset.asset_name}. Resolution due {req.resolution_due:%d %b %Y %H:%M} UTC.",
           link=f"/requests/{req.request_id}")
    notify(db, req.reporter, f"Request #{req.request_id} assigned",
           f"{tech.user.full_name} has been assigned to your request \"{req.title}\".",
           link=f"/requests/{req.request_id}", email=False)


def auto_assign(db: Session, req: MaintenanceRequest, actor_id: int | None = None) -> Technician | None:
    skill = required_skill(db, req.asset)
    candidates = candidate_technicians(db, skill)
    if not candidates:
        log_action(db, actor_id, "request.assign_failed", "request", req.request_id,
                   {"required_skill": skill.skill_name if skill else None})
        notify_roles(db, ("Manager",), f"Request #{req.request_id} needs manual assignment",
                     f"No available technician has the "
                     f"{skill.skill_name if skill else req.asset.category} skill for \"{req.title}\".",
                     link=f"/requests/{req.request_id}")
        return None
    tech = candidates[0]
    assign_request(db, req, tech, actor_id, reason="auto")
    return tech


def recount_workloads(db: Session) -> int:
    """Rebuild current_workload from actual open assignments (nightly safety net)."""
    counts = dict(db.execute(
        select(MaintenanceRequest.assigned_to, func.count())
        .where(MaintenanceRequest.status.in_(ACTIVE_STATUSES), MaintenanceRequest.assigned_to.is_not(None))
        .group_by(MaintenanceRequest.assigned_to)
    ).all())
    changed = 0
    for t in db.scalars(select(Technician)):
        new = counts.get(t.technician_id, 0)
        if t.current_workload != new:
            t.current_workload = new
            changed += 1
    return changed
