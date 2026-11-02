"""Laboratories and their RFID readers (administrator only)."""
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import state
from ..db import get_db
from ..logic import audit
from ..models import Device, Lab
from ..security import ADMIN, hash_device_key, require_roles

router = APIRouter(prefix="/api")


def lab_dict(l: Lab) -> dict:
    return {"id": l.id, "name": l.name, "code": l.code, "is_active": l.is_active}


def dev_dict(d: Device) -> dict:
    return {"id": d.id, "device_id": d.device_id, "name": d.name, "lab_id": d.lab_id,
            "lab_name": d.lab.name if d.lab else "", "is_active": d.is_active,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None}


class LabIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,20}$")


class LabPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


@router.get("/labs")
def list_labs(db: Session = Depends(get_db), _=Depends(require_roles(*ADMIN))):
    return [lab_dict(l) for l in db.query(Lab).order_by(Lab.id).all()]


@router.post("/labs", status_code=201)
def create_lab(data: LabIn, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    code = data.code.upper()
    if db.query(Lab).filter((Lab.code == code) | (Lab.name == data.name.strip())).first():
        raise HTTPException(409, "A laboratory with this name or code already exists")
    lab = Lab(name=data.name.strip(), code=code)
    db.add(lab)
    audit(db, admin, "create_lab", f"{lab.name} ({code})")
    db.commit()
    return lab_dict(lab)


@router.patch("/labs/{lab_id}")
def update_lab(lab_id: int, data: LabPatch, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    lab = db.get(Lab, lab_id)
    if not lab:
        raise HTTPException(404, "Laboratory not found")
    if data.name is not None:
        if db.query(Lab).filter(Lab.name == data.name.strip(), Lab.id != lab.id).first():
            raise HTTPException(409, "Another laboratory already has this name")
        lab.name = data.name.strip()
    if data.is_active is not None:
        if data.is_active is False and db.query(Lab).filter(Lab.is_active.is_(True), Lab.id != lab.id).count() == 0:
            raise HTTPException(400, "At least one laboratory must stay active")
        lab.is_active = data.is_active
    audit(db, admin, "update_lab", lab.name)
    db.commit()
    return lab_dict(lab)


# ------------------------------------------------------------------ readers
class DeviceIn(BaseModel):
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{3,40}$")
    name: str = Field(default="", max_length=100)
    lab_id: int


class DevicePatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=100)
    lab_id: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/devices")
def list_devices(db: Session = Depends(get_db), _=Depends(require_roles(*ADMIN))):
    return [dev_dict(d) for d in db.query(Device).order_by(Device.id).all()]


@router.post("/devices", status_code=201)
def create_device(data: DeviceIn, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    if not db.get(Lab, data.lab_id):
        raise HTTPException(404, "Laboratory not found")
    if db.query(Device).filter(Device.device_id == data.device_id).first():
        raise HTTPException(409, "A reader with this device ID already exists")
    key = secrets.token_urlsafe(24)
    d = Device(device_id=data.device_id, name=data.name.strip(), lab_id=data.lab_id, key_hash=hash_device_key(key))
    db.add(d)
    audit(db, admin, "create_device", f"{d.device_id} for lab {data.lab_id}")
    db.commit()
    state.device_cache.pop(d.device_id, None)
    return {**dev_dict(d), "key": key}        # the key is shown only now; only its hash is stored


@router.post("/devices/{did}/rotate-key")
def rotate_key(did: int, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "Reader not found")
    key = secrets.token_urlsafe(24)
    d.key_hash = hash_device_key(key)
    audit(db, admin, "rotate_device_key", d.device_id)
    db.commit()
    state.device_cache.pop(d.device_id, None)
    return {**dev_dict(d), "key": key}


@router.patch("/devices/{did}")
def update_device(did: int, data: DevicePatch, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    d = db.get(Device, did)
    if not d:
        raise HTTPException(404, "Reader not found")
    if data.name is not None:
        d.name = data.name.strip()
    if data.lab_id is not None:
        if not db.get(Lab, data.lab_id):
            raise HTTPException(404, "Laboratory not found")
        d.lab_id = data.lab_id
    if data.is_active is not None:
        d.is_active = data.is_active
    audit(db, admin, "update_device", d.device_id)
    db.commit()
    state.device_cache.pop(d.device_id, None)
    return dev_dict(d)
