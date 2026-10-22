"""Administration: notification/escalation settings, audit + system logs, usage, backup & restore."""
import json
import os
import re
import shutil
import subprocess
from collections import deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import Date, DateTime, Numeric, func, select, text
from sqlalchemy.orm import Session

from ..config import settings
from ..database import Base, engine, get_db
from ..models import AuditLog, MaintenanceRequest, User
from ..schemas import SettingsUpdate
from ..security import ADMIN, require_roles
from ..services.assignment import recount_workloads
from ..services.audit import log_action
from ..services.settings_store import all_settings, set_setting

router = APIRouter(prefix="/api/admin", tags=["Administration"])
admin_only = require_roles(ADMIN)
BACKUP_NAME = re.compile(r"^fixflow_\d{8}_\d{6}\.(sql|json)$")


# ---- Settings -----------------------------------------------------------------
@router.get("/settings")
def get_settings(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    return {"settings": all_settings(db), "smtp_enabled": settings.SMTP_ENABLED, "smtp_host": settings.SMTP_HOST,
            "sla_check_interval_minutes": settings.SLA_CHECK_INTERVAL_MINUTES}


@router.put("/settings")
def update_settings(body: SettingsUpdate, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    try:
        for k, v in body.values.items():
            set_setting(db, k, v)
    except KeyError as e:
        raise HTTPException(400, f"Unknown setting {e}")
    except ValueError as e:
        raise HTTPException(400, f"Invalid value: {e}")
    log_action(db, user.user_id, "settings.updated", "settings", None, body.values)
    db.commit()
    return {"settings": all_settings(db)}


# ---- Logs & usage -------------------------------------------------------------
@router.get("/audit-logs")
def audit_logs(action: str | None = None, user_id: int | None = None, limit: int = Query(200, le=1000),
               db: Session = Depends(get_db), _: User = Depends(admin_only)):
    stmt = (select(AuditLog, User.full_name).outerjoin(User, AuditLog.user_id == User.user_id)
            .order_by(AuditLog.created_at.desc()).limit(limit))
    if action:
        stmt = stmt.where(AuditLog.action.like(f"{action}%"))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return [{"log_id": a.log_id, "action": a.action, "entity": a.entity, "entity_id": a.entity_id,
             "details": a.details, "user": name or "System", "created_at": a.created_at}
            for a, name in db.execute(stmt).all()]


@router.get("/system-log")
def system_log(lines: int = Query(200, ge=10, le=2000), _: User = Depends(admin_only)):
    path = settings.LOG_DIR / "fixflow.log"
    if not path.exists():
        return {"lines": []}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return {"lines": list(deque(f, maxlen=lines))}


@router.get("/usage")
def usage(db: Session = Depends(get_db), _: User = Depends(admin_only)):
    now = datetime.now(timezone.utc)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    roles = dict(db.execute(select(User.role, func.count()).where(User.is_active.is_(True))
                            .group_by(User.role)).all())
    active_7d = db.scalar(select(func.count(func.distinct(AuditLog.user_id)))
                          .where(AuditLog.created_at >= d7, AuditLog.user_id.is_not(None)))
    logins = db.execute(
        select(func.date_trunc("day", AuditLog.created_at).label("d"), func.count())
        .where(AuditLog.action == "user.login", AuditLog.created_at >= d30).group_by("d").order_by("d")).all()
    requests = db.execute(
        select(func.date_trunc("day", MaintenanceRequest.reported_at).label("d"), func.count())
        .where(MaintenanceRequest.reported_at >= d30).group_by("d").order_by("d")).all()
    db_size = db.scalar(text("SELECT pg_size_pretty(pg_database_size(current_database()))"))
    from ..scheduler import jobs_status
    return {
        "users_by_role": roles, "active_users_7d": active_7d or 0,
        "logins_30d": [{"day": d.date().isoformat(), "count": c} for d, c in logins],
        "requests_30d": [{"day": d.date().isoformat(), "count": c} for d, c in requests],
        "database_size": db_size, "scheduler_jobs": jobs_status(),
    }


@router.post("/recount-workloads")
def recount(db: Session = Depends(get_db), user: User = Depends(admin_only)):
    changed = recount_workloads(db)
    log_action(db, user.user_id, "admin.recount_workloads", None, None, {"changed": changed})
    db.commit()
    return {"changed": changed}


# ---- Backup & restore ---------------------------------------------------------
def _pg_env() -> tuple[list[str], dict]:
    u = urlparse(settings.DATABASE_URL.replace("+psycopg2", ""))
    env = {**os.environ, "PGPASSWORD": u.password or ""}
    args = ["-h", u.hostname or "localhost", "-p", str(u.port or 5432), "-U", u.username or "postgres",
            "-d", (u.path or "/").lstrip("/")]
    return args, env


def _json_default(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    raise TypeError(type(v))


def _json_backup(path) -> None:
    data = {}
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            data[table.name] = [dict(r._mapping) for r in conn.execute(table.select())]
    path.write_text(json.dumps({"format": "fixflow-json-v1", "tables": data}, default=_json_default))


def _json_restore(path) -> None:
    payload = json.loads(path.read_text())
    tables = payload["tables"]
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
        for table in Base.metadata.sorted_tables:
            rows = tables.get(table.name, [])
            if not rows:
                continue
            for row in rows:  # convert JSON strings back to Python types
                for col in table.columns:
                    v = row.get(col.name)
                    if v is None:
                        continue
                    if isinstance(col.type, DateTime):
                        row[col.name] = datetime.fromisoformat(v)
                    elif isinstance(col.type, Date):
                        row[col.name] = date.fromisoformat(v)
                    elif isinstance(col.type, Numeric):
                        row[col.name] = Decimal(v)
            conn.execute(table.insert(), rows)
        # move SERIAL sequences past the restored ids
        for table in Base.metadata.sorted_tables:
            pk = list(table.primary_key.columns)
            if len(pk) == 1 and pk[0].autoincrement is not False and str(pk[0].type) == "INTEGER":
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table.name}', '{pk[0].name}'), "
                    f"COALESCE((SELECT MAX({pk[0].name}) FROM {table.name}), 0) + 1, false)"))


@router.post("/backups")
def create_backup(user: User = Depends(admin_only), db: Session = Depends(get_db)):
    """pg_dump if it's installed, otherwise a portable JSON export of every table."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if shutil.which(settings.PG_DUMP_PATH):
        path = settings.BACKUP_DIR / f"fixflow_{stamp}.sql"
        args, env = _pg_env()
        proc = subprocess.run([settings.PG_DUMP_PATH, *args, "--clean", "--if-exists", "--no-owner", "-f", str(path)],
                              env=env, capture_output=True, text=True, timeout=600)
        if proc.returncode != 0:
            raise HTTPException(500, f"pg_dump failed: {proc.stderr[:400]}")
        method = "pg_dump"
    else:
        path = settings.BACKUP_DIR / f"fixflow_{stamp}.json"
        _json_backup(path)
        method = "json"
    log_action(db, user.user_id, "admin.backup_created", None, None, {"file": path.name, "method": method})
    db.commit()
    return {"file": path.name, "method": method, "size_bytes": path.stat().st_size}


@router.get("/backups")
def list_backups(_: User = Depends(admin_only)):
    files = sorted(settings.BACKUP_DIR.glob("fixflow_*.*"), reverse=True)
    return [{"file": f.name, "size_bytes": f.stat().st_size,
             "created_at": datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)}
            for f in files if BACKUP_NAME.match(f.name)]


def _backup_path(name: str):
    if not BACKUP_NAME.match(name):
        raise HTTPException(400, "Invalid backup name")
    path = settings.BACKUP_DIR / name
    if not path.exists():
        raise HTTPException(404, "Backup not found")
    return path


@router.get("/backups/{name}")
def download_backup(name: str, _: User = Depends(admin_only)):
    path = _backup_path(name)
    return FileResponse(path, filename=name, media_type="application/octet-stream")


@router.post("/backups/{name}/restore")
def restore_backup(name: str, user: User = Depends(admin_only)):
    """Replaces ALL current data with the backup. The UI asks for confirmation first."""
    path = _backup_path(name)
    if path.suffix == ".sql":
        if not shutil.which(settings.PSQL_PATH):
            raise HTTPException(500, "psql is not installed on the server, so .sql backups can't be restored here.")
        args, env = _pg_env()
        proc = subprocess.run([settings.PSQL_PATH, *args, "-v", "ON_ERROR_STOP=1", "-f", str(path)],
                              env=env, capture_output=True, text=True, timeout=1200)
        if proc.returncode != 0:
            raise HTTPException(500, f"Restore failed: {proc.stderr[:400]}")
    else:
        _json_restore(path)
    from ..database import SessionLocal
    with SessionLocal() as db:
        # user_id is None: the admin's row may not exist in the restored data
        log_action(db, None, "admin.backup_restored", None, None, {"file": name, "by": user.email})
        db.commit()
    return {"restored": name}


@router.delete("/backups/{name}", status_code=204)
def delete_backup(name: str, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    _backup_path(name).unlink()
    log_action(db, user.user_id, "admin.backup_deleted", None, None, {"file": name})
    db.commit()
