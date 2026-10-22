"""
Create tables (if Alembic hasn't) and insert required reference data:
SLA policies, default skills/categories, system settings and the first admin.

    python -m app.init_db
"""
from sqlalchemy import select

from .config import settings
from .database import Base, SessionLocal, engine
from .models import AssetCategory, SLAPolicy, Skill, User
from .security import hash_password

DEFAULT_SLA = {"Critical": (1, 8), "High": (4, 24), "Medium": (8, 72), "Low": (24, 168)}
DEFAULT_SKILLS = ["Electrical", "Plumbing", "HVAC", "IT & Networking", "Carpentry", "Appliances", "Lab Equipment"]
DEFAULT_CATEGORIES = {
    "Electrical": "Electrical", "Lighting": "Electrical", "Plumbing": "Plumbing", "HVAC": "HVAC",
    "IT Equipment": "IT & Networking", "Furniture": "Carpentry", "Appliances": "Appliances",
    "Lab Equipment": "Lab Equipment",
}


def ensure_reference_data(db) -> None:
    for sev, (resp, res) in DEFAULT_SLA.items():
        if not db.scalar(select(SLAPolicy).where(SLAPolicy.severity == sev)):
            db.add(SLAPolicy(severity=sev, response_hours=resp, resolution_hours=res))
    skills = {s.skill_name: s for s in db.scalars(select(Skill))}
    for name in DEFAULT_SKILLS:
        if name not in skills:
            skills[name] = Skill(skill_name=name)
            db.add(skills[name])
    db.flush()
    for cat, skill in DEFAULT_CATEGORIES.items():
        if not db.scalar(select(AssetCategory).where(AssetCategory.name == cat)):
            db.add(AssetCategory(name=cat, skill_id=skills[skill].skill_id))
    if not db.scalar(select(User).where(User.role == "Admin")):
        db.add(User(full_name="System Administrator", email=settings.ADMIN_EMAIL.lower(),
                    password_hash=hash_password(settings.ADMIN_PASSWORD), role="Admin"))
    db.commit()


def main() -> None:
    Base.metadata.create_all(engine)  # no-op for tables Alembic already created
    with SessionLocal() as db:
        ensure_reference_data(db)
    print(f"Database ready. Admin login: {settings.ADMIN_EMAIL} / (ADMIN_PASSWORD from .env)")


if __name__ == "__main__":
    main()
