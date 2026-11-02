from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..logic import audit
from ..models import Equipment, InventoryLog, Lab
from ..security import STAFF, get_lab, require_roles

router = APIRouter(prefix="/api")
LABELS = {"name": "name", "category": "category", "total_qty": "total", "damaged_qty": "damaged",
          "missing_qty": "missing", "maintenance_qty": "maintenance", "notes": "notes"}


def eq_dict(e: Equipment) -> dict:
    return {"id": e.id, "name": e.name, "category": e.category, "total_qty": e.total_qty,
            "available_qty": e.available_qty, "issued_qty": e.issued_qty,
            "damaged_qty": e.damaged_qty, "missing_qty": e.missing_qty,
            "maintenance_qty": e.maintenance_qty, "notes": e.notes}


class EquipmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    category: str = Field(default="", max_length=60)
    total_qty: int = Field(ge=0, le=100000)
    damaged_qty: int = Field(default=0, ge=0)
    missing_qty: int = Field(default=0, ge=0)
    maintenance_qty: int = Field(default=0, ge=0)
    notes: str = Field(default="", max_length=255)
    reason: str = Field(default="", max_length=200)


class EquipmentPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=120)
    category: Optional[str] = Field(default=None, max_length=60)
    total_qty: Optional[int] = Field(default=None, ge=0, le=100000)
    damaged_qty: Optional[int] = Field(default=None, ge=0)
    missing_qty: Optional[int] = Field(default=None, ge=0)
    maintenance_qty: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = Field(default=None, max_length=255)
    reason: str = Field(default="", max_length=200)


def _rebalance(e: Equipment):
    avail = e.total_qty - e.issued_qty - e.damaged_qty - e.missing_qty - e.maintenance_qty
    if avail < 0:
        raise HTTPException(400, f"Quantities exceed the total. {e.issued_qty} unit(s) are currently issued.")
    e.available_qty = avail


@router.get("/inventory")
def list_inventory(q: str = "", db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    query = db.query(Equipment).filter(Equipment.lab_id == lab.id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(Equipment.name.ilike(like) | Equipment.category.ilike(like))
    return [eq_dict(e) for e in query.order_by(Equipment.name).all()]


@router.post("/inventory", status_code=201)
def create_equipment(data: EquipmentIn, db: Session = Depends(get_db), lab: Lab = Depends(get_lab),
                     user=Depends(require_roles(*STAFF))):
    name = data.name.strip()
    if db.query(Equipment).filter(Equipment.lab_id == lab.id, Equipment.name == name).first():
        raise HTTPException(409, "Equipment with this name already exists in this laboratory")
    e = Equipment(lab_id=lab.id, name=name, category=data.category.strip(), total_qty=data.total_qty, issued_qty=0,
                  damaged_qty=data.damaged_qty, missing_qty=data.missing_qty,
                  maintenance_qty=data.maintenance_qty, notes=data.notes)
    _rebalance(e)
    db.add(e)
    db.flush()
    db.add(InventoryLog(lab_id=lab.id, equipment_id=e.id, equipment_name=e.name, user_id=user.id, action="add",
                        change=f"added with total {e.total_qty}", reason=data.reason.strip()))
    audit(db, user, "add_equipment", f"{e.name} x{e.total_qty} ({lab.name})")
    db.commit()
    return eq_dict(e)


@router.get("/inventory/log")
def inventory_log(db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    rows = db.query(InventoryLog).filter(InventoryLog.lab_id == lab.id).order_by(InventoryLog.id.desc()).limit(100).all()
    return [{"id": r.id, "at": r.created_at.isoformat(), "user": r.user.full_name if r.user else "",
             "equipment": r.equipment_name, "action": r.action, "change": r.change, "reason": r.reason} for r in rows]


@router.patch("/inventory/{eid}")
def update_equipment(eid: int, data: EquipmentPatch, db: Session = Depends(get_db), lab: Lab = Depends(get_lab),
                     user=Depends(require_roles(*STAFF))):
    e = db.query(Equipment).filter(Equipment.id == eid, Equipment.lab_id == lab.id).with_for_update().first()
    if not e:
        raise HTTPException(404, "Equipment not found in this laboratory")
    changes = []
    for f, label in LABELS.items():
        v = getattr(data, f)
        if v is None:
            continue
        v = v.strip() if isinstance(v, str) else v
        old = getattr(e, f)
        if v != old:
            if f == "name" and db.query(Equipment).filter(Equipment.lab_id == lab.id, Equipment.name == v, Equipment.id != e.id).first():
                raise HTTPException(409, "Another item in this laboratory already has that name")
            changes.append(f"{label} {old} \u2192 {v}")
            setattr(e, f, v)
    _rebalance(e)
    if changes:
        db.add(InventoryLog(lab_id=lab.id, equipment_id=e.id, equipment_name=e.name, user_id=user.id, action="update",
                            change="; ".join(changes)[:400], reason=data.reason.strip()))
        audit(db, user, "update_equipment", f"{e.name}: {'; '.join(changes)} ({lab.name})")
    db.commit()
    return eq_dict(e)
