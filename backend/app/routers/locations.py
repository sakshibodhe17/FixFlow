"""Locations: buildings, floors and rooms."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Asset, Location, User
from ..schemas import LocationIn
from ..security import ADMIN, MANAGER, get_current_user, require_roles
from ..services.audit import log_action
from ..services.serializers import location_out

router = APIRouter(prefix="/api/locations", tags=["Locations"])


@router.get("")
def list_locations(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    counts = dict(db.execute(select(Asset.location_id, func.count()).group_by(Asset.location_id)).all())
    rows = db.scalars(select(Location).order_by(Location.building, Location.floor, Location.room))
    return [{**location_out(l), "asset_count": counts.get(l.location_id, 0)} for l in rows]


@router.post("", status_code=201)
def create_location(body: LocationIn, db: Session = Depends(get_db), user: User = Depends(require_roles(MANAGER, ADMIN))):
    exists = db.scalar(select(Location).where(
        Location.building == body.building, Location.floor == body.floor, Location.room == body.room))
    if exists:
        raise HTTPException(409, "That location already exists.")
    loc = Location(**body.model_dump())
    db.add(loc)
    db.flush()
    log_action(db, user.user_id, "location.created", "location", loc.location_id, body.model_dump())
    db.commit()
    return location_out(loc)


@router.put("/{location_id}")
def update_location(location_id: int, body: LocationIn, db: Session = Depends(get_db),
                    user: User = Depends(require_roles(MANAGER, ADMIN))):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    for k, v in body.model_dump().items():
        setattr(loc, k, v)
    log_action(db, user.user_id, "location.updated", "location", loc.location_id, body.model_dump())
    db.commit()
    return location_out(loc)


@router.delete("/{location_id}", status_code=204)
def delete_location(location_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(ADMIN))):
    loc = db.get(Location, location_id)
    if not loc:
        raise HTTPException(404, "Location not found")
    if db.scalar(select(func.count()).select_from(Asset).where(Asset.location_id == location_id)):
        raise HTTPException(409, "Move or retire the assets in this location before deleting it.")
    db.delete(loc)
    log_action(db, user.user_id, "location.deleted", "location", location_id)
    db.commit()
