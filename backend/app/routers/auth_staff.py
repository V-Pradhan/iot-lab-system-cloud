import time
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..logic import DEFAULTS, audit, get_settings
from ..models import AuditLog, Lab, Setting, StaffLab, User
from ..security import (ADMIN, STAFF, accessible_labs, create_token, get_current_user, hash_password,
                        require_roles, verify_password)

router = APIRouter(prefix="/api")
_failed: dict = {}  # username -> list of failure timestamps (simple brute-force guard)
Role = Literal["admin", "teacher", "lab_assistant"]


def user_dict(u: User, db: Session) -> dict:
    assigned = [r.lab_id for r in db.query(StaffLab).filter(StaffLab.user_id == u.id).all()]
    return {"id": u.id, "username": u.username, "full_name": u.full_name, "email": u.email,
            "employee_id": u.employee_id, "role": u.role, "is_active": u.is_active,
            "must_change_password": u.must_change_password, "lab_ids": assigned,
            "labs": [{"id": l.id, "name": l.name, "code": l.code} for l in accessible_labs(db, u)]}


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    key = data.username.strip().lower()
    recent = [t for t in _failed.get(key, []) if time.time() - t < 600]
    if len(recent) >= 5:
        raise HTTPException(429, "Too many failed attempts. Try again in 10 minutes.")
    user = db.query(User).filter(User.username == key).first()
    if not user or not user.is_active or not verify_password(data.password, user.password_hash):
        recent.append(time.time())
        _failed[key] = recent
        raise HTTPException(401, "Wrong username or password")
    _failed.pop(key, None)
    return {"token": create_token(user.id), "user": user_dict(user, db)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return user_dict(user, db)


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=72)


@router.post("/auth/change-password")
def change_password(data: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(data.old_password, user.password_hash):
        raise HTTPException(400, "Current password is wrong")
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    audit(db, user, "change_password")
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ staff
class StaffIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9_.-]+$")
    full_name: str = Field(min_length=2, max_length=100)
    email: str = Field(default="", max_length=120)
    employee_id: Optional[str] = Field(default=None, max_length=30)
    role: Role
    password: str = Field(min_length=8, max_length=72)
    lab_ids: List[int] = []


class StaffPatch(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    employee_id: Optional[str] = None
    role: Optional[Role] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=72)
    lab_ids: Optional[List[int]] = None


def _valid_lab_ids(db: Session, ids: List[int]) -> List[int]:
    ids = sorted(set(ids))
    found = {l.id for l in db.query(Lab).filter(Lab.id.in_(ids)).all()} if ids else set()
    if set(ids) - found:
        raise HTTPException(400, "Unknown laboratory selected")
    return ids


@router.get("/staff")
def list_staff(db: Session = Depends(get_db), _=Depends(require_roles(*ADMIN))):
    return [user_dict(u, db) for u in db.query(User).order_by(User.id).all()]


@router.post("/staff", status_code=201)
def create_staff(data: StaffIn, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    if data.role == "teacher" and not data.employee_id:
        raise HTTPException(400, "Teachers need an employee ID")
    if db.query(User).filter(User.username == data.username.lower()).first():
        raise HTTPException(409, "That username is taken")
    if data.employee_id and db.query(User).filter(User.employee_id == data.employee_id).first():
        raise HTTPException(409, "That employee ID is already registered")
    lab_ids = _valid_lab_ids(db, data.lab_ids)
    if data.role != "admin" and not lab_ids:
        raise HTTPException(400, "Choose at least one laboratory for this staff member")
    u = User(username=data.username.lower(), full_name=data.full_name, email=data.email,
             employee_id=data.employee_id or None, role=data.role,
             password_hash=hash_password(data.password), must_change_password=True)
    db.add(u)
    db.flush()
    for lid in lab_ids:
        db.add(StaffLab(user_id=u.id, lab_id=lid))
    audit(db, admin, "create_staff", f"{u.username} ({u.role})")
    db.commit()
    return user_dict(u, db)


@router.patch("/staff/{uid}")
def update_staff(uid: int, data: StaffPatch, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, "Staff member not found")
    if u.id == admin.id and (data.is_active is False or (data.role and data.role != "admin")):
        raise HTTPException(400, "You cannot disable or demote your own account")
    for field in ("full_name", "email", "employee_id", "role", "is_active"):
        val = getattr(data, field)
        if val is not None:
            setattr(u, field, val or None if field == "employee_id" else val)
    if data.password:
        u.password_hash = hash_password(data.password)
        u.must_change_password = True
    if data.lab_ids is not None:
        lab_ids = _valid_lab_ids(db, data.lab_ids)
        if u.role != "admin" and not lab_ids:
            raise HTTPException(400, "Choose at least one laboratory for this staff member")
        db.query(StaffLab).filter(StaffLab.user_id == u.id).delete()
        for lid in lab_ids:
            db.add(StaffLab(user_id=u.id, lab_id=lid))
    audit(db, admin, "update_staff", u.username)
    db.commit()
    return user_dict(u, db)


# --------------------------------------------------------------- settings
@router.get("/settings")
def read_settings(db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    return get_settings(db)


@router.put("/settings")
def write_settings(data: dict, db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    for k, v in data.items():
        if k not in DEFAULTS:
            raise HTTPException(400, f"Unknown setting: {k}")
        v = str(v).strip()
        if k in ("fine_per_day",):
            try:
                if float(v) < 0:
                    raise ValueError
            except ValueError:
                raise HTTPException(400, "Fine per day must be a number, 0 or more")
        if k in ("loan_days", "renew_days") and not (v.isdigit() and int(v) > 0):
            raise HTTPException(400, f"{k} must be a whole number above 0")
        if k == "reminder_days" and not all(p.strip().isdigit() for p in v.split(",") if p.strip()):
            raise HTTPException(400, "Reminder days must be numbers separated by commas, e.g. 7,1")
        if k == "renew_after_due":
            v = "true" if v.lower() == "true" else "false"
        row = db.get(Setting, k)
        if row:
            row.value = v
        else:
            db.add(Setting(key=k, value=v))
    audit(db, admin, "update_settings", ", ".join(data.keys()))
    db.commit()
    return get_settings(db)


@router.get("/audit")
def audit_log(db: Session = Depends(get_db), _=Depends(require_roles(*ADMIN))):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
    return [{"id": r.id, "user": r.user.full_name if r.user else "system", "action": r.action,
             "detail": r.detail, "at": r.created_at.isoformat()} for r in rows]
