"""Export maintenance reports as CSV or PDF."""
import csv
import io
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..models import Asset, MaintenanceRequest, Technician, User
from ..security import ADMIN, MANAGER, require_roles
from ..services.audit import log_action
from ..services.sla import sla_snapshot
from .assets import latest_predictions

router = APIRouter(prefix="/api/reports", tags=["Reports"])
staff_only = require_roles(MANAGER, ADMIN)

COLUMNS = ["ID", "Reported", "Title", "Asset", "Category", "Location", "Severity", "Status", "Technician",
           "Due", "Resolved", "SLA", "Labour h", "Cost", "Downtime h", "Rating"]


def _range(date_from: date | None, date_to: date | None, days: int) -> tuple[datetime, datetime]:
    end = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else datetime.now(timezone.utc)
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else end - timedelta(days=days)
    if start > end:
        raise HTTPException(400, "The start date must be before the end date.")
    return start, end


def _rows(db: Session, start: datetime, end: datetime, status: str | None) -> list[list]:
    stmt = (select(MaintenanceRequest)
            .options(selectinload(MaintenanceRequest.asset).selectinload(Asset.location),
                     selectinload(MaintenanceRequest.technician).selectinload(Technician.user),
                     selectinload(MaintenanceRequest.repair_logs), selectinload(MaintenanceRequest.feedback),
                     selectinload(MaintenanceRequest.sla))
            .where(MaintenanceRequest.reported_at.between(start, end))
            .order_by(MaintenanceRequest.reported_at))
    if status:
        stmt = stmt.where(MaintenanceRequest.status.in_([s.strip() for s in status.split(",")]))
    out = []
    for r in db.scalars(stmt):
        logs = r.repair_logs
        snap = sla_snapshot(r)
        out.append([
            r.request_id, r.reported_at.strftime("%Y-%m-%d %H:%M"), r.title, r.asset.asset_name, r.asset.category,
            r.asset.location.label if r.asset.location else "", r.severity, r.status,
            r.technician.user.full_name if r.technician else "",
            r.resolution_due.strftime("%Y-%m-%d %H:%M") if r.resolution_due else "",
            r.resolved_at.strftime("%Y-%m-%d %H:%M") if r.resolved_at else "",
            snap["state"].replace("_", " ") if snap else "",
            round(sum(float(l.labour_hours or 0) for l in logs), 2),
            round(sum(float(l.repair_cost or 0) for l in logs), 2),
            round(sum(float(l.downtime_hours or 0) for l in logs), 2),
            r.feedback.rating if r.feedback else "",
        ])
    return out


def _csv(rows: list[list], header: list[str], filename: str) -> StreamingResponse:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue().encode("utf-8-sig")]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def _pdf(rows: list[list], start: datetime, end: datetime, filename: str) -> StreamingResponse:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=12 * mm, rightMargin=12 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm, title="FixFlow maintenance report")
    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7, leading=8.5)
    story = [Paragraph("FixFlow maintenance report", styles["Title"]),
             Paragraph(f"{start:%d %b %Y} to {end:%d %b %Y} · generated {datetime.now(timezone.utc):%d %b %Y %H:%M} UTC",
                       styles["Normal"]), Spacer(1, 6 * mm)]

    total = len(rows)
    resolved = [r for r in rows if r[10]]
    met = sum(1 for r in rows if r[11] == "met")
    judged = sum(1 for r in rows if r[11] in ("met", "missed"))
    summary = [["Requests", "Resolved", "SLA compliance", "Total cost", "Labour hours", "Downtime hours", "Avg rating"],
               [total, len(resolved), f"{100 * met / judged:.1f}%" if judged else "—",
                f"{sum(r[13] for r in rows):,.2f}", f"{sum(r[12] for r in rows):,.1f}",
                f"{sum(r[14] for r in rows):,.1f}",
                f"{sum(r[15] for r in rows if r[15]) / max(1, sum(1 for r in rows if r[15])):.2f}"
                if any(r[15] for r in rows) else "—"]]
    st = Table(summary, hAlign="LEFT")
    st.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173F5A")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D6DCDF")),
                            ("PADDING", (0, 0), (-1, -1), 5)]))
    story += [st, Spacer(1, 6 * mm)]

    cols = [0, 1, 2, 3, 5, 6, 7, 8, 9, 11, 13, 14]
    data = [[COLUMNS[c] for c in cols]] + [[Paragraph(str(r[c]), small) for c in cols] for r in rows]
    widths = [12, 26, 55, 40, 45, 17, 19, 30, 26, 16, 18, 16]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#22577A")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 7.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F3F5F4")]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D6DCDF")), ("PADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t if rows else Paragraph("No requests in this period.", styles["Normal"]))
    doc.build(story)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/requests")
def export_requests(format: Literal["csv", "pdf"] = "csv", days: int = Query(30, ge=1, le=3650),
                    date_from: date | None = None, date_to: date | None = None, status: str | None = None,
                    db: Session = Depends(get_db), user: User = Depends(staff_only)):
    start, end = _range(date_from, date_to, days)
    rows = _rows(db, start, end, status)
    log_action(db, user.user_id, "report.exported", "report", None, {"format": format, "rows": len(rows)})
    db.commit()
    name = f"fixflow_requests_{start:%Y%m%d}_{end:%Y%m%d}.{format}"
    return _csv(rows, COLUMNS, name) if format == "csv" else _pdf(rows, start, end, name)


@router.get("/assets")
def export_assets(db: Session = Depends(get_db), user: User = Depends(staff_only)):
    preds = latest_predictions(db)
    rows = []
    for a in db.scalars(select(Asset).options(selectinload(Asset.location)).order_by(Asset.asset_id)):
        p = preds.get(a.asset_id)
        rows.append([a.asset_id, a.asset_name, a.category, a.location.label if a.location else "", a.qr_code,
                     a.purchase_date or "", a.warranty_expiry or "", a.status,
                     float(p.risk_score) if p else "", p.risk_level if p else ""])
    log_action(db, user.user_id, "report.exported", "report", None, {"format": "csv", "type": "assets"})
    db.commit()
    return _csv(rows, ["ID", "Name", "Category", "Location", "QR code", "Purchased", "Warranty until",
                       "Status", "Risk score", "Risk level"], "fixflow_assets.csv")
