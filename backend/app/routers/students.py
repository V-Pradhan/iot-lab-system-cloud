from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..logic import audit
from ..models import Student
from ..security import STAFF, get_lab, require_roles

router = APIRouter(prefix="/api")
EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
MOBILE = r"^\+?\d{10,13}$"
RFID = r"^[0-9A-Fa-f]{4,20}$"


def student_dict(s: Student) -> dict:
    return {"id": s.id, "name": s.name, "university_uid": s.university_uid,
            "class_section": s.class_section, "mobile": s.mobile, "email": s.email,
            "course": s.course, "department": s.department,
            "rfid_uid": s.rfid_uid, "is_active": s.is_active}


class StudentIn(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    university_uid: str = Field(min_length=3, max_length=30)
    class_section: str = Field(min_length=1, max_length=40)
    mobile: str = Field(pattern=MOBILE)
    email: str = Field(pattern=EMAIL, max_length=120)
    course: str = Field(default="", max_length=80)
    department: str = Field(default="", max_length=80)
    rfid_uid: Optional[str] = Field(default=None, pattern=RFID)


class StudentPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    class_section: Optional[str] = Field(default=None, min_length=1, max_length=40)
    course: Optional[str] = Field(default=None, max_length=80)
    department: Optional[str] = Field(default=None, max_length=80)
    mobile: Optional[str] = Field(default=None, pattern=MOBILE)
    email: Optional[str] = Field(default=None, pattern=EMAIL)
    rfid_uid: Optional[str] = Field(default=None, pattern=RFID)
    clear_rfid: bool = False
    is_active: Optional[bool] = None


def _check_rfid_free(db: Session, uid: str, except_id: Optional[int] = None):
    other = db.query(Student).filter(Student.rfid_uid == uid).first()
    if other and other.id != except_id:
        raise HTTPException(409, f"This card is already assigned to {other.name}")


@router.get("/students")
def list_students(q: str = "", db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    query = db.query(Student)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Student.name.ilike(like), Student.university_uid.ilike(like),
                                 Student.class_section.ilike(like), Student.mobile.ilike(like)))
    return [student_dict(s) for s in query.order_by(Student.name).limit(300).all()]


@router.post("/students", status_code=201)
def create_student(data: StudentIn, db: Session = Depends(get_db), lab=Depends(get_lab), user=Depends(require_roles(*STAFF))):
    uid = data.university_uid.strip().upper()
    if db.query(Student).filter(Student.university_uid == uid).first():
        raise HTTPException(409, "A student with this university UID already exists")
    rfid = data.rfid_uid.upper() if data.rfid_uid else None
    if rfid:
        _check_rfid_free(db, rfid)
    s = Student(name=data.name.strip(), university_uid=uid, class_section=data.class_section.strip(),
                mobile=data.mobile, email=data.email.strip(), course=data.course.strip(),
                department=data.department.strip(), registered_lab_id=lab.id, rfid_uid=rfid)
    db.add(s)
    audit(db, user, "register_student", f"{s.name} ({uid})")
    db.commit()
    return student_dict(s)


@router.get("/students/{sid}")
def get_student(sid: int, db: Session = Depends(get_db), _=Depends(require_roles(*STAFF))):
    s = db.get(Student, sid)
    if not s:
        raise HTTPException(404, "Student not found")
    return student_dict(s)


@router.patch("/students/{sid}")
def update_student(sid: int, data: StudentPatch, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    s = db.get(Student, sid)
    if not s:
        raise HTTPException(404, "Student not found")
    for f in ("name", "class_section", "course", "department", "mobile", "email", "is_active"):
        v = getattr(data, f)
        if v is not None:
            setattr(s, f, v)
    if data.clear_rfid:
        s.rfid_uid = None
    if data.rfid_uid:
        uid = data.rfid_uid.upper()
        _check_rfid_free(db, uid, s.id)
        s.rfid_uid = uid
    audit(db, user, "update_student", f"{s.name} ({s.university_uid})")
    db.commit()
    return student_dict(s)
