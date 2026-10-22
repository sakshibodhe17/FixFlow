"""
Demo data: a college campus with ~60 assets, 5 technicians and 12 months of simulated
maintenance history (so analytics and the ML model have something real to learn from).

    python -m app.seed            # refuses if requests already exist
    python -m app.seed --reset    # DROPS ALL TABLES and rebuilds with demo data

Failures are simulated per asset per day. Each asset has a hidden "fragility" (older,
out-of-warranty, HVAC/appliances are more fragile) and failures make further failures
more likely for ~60 days — the pattern the model should pick up.
"""
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from .database import Base, SessionLocal, engine
from .init_db import ensure_reference_data
from .models import (
    Asset, AuditLog, Feedback, Location, MaintenanceRequest, Notification, RepairLog, SLAPolicy, Skill,
    Technician, User,
)
from .security import hash_password
from .services.assignment import recount_workloads
from .services.qr import new_qr_code

RNG = random.Random(42)
NOW = datetime.now(timezone.utc).replace(microsecond=0)

LOCATIONS = [
    ("Main Academic Block", "G", "G-01"), ("Main Academic Block", "1", "101"), ("Main Academic Block", "1", "104"),
    ("Main Academic Block", "2", "201"), ("Main Academic Block", "2", "204"), ("Main Academic Block", "3", "Seminar Hall"),
    ("Computer Lab Block", "1", "Lab 1"), ("Computer Lab Block", "1", "Lab 2"), ("Computer Lab Block", "2", "Server Room"),
    ("Library", "G", "Reading Hall"), ("Library", "1", "Digital Library"),
    ("Hostel A", "G", "Common Room"), ("Hostel A", "2", "Washroom 2"), ("Hostel A", "3", "Pantry"),
    ("Science Block", "1", "Chemistry Lab"), ("Science Block", "2", "Biology Lab"),
    ("Cafeteria", "G", "Kitchen"), ("Admin Building", "1", "Accounts Office"),
]

# category -> (asset name templates, typical issues, cost range INR, base fragility, severity weights L/M/H/C)
CATALOG = {
    "HVAC": (["Split AC 1.5T", "Split AC 2T", "Cassette AC", "Exhaust fan"],
             ["AC not cooling", "Water leaking from indoor unit", "Unusual noise from compressor", "AC trips breaker"],
             (800, 9000), 1.5, (2, 5, 3, 1)),
    "Electrical": (["Distribution board", "Ceiling fan", "Power socket bank", "UPS 5kVA"],
                   ["Sparking from socket", "Fan not working", "Frequent power trips", "UPS not holding charge"],
                   (300, 6000), 1.0, (2, 4, 3, 2)),
    "Lighting": (["LED panel set", "Tube light bank", "Corridor lights"],
                 ["Lights flickering", "Lights not turning on", "Burnt fitting"], (150, 1500), 0.8, (5, 4, 1, 0)),
    "Plumbing": (["Water cooler", "Wash basin taps", "Flush system", "RO purifier"],
                 ["Leaking tap", "Blocked drain", "No water flow", "Water cooler not cooling"],
                 (200, 4000), 1.1, (3, 5, 2, 0)),
    "IT Equipment": (["Desktop PC", "Projector", "Network switch", "Smart board", "Printer"],
                     ["Won't power on", "No network connectivity", "Projector display dim", "Paper jam / not printing"],
                     (300, 12000), 0.9, (2, 5, 3, 1)),
    "Furniture": (["Lecture benches", "Office chairs", "Library shelves"],
                  ["Broken bench", "Chair wheel broken", "Shelf loose"], (100, 2500), 0.5, (6, 3, 1, 0)),
    "Appliances": (["Geyser", "Refrigerator", "Microwave oven", "Commercial mixer"],
                   ["Not heating", "Not cooling", "Tripping power", "Motor making noise"],
                   (500, 7000), 1.4, (2, 5, 2, 1)),
    "Lab Equipment": (["Fume hood", "Centrifuge", "Microscope", "Hot air oven"],
                      ["Fan not exhausting", "Rotor imbalance", "Light source failed", "Temperature unstable"],
                      (1000, 15000), 1.0, (1, 4, 4, 1)),
}
LOCATION_CATEGORIES = {
    "Main Academic Block": ["HVAC", "Electrical", "Lighting", "IT Equipment", "Furniture"],
    "Computer Lab Block": ["IT Equipment", "HVAC", "Electrical"],
    "Library": ["Lighting", "HVAC", "Furniture", "IT Equipment"],
    "Hostel A": ["Plumbing", "Appliances", "Electrical", "Lighting"],
    "Science Block": ["Lab Equipment", "Plumbing", "Electrical"],
    "Cafeteria": ["Appliances", "Plumbing", "Electrical"],
    "Admin Building": ["IT Equipment", "HVAC", "Furniture"],
}
TECHS = [
    ("Ravi Patil", "ravi@fixflow.dev", ["Electrical", "HVAC"]),
    ("Priya Kulkarni", "priya@fixflow.dev", ["IT & Networking", "Electrical"]),
    ("Amit Deshmukh", "amit@fixflow.dev", ["Plumbing", "Carpentry"]),
    ("Sneha Joshi", "sneha@fixflow.dev", ["Appliances", "HVAC", "Lab Equipment"]),
    ("Karan Shinde", "karan@fixflow.dev", ["Carpentry", "Electrical", "Plumbing"]),
]
REPORTERS = [
    ("Sakshi Bodhe", "student@fixflow.dev"), ("Rohan Mehta", "rohan@fixflow.dev"),
    ("Ananya Rao", "ananya@fixflow.dev"), ("Dr. Meera Iyer", "meera@fixflow.dev"),
]
COMMENTS = {5: ["Fixed quickly, thanks!", "Very professional.", "Works perfectly now."],
            4: ["Good job.", "Fixed, took a little while.", ""],
            3: ["Okay, but took longer than expected.", "Fixed after a second visit."],
            2: ["Problem came back after a day.", "Slow response."], 1: ["Still not working properly."]}


def _audit(db, user_id, action, req_id, at, details=None):
    db.add(AuditLog(user_id=user_id, action=action, entity="request", entity_id=req_id,
                    details=json.dumps(details) if details else None, created_at=at))


def reset_schema() -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def seed() -> None:
    with SessionLocal() as db:
        ensure_reference_data(db)
        if db.scalar(select(func.count()).select_from(MaintenanceRequest)):
            print("Requests already exist. Run with --reset to rebuild the demo data.")
            return
        skills = {s.skill_name: s for s in db.scalars(select(Skill))}
        sla = {p.severity: p for p in db.scalars(select(SLAPolicy))}
        cat_skill = {"HVAC": "HVAC", "Electrical": "Electrical", "Lighting": "Electrical", "Plumbing": "Plumbing",
                     "IT Equipment": "IT & Networking", "Furniture": "Carpentry", "Appliances": "Appliances",
                     "Lab Equipment": "Lab Equipment"}

        # ---- people ----
        start_users = NOW - timedelta(days=400)
        manager = User(full_name="Facility Manager", email="manager@fixflow.dev", phone="9876500001",
                       password_hash=hash_password("Manager@123"), role="Manager", created_at=start_users)
        db.add(manager)
        techs = []
        for i, (name, email, sk) in enumerate(TECHS):
            u = User(full_name=name, email=email, phone=f"98765100{i:02d}", role="Technician",
                     password_hash=hash_password("Tech@123"), created_at=start_users)
            db.add(u)
            db.flush()
            t = Technician(user_id=u.user_id, is_available=True, skills=[skills[s] for s in sk])
            db.add(t)
            techs.append(t)
        reporters = []
        for i, (name, email) in enumerate(REPORTERS):
            u = User(full_name=name, email=email, phone=f"98765200{i:02d}", role="Reporter",
                     password_hash=hash_password("Reporter@123"), created_at=start_users)
            db.add(u)
            reporters.append(u)
        db.flush()

        # ---- locations & assets ----
        locs = []
        for b, f, r in LOCATIONS:
            loc = Location(building=b, floor=f, room=r)
            db.add(loc)
            locs.append(loc)
        db.flush()
        assets, fragility = [], {}
        for loc in locs:
            for cat in RNG.sample(LOCATION_CATEGORIES[loc.building], k=min(4, len(LOCATION_CATEGORIES[loc.building]))):
                names, _, _, base, _ = CATALOG[cat]
                age_days = RNG.randint(150, 3200)
                purchased = (NOW - timedelta(days=age_days)).date()
                warranty_years = RNG.choice([1, 2, 3, 5])
                a = Asset(location_id=loc.location_id, category=cat, qr_code=new_qr_code(db),
                          asset_name=f"{RNG.choice(names)} – {loc.room}", purchase_date=purchased,
                          warranty_expiry=purchased + timedelta(days=365 * warranty_years), status="Working",
                          created_at=NOW - timedelta(days=380))
                db.add(a)
                db.flush()
                assets.append(a)
                out_of_warranty = a.warranty_expiry < NOW.date()
                fragility[a.asset_id] = base * (0.5 + age_days / 2400) * (1.3 if out_of_warranty else 0.8) \
                    * RNG.lognormvariate(0, 0.45)
        print(f"Created {len(assets)} assets in {len(locs)} locations")

        # ---- simulate 365 days of failures ----
        events = []
        for a in assets:
            recent: list[datetime] = []
            for d in range(365, 0, -1):
                day = NOW - timedelta(days=d)
                boost = 1 + 1.4 * sum(1 for x in recent if (day - x).days < 60)
                if RNG.random() < 0.0028 * fragility[a.asset_id] * boost:
                    t = day.replace(hour=RNG.randint(8, 19), minute=RNG.randint(0, 59), second=0)
                    if t < NOW:
                        recent.append(t)
                        events.append((t, a))
        events.sort(key=lambda e: e[0])
        print(f"Simulating {len(events)} maintenance requests")

        tech_by_skill = {s: [t for t in techs if any(sk.skill_name == s for sk in t.skills)] for s in skills}
        for t_reported, a in events:
            _, issues, (cmin, cmax), _, weights = CATALOG[a.category]
            severity = RNG.choices(["Low", "Medium", "High", "Critical"], weights=weights)[0]
            pol = sla[severity]
            reporter = RNG.choice(reporters + [manager]) if RNG.random() < 0.1 else RNG.choice(reporters)
            tech = RNG.choice(tech_by_skill.get(cat_skill[a.category]) or techs)
            title = RNG.choice(issues)
            req = MaintenanceRequest(asset_id=a.asset_id, reported_by=reporter.user_id, sla_id=pol.sla_id,
                                     title=title, severity=severity,
                                     description=f"{title}. Noticed in {a.location.room}. Please check.",
                                     reported_at=t_reported,
                                     resolution_due=t_reported + timedelta(hours=pol.resolution_hours))
            db.add(req)
            db.flush()
            _audit(db, reporter.user_id, "request.created", req.request_id, t_reported,
                   {"severity": severity, "asset": a.asset_name})

            assigned = t_reported + timedelta(minutes=RNG.randint(1, 5))
            req.assigned_to, req.assigned_at, req.status = tech.technician_id, assigned, "Assigned"
            _audit(db, None, "request.assigned", req.request_id, assigned,
                   {"technician": tech.user.full_name, "mode": "auto"})

            accepted = assigned + timedelta(hours=pol.response_hours * RNG.uniform(0.1, 1.2))
            # most jobs finish inside the SLA, ~15 % overrun
            frac = RNG.uniform(0.15, 0.9) if RNG.random() > 0.15 else RNG.uniform(1.05, 2.2)
            resolved = t_reported + timedelta(hours=pol.resolution_hours * frac)
            started = accepted + (resolved - accepted) * RNG.uniform(0.1, 0.6)

            if accepted > NOW:  # brand-new: still waiting
                if RNG.random() < 0.15:
                    req.status, req.assigned_to, req.assigned_at = "Open", None, None
                continue
            req.accepted_at = accepted
            _audit(db, tech.user_id, "request.accepted", req.request_id, accepted)
            if started > NOW:
                continue
            _audit(db, tech.user_id, "request.started", req.request_id, started)
            if resolved > NOW:  # work in progress
                req.status = RNG.choice(["In Progress", "In Progress", "On Hold"])
                if req.status == "In Progress":
                    req.work_started_at = started
                else:
                    req.work_seconds = int((NOW - started).total_seconds() * 0.4)
                continue

            labour = round(max(0.5, (resolved - started).total_seconds() / 3600 * RNG.uniform(0.3, 0.8)), 2)
            labour = min(labour, 40)
            cost = round(RNG.uniform(cmin, cmax) * (1.4 if severity in ("High", "Critical") else 1), 2)
            downtime = round((resolved - t_reported).total_seconds() / 3600, 2)
            db.add(RepairLog(request_id=req.request_id, technician_id=tech.technician_id,
                             work_notes=f"Diagnosed: {title.lower()}. Repaired and tested.",
                             parts_used=RNG.choice(["", "Capacitor", "Fuse, wiring", "Gasket", "Filter",
                                                    "Power supply", "Bearings", "Washer set"]) or None,
                             labour_hours=Decimal(str(labour)), repair_cost=Decimal(str(cost)),
                             downtime_hours=Decimal(str(min(downtime, 9999))), completed_at=resolved))
            req.status, req.resolved_at, req.work_seconds = "Resolved", resolved, int(labour * 3600)
            _audit(db, tech.user_id, "request.resolved", req.request_id, resolved,
                   {"labour_hours": labour, "repair_cost": cost})

            if NOW - resolved > timedelta(hours=36):
                req.status, req.closed_at = "Closed", resolved + timedelta(hours=RNG.randint(2, 30))
                if RNG.random() < 0.72:
                    on_time = resolved <= req.resolution_due
                    rating = RNG.choices([5, 4, 3, 2, 1], weights=[5, 4, 1, 0.3, 0.1] if on_time else [1, 2, 3, 2, 1])[0]
                    db.add(Feedback(request_id=req.request_id, user_id=reporter.user_id, rating=rating,
                                    comment=RNG.choice(COMMENTS[rating]) or None, created_at=req.closed_at))
                    _audit(db, reporter.user_id, "request.rated", req.request_id, req.closed_at, {"rating": rating})

        db.flush()
        # a couple of reopened requests for the demo
        for req in db.scalars(select(MaintenanceRequest).where(MaintenanceRequest.status == "Resolved").limit(2)):
            reopened_at = NOW - timedelta(hours=2)
            req.resolved_at, req.reopen_count, req.accepted_at = None, 1, None
            req.resolution_due = reopened_at + timedelta(hours=req.sla.resolution_hours)
            req.status, req.assigned_at = "Assigned", reopened_at  # reopen → engine re-assigns
            _audit(db, req.reported_by, "request.reopened", req.request_id, reopened_at,
                   {"reason": "The problem came back the next morning."})
            _audit(db, None, "request.assigned", req.request_id, reopened_at,
                   {"technician": req.technician.user.full_name, "mode": "reopen"})

        # asset status from open work
        for a in assets:
            states = [r.status for r in a.requests if r.status not in ("Resolved", "Closed")]
            a.status = "Under Repair" if "In Progress" in states else "Faulty" if states else "Working"

        db.flush()  # autoflush is off; make status changes visible to the recount query
        recount_workloads(db)
        student = reporters[0]
        db.add(Notification(user_id=student.user_id, title="Welcome to FixFlow",
                            message="Report a problem by scanning the QR sticker on any asset.", link="/report"))
        db.commit()
        print(f"Seeded {db.scalar(select(func.count()).select_from(MaintenanceRequest))} requests")

    # ---- train the model and score assets ----
    from . import ml_engine
    with SessionLocal() as db:
        try:
            info = ml_engine.train_model(db)
            print(f"Model {info['version']} trained: {info['metrics']}")
        except ml_engine.InsufficientDataError as e:
            print(f"Model not trained: {e}")
        print("Predictions:", ml_engine.predict_all(db, notify_new_high=False))

    print("\nDemo accounts (email / password):")
    print("  admin@fixflow.dev    / Admin@123     (Admin)")
    print("  manager@fixflow.dev  / Manager@123   (Facility Manager)")
    print("  ravi@fixflow.dev     / Tech@123      (Technician; also priya, amit, sneha, karan)")
    print("  student@fixflow.dev  / Reporter@123  (Reporter)")


if __name__ == "__main__":
    if "--reset" in sys.argv:
        print("Dropping and recreating all tables…")
        reset_schema()
    seed()
