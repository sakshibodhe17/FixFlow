"""Pydantic schemas for request bodies. Responses are built by the serializers in
services/serializers.py so nested objects stay explicit and easy to read."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

Role = Literal["Reporter", "Technician", "Manager", "Admin"]
Severity = Literal["Low", "Medium", "High", "Critical"]
Status = Literal["Open", "Assigned", "In Progress", "On Hold", "Resolved", "Closed", "Reopened"]
AssetStatus = Literal["Working", "Faulty", "Under Repair", "Retired"]

Password = Annotated[str, Field(min_length=8, max_length=72)]


# ---- Auth / users -----------------------------------------------------------
class RegisterIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: Password
    phone: str | None = Field(default=None, max_length=15)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class ProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=15)


class PasswordChange(BaseModel):
    current_password: str
    new_password: Password


class UserCreate(RegisterIn):
    role: Role = "Reporter"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=100)
    phone: str | None = Field(default=None, max_length=15)
    role: Role | None = None
    is_active: bool | None = None


class PasswordReset(BaseModel):
    new_password: Password


# ---- Catalog ------------------------------------------------------------------
class LocationIn(BaseModel):
    building: str = Field(min_length=1, max_length=100)
    floor: str | None = Field(default=None, max_length=20)
    room: str | None = Field(default=None, max_length=50)


class SkillIn(BaseModel):
    skill_name: str = Field(min_length=2, max_length=50)


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=50)
    skill_id: int | None = None
    description: str | None = Field(default=None, max_length=255)


# ---- Assets -------------------------------------------------------------------
class AssetIn(BaseModel):
    asset_name: str = Field(min_length=2, max_length=150)
    category: str = Field(min_length=2, max_length=50)
    location_id: int | None = None
    purchase_date: date | None = None
    warranty_expiry: date | None = None
    status: AssetStatus = "Working"


class AssetUpdate(BaseModel):
    asset_name: str | None = Field(default=None, min_length=2, max_length=150)
    category: str | None = Field(default=None, min_length=2, max_length=50)
    location_id: int | None = None
    purchase_date: date | None = None
    warranty_expiry: date | None = None
    status: AssetStatus | None = None


# ---- Requests -----------------------------------------------------------------
class RequestCreate(BaseModel):
    asset_id: int | None = None
    qr_code: str | None = None
    title: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    severity: Severity = "Medium"


class CompleteWork(BaseModel):
    work_notes: str = Field(min_length=3, max_length=5000)
    parts_used: str | None = Field(default=None, max_length=2000)
    labour_hours: float | None = Field(default=None, ge=0, le=999)
    repair_cost: float = Field(default=0, ge=0, le=99_999_999)
    downtime_hours: float | None = Field(default=None, ge=0, le=9999)


class RepairLogIn(BaseModel):
    work_notes: str = Field(min_length=3, max_length=5000)
    parts_used: str | None = Field(default=None, max_length=2000)
    labour_hours: float | None = Field(default=None, ge=0, le=999)
    repair_cost: float | None = Field(default=None, ge=0, le=99_999_999)


class FeedbackIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReopenIn(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class AssignIn(BaseModel):
    technician_id: int


class StatusOverride(BaseModel):
    status: Status
    note: str | None = Field(default=None, max_length=500)


# ---- Technicians --------------------------------------------------------------
class TechnicianUpdate(BaseModel):
    is_available: bool | None = None
    skill_ids: list[int] | None = None


# ---- SLA ----------------------------------------------------------------------
class SLAPolicyIn(BaseModel):
    severity: Severity
    response_hours: int = Field(gt=0, le=24 * 60)
    resolution_hours: int = Field(gt=0, le=24 * 365)

    @field_validator("resolution_hours")
    @classmethod
    def resolution_after_response(cls, v, info):
        resp = info.data.get("response_hours")
        if resp is not None and v < resp:
            raise ValueError("Resolution time must be at least the response time")
        return v


class SLAPolicyUpdate(BaseModel):
    response_hours: int = Field(gt=0, le=24 * 60)
    resolution_hours: int = Field(gt=0, le=24 * 365)


# ---- Predictions --------------------------------------------------------------
class PreventiveIn(BaseModel):
    asset_id: int
    scheduled_for: datetime
    notes: str | None = Field(default=None, max_length=2000)
    severity: Severity = "Medium"


# ---- Admin --------------------------------------------------------------------
class SettingsUpdate(BaseModel):
    values: dict[str, str | int | float | bool]
