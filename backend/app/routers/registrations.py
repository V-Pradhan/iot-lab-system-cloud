"""Student self-registration.

Public : the student opens the lab's QR link on a phone and fills the form (stored as PENDING).
Staff  : review the request, tap the student's ID card on the reader to link it, then approve.
"""
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import config, state
from ..db import get_db
from ..logic import audit, email_in_background
from ..models import Lab, RegistrationRequest, Student, now
from ..security import STAFF, can_access_lab, get_lab, require_roles

router = APIRouter(prefix="/api")
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MOBILE = r"^\+?\d{10,13}$"
SIGN = "\nElectronics Department, University Institute of Computing"


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")


def _limit(key: str, max_n: int, window: int) -> None:
    t = time.time()
    hits = [x for x in state.rate.get(key, []) if t - x < window]
    if len(hits) >= max_n:
        raise HTTPException(429, "Too many attempts. Please try again later.")
    hits.append(t)
    state.rate[key] = hits


def req_dict(r: RegistrationRequest) -> dict:
    return {"id": r.id, "lab_id": r.lab_id, "lab_name": r.lab.name if r.lab else "", "name": r.name,
            "university_uid": r.university_uid, "course": r.course, "department": r.department,
            "class_section": r.class_section, "mobile": r.mobile, "email": r.email, "status": r.status,
            "note": r.note, "created_at": r.created_at.isoformat(),
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None}


# ----------------------------------------------------------------- public (no login)
@router.get("/public/labs/{code}")
def public_lab(code: str, db: Session = Depends(get_db)):
    lab = db.query(Lab).filter(Lab.code == code.upper(), Lab.is_active.is_(True)).first()
    if not lab:
        raise HTTPException(404, "This registration link is not valid")
    return {"name": lab.name, "code": lab.code}


class RegisterIn(BaseModel):
    lab_code: str = Field(max_length=20)
    name: str = Field(min_length=2, max_length=100)
    university_uid: str = Field(min_length=3, max_length=30)
    course: str = Field(min_length=1, max_length=80)
    department: str = Field(min_length=1, max_length=80)
    class_section: str = Field(min_length=1, max_length=40)
    mobile: str = Field(pattern=MOBILE)
    email: str = Field(pattern=EMAIL, max_length=120)
    consent: bool = False
    website: str = ""                      # hidden "honeypot" field: real people leave it empty


@router.post("/public/register", status_code=201)
def public_register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    _limit("reg-ip:" + _client_ip(request), 5, 600)
    _limit("reg-all", 200, 3600)
    if data.website:                       # a bot filled the hidden field: pretend it worked
        return {"ok": True, "message": "Your registration was received."}
    if not data.consent:
        raise HTTPException(400, "Please tick the box to agree that your details may be stored")
    lab = db.query(Lab).filter(Lab.code == data.lab_code.upper(), Lab.is_active.is_(True)).first()
    if not lab:
        raise HTTPException(404, "This registration link is not valid")
    uid = data.university_uid.strip().upper()
    if db.query(Student).filter(Student.university_uid == uid).first():
        raise HTTPException(409, "This university ID is already registered. Please meet the lab staff if you need help.")
    if db.query(RegistrationRequest).filter(RegistrationRequest.university_uid == uid,
                                            RegistrationRequest.status == "PENDING").first():
        raise HTTPException(409, "Your registration was already submitted and is waiting for approval.")
    r = RegistrationRequest(lab_id=lab.id, name=data.name.strip(), university_uid=uid, course=data.course.strip(),
                            department=data.department.strip(), class_section=data.class_section.strip(),
                            mobile=data.mobile, email=data.email.strip())
    db.add(r)
    db.commit()
    email_in_background(f"reg_received_{r.id}", r.email, f"Registration received: {lab.name}",
                        f"Hello {r.name},\n\nWe received your registration for {lab.name}. A staff member will check "
                        f"your details and link your ID card when you visit the lab. You will get another e-mail "
                        f"when it is approved.\n{SIGN}")
    return {"ok": True, "message": "Your registration was received. Please show your ID card to the lab staff."}


# ----------------------------------------------------------------- staff
def _get_for_staff(db: Session, user, rid: int) -> RegistrationRequest:
    r = db.get(RegistrationRequest, rid)
    if not r or not can_access_lab(db, user, r.lab_id):
        raise HTTPException(404, "Registration request not found")
    return r


@router.get("/registrations/count")
def registration_count(db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    n = db.query(RegistrationRequest).filter(RegistrationRequest.lab_id == lab.id,
                                             RegistrationRequest.status == "PENDING").count()
    return {"pending": n}


@router.get("/registrations")
def list_registrations(status: str = "PENDING", db: Session = Depends(get_db), lab: Lab = Depends(get_lab),
                       _=Depends(require_roles(*STAFF))):
    q = db.query(RegistrationRequest).filter(RegistrationRequest.lab_id == lab.id)
    if status != "ALL":
        q = q.filter(RegistrationRequest.status == status.upper())
    return [req_dict(r) for r in q.order_by(RegistrationRequest.id.desc()).limit(200).all()]


class RegPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    course: Optional[str] = Field(default=None, max_length=80)
    department: Optional[str] = Field(default=None, max_length=80)
    class_section: Optional[str] = Field(default=None, max_length=40)
    mobile: Optional[str] = Field(default=None, pattern=MOBILE)
    email: Optional[str] = Field(default=None, pattern=EMAIL, max_length=120)


@router.patch("/registrations/{rid}")
def fix_registration(rid: int, data: RegPatch, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    r = _get_for_staff(db, user, rid)
    if r.status != "PENDING":
        raise HTTPException(400, "Only pending requests can be edited")
    for f in ("name", "course", "department", "class_section", "mobile", "email"):
        v = getattr(data, f)
        if v is not None:
            setattr(r, f, v.strip())
    db.commit()
    return req_dict(r)


class ApproveIn(BaseModel):
    rfid_uid: str = Field(pattern=r"^[0-9A-Fa-f]{4,20}$")


@router.post("/registrations/{rid}/approve")
def approve(rid: int, data: ApproveIn, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    r = _get_for_staff(db, user, rid)
    if r.status != "PENDING":
        raise HTTPException(400, "This request was already reviewed")
    uid = data.rfid_uid.upper()
    other = db.query(Student).filter(Student.rfid_uid == uid).first()
    if other:
        raise HTTPException(409, f"This card is already assigned to {other.name}")
    if db.query(Student).filter(Student.university_uid == r.university_uid).first():
        raise HTTPException(409, "A student with this university ID already exists")
    s = Student(name=r.name, university_uid=r.university_uid, class_section=r.class_section, mobile=r.mobile,
                email=r.email, course=r.course, department=r.department, registered_lab_id=r.lab_id, rfid_uid=uid)
    db.add(s)
    db.flush()
    r.status, r.student_id = "APPROVED", s.id
    r.reviewed_by, r.reviewed_at = user.id, now()
    audit(db, user, "approve_registration", f"{r.name} ({r.university_uid})")
    db.commit()
    email_in_background(f"reg_approved_{r.id}", r.email, f"Registration approved: {r.lab.name}",
                        f"Hello {r.name},\n\nYour registration is approved. You can now collect equipment from "
                        f"{r.lab.name} by tapping your ID card on the reader.\n{SIGN}")
    return req_dict(r)


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=300)


@router.post("/registrations/{rid}/reject")
def reject(rid: int, data: NoteIn, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    r = _get_for_staff(db, user, rid)
    if r.status != "PENDING":
        raise HTTPException(400, "This request was already reviewed")
    r.status, r.note, r.reviewed_by, r.reviewed_at = "REJECTED", data.note.strip(), user.id, now()
    audit(db, user, "reject_registration", f"{r.name} ({r.university_uid})")
    db.commit()
    email_in_background(f"reg_rejected_{r.id}", r.email, f"Registration not approved: {r.lab.name}",
                        f"Hello {r.name},\n\nYour registration for {r.lab.name} could not be approved."
                        + (f"\nReason: {r.note}" if r.note else "") + f"\nPlease meet the lab staff for help.\n{SIGN}")
    return req_dict(r)


@router.post("/registrations/{rid}/correction")
def needs_correction(rid: int, data: NoteIn, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    r = _get_for_staff(db, user, rid)
    if r.status != "PENDING":
        raise HTTPException(400, "This request was already reviewed")
    if len(data.note.strip()) < 3:
        raise HTTPException(400, "Write what the student must correct")
    r.status, r.note, r.reviewed_by, r.reviewed_at = "NEEDS_CORRECTION", data.note.strip(), user.id, now()
    audit(db, user, "registration_needs_correction", f"{r.name} ({r.university_uid})")
    db.commit()
    link = f"{config.PUBLIC_URL}/#/register/{r.lab.code}" if config.PUBLIC_URL else "the QR code in the lab"
    email_in_background(f"reg_correction_{r.id}", r.email, f"Please correct your registration: {r.lab.name}",
                        f"Hello {r.name},\n\nPlease correct your registration for {r.lab.name}: {r.note}\n\n"
                        f"Fill the form again using {link}.\n{SIGN}")
    return req_dict(r)
