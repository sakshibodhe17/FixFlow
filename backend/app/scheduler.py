"""
Background jobs (APScheduler, runs inside the API process).

  sla_check          every SLA_CHECK_INTERVAL_MINUTES
      Response breach : still unaccepted after SLA response_hours
      Warning         : sla_warning_pct % of the resolution window has elapsed
      Breach          : resolution_due has passed
    Each level is escalated once per SLA window: an Escalation row per manager
    (and admin, if configured) + in-app and email notifications.
  nightly_predictions 02:00 UTC — score every asset
  weekly_retrain      Sunday 03:00 UTC — retrain the failure model
  workload_recount    hourly — rebuild technician workload counters

If you run several API workers (e.g. `uvicorn --workers 4`), set SCHEDULER_ENABLED=false
on all but one, or run `python -m app.scheduler` as a separate process.
"""
import logging
import time
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from .config import settings
from .database import SessionLocal
from .models import UNRESOLVED_STATUSES, Escalation, MaintenanceRequest, Technician
from .services.assignment import recount_workloads
from .services.audit import log_action
from .services.notify import notify, users_with_roles
from .services.settings_store import get_setting
from .services.sla import response_due, sla_window_start

log = logging.getLogger("fixflow.scheduler")
scheduler = BackgroundScheduler(timezone="UTC")


def _already_escalated(db, req: MaintenanceRequest, level: str) -> bool:
    window_start = sla_window_start(req)
    return db.scalar(select(Escalation.escalation_id).where(
        Escalation.request_id == req.request_id, Escalation.level == level,
        Escalation.escalated_at >= window_start).limit(1)) is not None


def _escalate(db, req: MaintenanceRequest, level: str, reason: str) -> None:
    roles = ("Manager", "Admin") if get_setting(db, "escalate_to_admins") else ("Manager",)
    recipients = users_with_roles(db, *roles)
    if not recipients:
        log.warning("No managers to escalate request #%s to", req.request_id)
        return
    for u in recipients:
        db.add(Escalation(request_id=req.request_id, escalated_to=u.user_id, reason=reason[:255], level=level))
        notify(db, u, f"SLA {level.lower()}: #{req.request_id} {req.title}", reason,
               link=f"/requests/{req.request_id}")
    if level == "Breach" and req.technician:
        notify(db, req.technician.user, f"SLA breached on #{req.request_id}",
               "This job is past its resolution deadline. Update its status or log progress.",
               link=f"/requests/{req.request_id}")
    log_action(db, None, f"sla.{level.lower()}", "request", req.request_id, {"reason": reason})


def check_sla_deadlines() -> dict:
    """One pass over every unresolved request. Safe to run any time (idempotent)."""
    started = time.monotonic()
    result = {"checked": 0, "warnings": 0, "breaches": 0, "response_breaches": 0}
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        warn_pct = get_setting(db, "sla_warning_pct")
        reqs = db.scalars(
            select(MaintenanceRequest)
            .options(selectinload(MaintenanceRequest.sla), selectinload(MaintenanceRequest.asset),
                     selectinload(MaintenanceRequest.technician).selectinload(Technician.user))
            .where(MaintenanceRequest.status.in_(UNRESOLVED_STATUSES),
                   MaintenanceRequest.resolution_due.is_not(None))
        ).all()
        for req in reqs:
            result["checked"] += 1
            due = req.resolution_due
            start = sla_window_start(req)
            elapsed_pct = (now - start).total_seconds() / max((due - start).total_seconds(), 1) * 100
            who = req.technician.user.full_name if req.technician else "nobody (unassigned)"

            if now > due:
                if not _already_escalated(db, req, "Breach"):
                    hours_late = (now - due).total_seconds() / 3600
                    _escalate(db, req, "Breach",
                              f"{req.severity} request is {hours_late:.1f} h past its resolution deadline. "
                              f"Asset: {req.asset.asset_name}. Assigned to {who}. Status: {req.status}.")
                    result["breaches"] += 1
            elif elapsed_pct >= warn_pct and not _already_escalated(db, req, "Warning"):
                hours_left = (due - now).total_seconds() / 3600
                _escalate(db, req, "Warning",
                          f"{hours_left:.1f} h left to resolve this {req.severity.lower()} request "
                          f"({elapsed_pct:.0f}% of SLA used). Assigned to {who}. Status: {req.status}.")
                result["warnings"] += 1

            rdue = response_due(req)
            not_responded = req.accepted_at is None and req.status in ("Open", "Assigned", "Reopened")
            if rdue and now > rdue and not_responded and not _already_escalated(db, req, "Response"):
                _escalate(db, req, "Response",
                          f"No technician has responded within the {req.sla.response_hours} h response time. "
                          f"Assigned to {who}.")
                result["response_breaches"] += 1
        db.commit()
    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    if result["warnings"] or result["breaches"] or result["response_breaches"]:
        log.info("SLA check: %s", result)
    return result


def nightly_predictions() -> None:
    from .ml_engine import predict_all
    with SessionLocal() as db:
        if get_setting(db, "nightly_predictions"):
            log.info("Nightly predictions: %s", predict_all(db))


def weekly_retrain() -> None:
    from .ml_engine import InsufficientDataError, train_model
    with SessionLocal() as db:
        if not get_setting(db, "auto_retrain_weekly"):
            return
        try:
            train_model(db)
        except InsufficientDataError as e:
            log.info("Weekly retrain skipped: %s", e)


def workload_recount() -> None:
    with SessionLocal() as db:
        changed = recount_workloads(db)
        db.commit()
        if changed:
            log.info("Workload recount corrected %d technician(s)", changed)


def _safe(fn):
    def wrapper():
        try:
            fn()
        except Exception:
            log.exception("Scheduled job %s failed", fn.__name__)
    wrapper.__name__ = fn.__name__
    return wrapper


def start_scheduler() -> None:
    if scheduler.running:
        return
    scheduler.add_job(_safe(check_sla_deadlines), "interval", minutes=settings.SLA_CHECK_INTERVAL_MINUTES,
                      id="sla_check", replace_existing=True, next_run_time=datetime.now(timezone.utc),
                      max_instances=1, coalesce=True)
    scheduler.add_job(_safe(nightly_predictions), "cron", hour=2, minute=0, id="nightly_predictions",
                      replace_existing=True)
    scheduler.add_job(_safe(weekly_retrain), "cron", day_of_week="sun", hour=3, minute=0, id="weekly_retrain",
                      replace_existing=True)
    scheduler.add_job(_safe(workload_recount), "interval", hours=1, id="workload_recount", replace_existing=True)
    scheduler.start()
    log.info("Scheduler started (SLA check every %s min)", settings.SLA_CHECK_INTERVAL_MINUTES)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


def jobs_status() -> list[dict]:
    return [{"id": j.id, "next_run": j.next_run_time, "trigger": str(j.trigger)} for j in scheduler.get_jobs()]


if __name__ == "__main__":  # standalone worker: python -m app.scheduler
    logging.basicConfig(level=logging.INFO)
    from apscheduler.schedulers.blocking import BlockingScheduler
    scheduler = BlockingScheduler(timezone="UTC")  # rebinds the module-level scheduler
    start_scheduler()
