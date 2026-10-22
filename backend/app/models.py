"""
FixFlow database models.

The 13 tables from the project specification are implemented exactly as specified
(column names, types and constraints). A few clearly-marked *extension* columns and
five supporting tables were added because the requirements need somewhere to store
that data (in-app notifications, audit logs, settings, asset categories, ML runs).

Note: "user" is a reserved word in PostgreSQL, so the User table is named "users".
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# ---- Domain constants -------------------------------------------------------
ROLES = ("Reporter", "Technician", "Manager", "Admin")
SEVERITIES = ("Low", "Medium", "High", "Critical")
# Lifecycle: Open → Assigned → In Progress (⇄ On Hold) → Resolved → Closed / Reopened
REQUEST_STATUSES = ("Open", "Assigned", "In Progress", "On Hold", "Resolved", "Closed", "Reopened")
ACTIVE_STATUSES = ("Assigned", "In Progress", "On Hold")          # counts towards workload
UNRESOLVED_STATUSES = ("Open", "Assigned", "In Progress", "On Hold", "Reopened")
ASSET_STATUSES = ("Working", "Faulty", "Under Repair", "Retired")
RISK_LEVELS = ("Low", "Medium", "High")


def _in(col: str, values: tuple[str, ...]) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


TS = DateTime(timezone=True)


# ---- 1. User ------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_users_role"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(15))
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="Reporter")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    # extension: lets admins deactivate accounts without deleting history
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    technician: Mapped[Technician | None] = relationship(back_populates="user", uselist=False)
    reported_requests: Mapped[list[MaintenanceRequest]] = relationship(
        back_populates="reporter", foreign_keys="MaintenanceRequest.reported_by"
    )


# ---- 2. Location --------------------------------------------------------------
class Location(Base):
    __tablename__ = "locations"

    location_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    building: Mapped[str] = mapped_column(String(100), nullable=False)
    floor: Mapped[str | None] = mapped_column(String(20))
    room: Mapped[str | None] = mapped_column(String(50))

    assets: Mapped[list[Asset]] = relationship(back_populates="location")

    @property
    def label(self) -> str:
        parts = [self.building]
        if self.floor:
            parts.append(f"Floor {self.floor}")
        if self.room:
            parts.append(f"Room {self.room}")
        return ", ".join(parts)


# ---- 3. Asset -----------------------------------------------------------------
class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (CheckConstraint(_in("status", ASSET_STATUSES), name="ck_assets_status"),)

    asset_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    location_id: Mapped[int | None] = mapped_column(ForeignKey("locations.location_id"), index=True)
    asset_name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    qr_code: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_expiry: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="Working", server_default="Working")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    location: Mapped[Location | None] = relationship(back_populates="assets")
    requests: Mapped[list[MaintenanceRequest]] = relationship(back_populates="asset")
    predictions: Mapped[list[FailurePrediction]] = relationship(back_populates="asset")


# ---- 6. Technician_Skill (association table) ----------------------------------
technician_skill = Table(
    "technician_skills",
    Base.metadata,
    Column("technician_id", ForeignKey("technicians.technician_id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", ForeignKey("skills.skill_id", ondelete="CASCADE"), primary_key=True),
)


# ---- 4. Technician ------------------------------------------------------------
class Technician(Base):
    __tablename__ = "technicians"

    technician_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), unique=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    current_workload: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user: Mapped[User] = relationship(back_populates="technician")
    skills: Mapped[list[Skill]] = relationship(secondary=technician_skill, back_populates="technicians")
    assigned_requests: Mapped[list[MaintenanceRequest]] = relationship(back_populates="technician")


# ---- 5. Skill -----------------------------------------------------------------
class Skill(Base):
    __tablename__ = "skills"

    skill_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    technicians: Mapped[list[Technician]] = relationship(secondary=technician_skill, back_populates="skills")


# ---- 7. SLA_Policy ------------------------------------------------------------
class SLAPolicy(Base):
    __tablename__ = "sla_policies"
    __table_args__ = (
        CheckConstraint(_in("severity", SEVERITIES), name="ck_sla_severity"),
        CheckConstraint("response_hours > 0 AND resolution_hours > 0", name="ck_sla_positive"),
    )

    sla_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    response_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_hours: Mapped[int] = mapped_column(Integer, nullable=False)


# ---- 8. Maintenance_Request ---------------------------------------------------
class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"
    __table_args__ = (
        CheckConstraint(_in("severity", SEVERITIES), name="ck_req_severity"),
        CheckConstraint(_in("status", REQUEST_STATUSES), name="ck_req_status"),
    )

    request_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id"), nullable=False, index=True)
    reported_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False, index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("technicians.technician_id"), nullable=True, index=True)
    sla_id: Mapped[int | None] = mapped_column(ForeignKey("sla_policies.sla_id"))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="Open", server_default="Open", index=True)
    reported_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)
    resolution_due: Mapped[datetime | None] = mapped_column(TS)
    resolved_at: Mapped[datetime | None] = mapped_column(TS, nullable=True)

    # --- extension columns (work timer, lifecycle timestamps, preventive flag) ---
    is_preventive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    assigned_at: Mapped[datetime | None] = mapped_column(TS)
    accepted_at: Mapped[datetime | None] = mapped_column(TS)
    work_started_at: Mapped[datetime | None] = mapped_column(TS)   # set while the timer is running
    work_seconds: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    closed_at: Mapped[datetime | None] = mapped_column(TS)
    reopen_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    asset: Mapped[Asset] = relationship(back_populates="requests")
    reporter: Mapped[User] = relationship(back_populates="reported_requests", foreign_keys=[reported_by])
    technician: Mapped[Technician | None] = relationship(back_populates="assigned_requests")
    sla: Mapped[SLAPolicy | None] = relationship()
    photos: Mapped[list[RequestPhoto]] = relationship(back_populates="request", cascade="all, delete-orphan")
    repair_logs: Mapped[list[RepairLog]] = relationship(back_populates="request", cascade="all, delete-orphan")
    escalations: Mapped[list[Escalation]] = relationship(back_populates="request", cascade="all, delete-orphan")
    feedback: Mapped[Feedback | None] = relationship(back_populates="request", uselist=False, cascade="all, delete-orphan")


# ---- 9. Request_Photo ---------------------------------------------------------
class RequestPhoto(Base):
    __tablename__ = "request_photos"
    __table_args__ = (CheckConstraint(_in("photo_type", ("Before", "After")), name="ck_photo_type"),)

    photo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("maintenance_requests.request_id", ondelete="CASCADE"), index=True)
    photo_url: Mapped[str] = mapped_column(Text, nullable=False)
    photo_type: Mapped[str] = mapped_column(String(10), default="Before")
    uploaded_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    request: Mapped[MaintenanceRequest] = relationship(back_populates="photos")


# ---- 10. Repair_Log -----------------------------------------------------------
class RepairLog(Base):
    __tablename__ = "repair_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("maintenance_requests.request_id", ondelete="CASCADE"), index=True)
    technician_id: Mapped[int | None] = mapped_column(ForeignKey("technicians.technician_id"))
    work_notes: Mapped[str | None] = mapped_column(Text)
    parts_used: Mapped[str | None] = mapped_column(Text)
    labour_hours: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    repair_cost: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    downtime_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    completed_at: Mapped[datetime | None] = mapped_column(TS)

    request: Mapped[MaintenanceRequest] = relationship(back_populates="repair_logs")
    technician: Mapped[Technician | None] = relationship()


# ---- 11. Escalation -----------------------------------------------------------
class Escalation(Base):
    __tablename__ = "escalations"

    escalation_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("maintenance_requests.request_id", ondelete="CASCADE"), index=True)
    escalated_to: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    reason: Mapped[str | None] = mapped_column(String(255))
    escalated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
    # extension columns
    level: Mapped[str] = mapped_column(String(20), default="Breach", server_default="Breach")  # Warning / Breach / Response
    is_acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    request: Mapped[MaintenanceRequest] = relationship(back_populates="escalations")
    recipient: Mapped[User] = relationship()


# ---- 12. Feedback -------------------------------------------------------------
class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="ck_feedback_rating"),)

    feedback_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("maintenance_requests.request_id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())

    request: Mapped[MaintenanceRequest] = relationship(back_populates="feedback")
    user: Mapped[User] = relationship()


# ---- 13. Failure_Prediction ---------------------------------------------------
class FailurePrediction(Base):
    __tablename__ = "failure_predictions"
    __table_args__ = (
        CheckConstraint("risk_score BETWEEN 0 AND 1", name="ck_pred_score"),
        CheckConstraint(_in("risk_level", RISK_LEVELS), name="ck_pred_level"),
    )

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.asset_id", ondelete="CASCADE"), index=True)
    risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(10), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50))
    predicted_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)

    asset: Mapped[Asset] = relationship(back_populates="predictions")


# =============================================================================
# Supporting tables (not in the original ERD, required by the feature list)
# =============================================================================
class AssetCategory(Base):
    """Admin-managed asset categories. Each maps to the skill needed to repair it,
    which is what the auto-assignment engine uses for skill matching."""
    __tablename__ = "asset_categories"

    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.skill_id", ondelete="SET NULL"))
    description: Mapped[str | None] = mapped_column(String(255))

    skill: Mapped[Skill | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), index=True)

    user: Mapped[User | None] = relationship()


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TS, server_default=func.now(), onupdate=func.now())


class ModelRun(Base):
    """One row per training run of the failure-prediction model."""
    __tablename__ = "model_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(40), nullable=False)
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    positive_rate: Mapped[float | None] = mapped_column(Numeric(6, 4))
    metrics: Mapped[dict | None] = mapped_column(JSON)
    feature_importance: Mapped[dict | None] = mapped_column(JSON)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    trained_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"))
    trained_at: Mapped[datetime] = mapped_column(TS, server_default=func.now())
