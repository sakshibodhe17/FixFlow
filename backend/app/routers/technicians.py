"""Technician roster, skills and availability."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Feedback, MaintenanceRequest, RepairLog, Skill, Technician, User
from ..schemas import TechnicianUpdate
from ..security import ADMIN, MANAGER, TECHNICIAN, require_roles
from ..services.audit import log_action
from ..services.serializers import technician_out

router = APIRouter(prefix="/api/technicians", tags=["Technicians"])


def _stats(db: Session, tech_ids: list[int]) -> dict[int, dict]:
    since = datetime.now(timezone.utc) - timedelta(days=30)
    resolved = dict(db.execute(
        select(MaintenanceRequest.assigned_to, func.count())
        .where(MaintenanceRequest.assigned_to.in_(tech_ids), MaintenanceRequest.resolved_at >= since)
        .group_by(MaintenanceRequest.assigned_to)).all())
    ratings = dict(db.execute(
        select(MaintenanceRequest.assigned_to, func.avg(Feedback.rating))
        .join(Feedback, Feedback.request_id == MaintenanceRequest.request_id)
        .where(MaintenanceRequest.assigned_to.in_(tech_ids))
        .group_by(MaintenanceRequest.assigned_to)).all())
    hours = dict(db.execute(
        select(RepairLog.technician_id, func.sum(RepairLog.labour_hours))
        .where(RepairLog.technician_id.in_(tech_ids), RepairLog.completed_at >= since)
        .group_by(RepairLog.technician_id)).all())
    return {t: {"resolved_30d": resolved.get(t, 0),
                "avg_rating": round(float(ratings[t]), 2) if ratings.get(t) is not None else None,
                "labour_hours_30d": round(float(hours.get(t) or 0), 1)} for t in tech_ids}


def _apply_update(db: Session, tech: Technician, body: TechnicianUpdate, actor: User) -> None:
    changes = {}
    if body.is_available is not None:
        tech.is_available = body.is_available
        changes["is_available"] = body.is_available
    if body.skill_ids is not None:
        skills = list(db.scalars(select(Skill).where(Skill.skill_id.in_(body.skill_ids))))
        if len(skills) != len(set(body.skill_ids)):
            raise HTTPException(400, "One or more skills don't exist.")
        tech.skills = skills
        changes["skills"] = [s.skill_name for s in skills]
    log_action(db, actor.user_id, "technician.updated", "technician", tech.technician_id, changes)


@router.get("")
def list_technicians(db: Session = Depends(get_db), _: User = Depends(require_roles(MANAGER, ADMIN))):
    techs = list(db.scalars(select(Technician).join(User)
                            .options(selectinload(Technician.user), selectinload(Technician.skills))
                            .where(User.role == "Technician").order_by(User.full_name)))
    stats = _stats(db, [t.technician_id for t in techs]) if techs else {}
    return [technician_out(t, {**stats.get(t.technician_id, {}), "is_active": t.user.is_active}) for t in techs]


@router.get("/me")
def my_profile(db: Session = Depends(get_db), user: User = Depends(require_roles(TECHNICIAN))):
    tech = user.technician
    if not tech:
        raise HTTPException(404, "No technician profile. Ask an administrator to set one up.")
    return technician_out(tech, _stats(db, [tech.technician_id])[tech.technician_id])


@router.put("/me")
def update_my_profile(body: TechnicianUpdate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(TECHNICIAN))):
    tech = user.technician
    if not tech:
        raise HTTPException(404, "No technician profile.")
    _apply_update(db, tech, body, user)
    db.commit()
    return technician_out(tech, _stats(db, [tech.technician_id])[tech.technician_id])


@router.put("/{technician_id}")
def update_technician(technician_id: int, body: TechnicianUpdate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles(MANAGER, ADMIN))):
    tech = db.get(Technician, technician_id)
    if not tech:
        raise HTTPException(404, "Technician not found")
    _apply_update(db, tech, body, user)
    db.commit()
    return technician_out(tech, _stats(db, [tech.technician_id])[tech.technician_id])
