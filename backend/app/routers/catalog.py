"""Administrator-managed catalogs: technician skill types and asset categories."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Asset, AssetCategory, Skill, User
from ..schemas import CategoryIn, SkillIn
from ..security import ADMIN, get_current_user, require_roles
from ..services.audit import log_action

router = APIRouter(prefix="/api", tags=["Skills & categories"])
admin_only = require_roles(ADMIN)


# ---- Skills -------------------------------------------------------------------
@router.get("/skills")
def list_skills(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [{"skill_id": s.skill_id, "skill_name": s.skill_name, "technician_count": len(s.technicians)}
            for s in db.scalars(select(Skill).order_by(Skill.skill_name))]


@router.post("/skills", status_code=201)
def create_skill(body: SkillIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    name = body.skill_name.strip()
    if db.scalar(select(Skill).where(func.lower(Skill.skill_name) == name.lower())):
        raise HTTPException(409, "That skill already exists.")
    s = Skill(skill_name=name)
    db.add(s)
    db.flush()
    log_action(db, user.user_id, "skill.created", "skill", s.skill_id, {"name": name})
    db.commit()
    return {"skill_id": s.skill_id, "skill_name": s.skill_name, "technician_count": 0}


@router.put("/skills/{skill_id}")
def rename_skill(skill_id: int, body: SkillIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    s = db.get(Skill, skill_id)
    if not s:
        raise HTTPException(404, "Skill not found")
    s.skill_name = body.skill_name.strip()
    log_action(db, user.user_id, "skill.renamed", "skill", s.skill_id, {"name": s.skill_name})
    db.commit()
    return {"skill_id": s.skill_id, "skill_name": s.skill_name, "technician_count": len(s.technicians)}


@router.delete("/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    s = db.get(Skill, skill_id)
    if not s:
        raise HTTPException(404, "Skill not found")
    db.delete(s)
    log_action(db, user.user_id, "skill.deleted", "skill", skill_id)
    db.commit()


# ---- Asset categories --------------------------------------------------------
def _cat_out(c: AssetCategory, count: int = 0) -> dict:
    return {"category_id": c.category_id, "name": c.name, "description": c.description,
            "skill_id": c.skill_id, "skill_name": c.skill.skill_name if c.skill else None, "asset_count": count}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    counts = dict(db.execute(select(Asset.category, func.count()).group_by(Asset.category)).all())
    return [_cat_out(c, counts.get(c.name, 0)) for c in db.scalars(select(AssetCategory).order_by(AssetCategory.name))]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    if db.scalar(select(AssetCategory).where(func.lower(AssetCategory.name) == body.name.lower())):
        raise HTTPException(409, "That category already exists.")
    if body.skill_id and not db.get(Skill, body.skill_id):
        raise HTTPException(400, "Unknown skill")
    c = AssetCategory(**body.model_dump())
    db.add(c)
    db.flush()
    log_action(db, user.user_id, "category.created", "category", c.category_id, body.model_dump())
    db.commit()
    db.refresh(c)
    return _cat_out(c)


@router.put("/categories/{category_id}")
def update_category(category_id: int, body: CategoryIn, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    c = db.get(AssetCategory, category_id)
    if not c:
        raise HTTPException(404, "Category not found")
    old_name = c.name
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    if old_name != c.name:  # keep assets pointing at the renamed category
        for a in db.scalars(select(Asset).where(Asset.category == old_name)):
            a.category = c.name
    log_action(db, user.user_id, "category.updated", "category", c.category_id, body.model_dump())
    db.commit()
    db.refresh(c)
    return _cat_out(c)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    c = db.get(AssetCategory, category_id)
    if not c:
        raise HTTPException(404, "Category not found")
    if db.scalar(select(func.count()).select_from(Asset).where(Asset.category == c.name)):
        raise HTTPException(409, "Assets still use this category. Recategorise them first.")
    db.delete(c)
    log_action(db, user.user_id, "category.deleted", "category", category_id)
    db.commit()
