"""RFID integration (per laboratory).

Reader side  : POST /api/rfid/scan     the card UID; the answer tells the reader what to show
               GET  /api/rfid/display  new issue/return screens for the reader's OLED
Browser side : POST /api/rfid/arm      start waiting for a card in the lab you are working in
               GET  /api/rfid/latest   newest scan of that lab

Every reader has its own device id and key and belongs to exactly one lab, so a scan on lab A's reader
can never be used in lab B.
"""
import hmac
import time
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import state
from ..db import get_db
from ..models import Device, DeviceMessage, Lab, RfidScan, Student, now
from ..security import STAFF, get_lab, hash_device_key, require_roles

router = APIRouter(prefix="/api")

ARM_SECONDS = 60
_recent: dict = {}                          # scan_id -> (timestamp, status, body)  (retried requests)


def authenticate_device(db: Session, device_id: str, key: str) -> dict:
    """Check the reader's id and key. Looked up in the database at most once a minute per reader."""
    t = time.time()
    hit = state.device_cache.get(device_id)
    if not hit or hit[0] < t:
        d = db.query(Device).filter(Device.device_id == device_id).first()
        info = {"lab_id": d.lab_id, "key_hash": d.key_hash, "active": d.is_active} if d else None
        state.device_cache[device_id] = hit = (t + 60, info)
        if d:
            d.last_seen = now()
            db.commit()
    info = hit[1]
    if not info or not info["active"] or not hmac.compare_digest(hash_device_key(key or ""), info["key_hash"]):
        raise HTTPException(403, "Invalid device or key")
    return info


class ScanIn(BaseModel):
    device_id: str = Field(max_length=40)
    uid: str = Field(pattern=r"^[0-9A-Fa-f]{4,20}$")
    scan_id: Optional[str] = Field(default=None, max_length=60)


def scan_dict(r: RfidScan) -> dict:
    s = r.student
    return {"id": r.id, "uid": r.uid, "result": r.result, "device_id": r.device_id,
            "at": r.created_at.isoformat(),
            "student": ({"id": s.id, "name": s.name, "university_uid": s.university_uid,
                         "class_section": s.class_section, "is_active": s.is_active} if s else None)}


@router.post("/rfid/scan")
def device_scan(data: ScanIn, db: Session = Depends(get_db), x_device_key: str = Header(default="")):
    dev = authenticate_device(db, data.device_id, x_device_key)
    lab_id = dev["lab_id"]
    uid = data.uid.upper()
    if data.scan_id and data.scan_id in _recent:      # the reader retried the same request
        _, code, body = _recent[data.scan_id]
        return JSONResponse(body, status_code=code)

    student = db.query(Student).filter(Student.rfid_uid == uid).first()
    arm = state.armed.get(lab_id)
    registering = bool(arm) and arm["mode"] == "register" and time.time() < arm["until"]
    name = ""

    if registering:
        if student:
            code, result, msg = 409, "in_use", f"Assigned to {student.name}"[:40]
        else:
            code, result, msg = 200, "captured", "UID captured. Confirm on PC"
            state.armed[lab_id] = {"mode": "lookup", "until": 0.0}
    elif not student:
        code, result, msg = 404, "unregistered", "Card not registered"
    elif not student.is_active:
        code, result, msg = 422, "inactive", "Student account inactive"
    else:
        code, result, msg = 200, "recognised", "Card recognised"
        name = student.name[:21]

    db.add(RfidScan(device_id=data.device_id, lab_id=lab_id, uid=uid, result=result,
                    student_id=student.id if student else None))
    db.commit()

    body = {"status": result, "message": msg, "display_name": name}
    if data.scan_id:
        _recent[data.scan_id] = (time.time(), code, body)
        if len(_recent) > 200:
            for k in sorted(_recent, key=lambda k: _recent[k][0])[:100]:
                _recent.pop(k, None)
    return JSONResponse(body, status_code=code)


@router.get("/rfid/display")
def display_messages(device_id: str, after_id: int = 0, db: Session = Depends(get_db),
                     x_device_key: str = Header(default="")):
    """The reader polls this and shows any new issue/return screens on its OLED."""
    dev = authenticate_device(db, device_id, x_device_key)
    lab_id = dev["lab_id"]
    latest = state.latest_msg.get(lab_id)
    if latest is None:                                  # first poll since the server started
        latest = db.query(func.max(DeviceMessage.id)).filter(DeviceMessage.lab_id == lab_id).scalar() or 0
        state.latest_msg[lab_id] = latest
    if after_id >= latest:                              # nothing new: answered without touching the database
        return {"latest_id": latest, "messages": []}
    since = now() - timedelta(seconds=30)
    rows = (db.query(DeviceMessage)
            .filter(DeviceMessage.lab_id == lab_id, DeviceMessage.id > after_id, DeviceMessage.created_at >= since)
            .order_by(DeviceMessage.id).limit(6).all())
    return {"latest_id": latest, "messages": [{"id": m.id, "title": m.title, "l1": m.line1, "l2": m.line2,
                                               "l3": m.line3, "ms": m.show_ms} for m in rows]}


class ArmIn(BaseModel):
    mode: Literal["register", "lookup"] = "lookup"


def _latest_id(db: Session) -> int:
    return db.query(func.max(RfidScan.id)).scalar() or 0


@router.post("/rfid/arm")
def arm(data: ArmIn, db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    state.armed[lab.id] = {"mode": data.mode, "until": time.time() + ARM_SECONDS if data.mode == "register" else 0.0}
    return {"baseline_id": _latest_id(db), "mode": data.mode, "expires_in": ARM_SECONDS}


@router.delete("/rfid/arm")
def disarm(lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    state.armed[lab.id] = {"mode": "lookup", "until": 0.0}
    return {"ok": True}


@router.get("/rfid/latest")
def latest(after_id: int = 0, db: Session = Depends(get_db), lab: Lab = Depends(get_lab),
           _=Depends(require_roles(*STAFF))):
    last = (db.query(RfidScan).filter(RfidScan.lab_id == lab.id, RfidScan.id > after_id)
            .order_by(RfidScan.id.desc()).first())
    if not last:
        return {"latest_id": after_id, "scan": None}
    return {"latest_id": last.id, "scan": scan_dict(last)}
