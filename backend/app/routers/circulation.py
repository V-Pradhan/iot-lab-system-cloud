from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db import get_db
from ..logic import (audit, consume_issue_code, fine_rate, get_settings, issue_dict, issue_items,
                     items_fingerprint, renew_issue, require_recent_scan, return_items, send_issue_code)
from ..models import Issue, Lab, Student, now
from ..security import STAFF, can_access_lab, get_lab, require_roles

router = APIRouter(prefix="/api")


class ItemIn(BaseModel):
    equipment_id: int
    quantity: int = Field(ge=1, le=1000)


class IssueIn(BaseModel):
    student_id: int
    items: List[ItemIn] = Field(min_length=1, max_length=30)
    request_id: Optional[str] = Field(default=None, max_length=40)
    notes: str = Field(default="", max_length=255)
    code: Optional[str] = Field(default=None, pattern=r"^\d{6}$")      # emailed one-time code
    override_reason: Optional[str] = Field(default=None, max_length=200)  # admin only, replaces scan + code


class ReturnItem(BaseModel):
    issue_id: int
    quantity: int = Field(ge=1, le=1000)
    condition: Literal["good", "damaged", "missing"] = "good"


class ReturnIn(BaseModel):
    items: List[ReturnItem] = Field(min_length=1, max_length=50)


class CodeIn(BaseModel):
    student_id: int
    items: List[ItemIn] = Field(min_length=1, max_length=30)


@router.post("/issue-codes")
def send_code(data: CodeIn, db: Session = Depends(get_db), lab: Lab = Depends(get_lab), user=Depends(require_roles(*STAFF))):
    student = db.get(Student, data.student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    return send_issue_code(db, user, student, data.items, lab)


@router.post("/issues", status_code=201)
def create_issue(data: IssueIn, db: Session = Depends(get_db), lab: Lab = Depends(get_lab), user=Depends(require_roles(*STAFF))):
    student = db.get(Student, data.student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    rate = fine_rate(get_settings(db))

    if data.request_id:  # a repeated click returns the earlier result without asking for the code again
        prior = db.query(Issue).filter(Issue.request_id.like(f"{data.request_id}:%")).all()
        if prior:
            return [issue_dict(i, rate) for i in prior]

    if data.override_reason:
        if user.role != "admin":
            raise HTTPException(403, "Only an administrator can issue without the card and code")
        if len(data.override_reason.strip()) < 5:
            raise HTTPException(400, "Write a short reason for the override")
        audit(db, user, "issue_override", f"{student.name} ({student.university_uid}): {data.override_reason.strip()}")
    else:
        require_recent_scan(db, student, lab.id)
        if not data.code:
            raise HTTPException(400, "Enter the 6-digit code emailed to the student")
        consume_issue_code(db, student, data.code, items_fingerprint(data.items))

    issues = issue_items(db, user, student, data.items, data.request_id, data.notes, lab)
    return [issue_dict(i, rate) for i in issues]


@router.get("/issues")
def list_issues(status: Literal["active", "overdue", "returned", "all"] = "active",
                student_id: Optional[int] = None, q: str = "",
                db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    query = db.query(Issue).join(Student, Issue.student_id == Student.id).filter(Issue.lab_id == lab.id)
    if status in ("active", "overdue"):
        query = query.filter(Issue.status == "issued")
    elif status == "returned":
        query = query.filter(Issue.status == "returned")
    if status == "overdue":
        query = query.filter(Issue.due_date < now().replace(hour=0, minute=0, second=0, microsecond=0))
    if student_id:
        query = query.filter(Issue.student_id == student_id)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(Student.name.ilike(like) | Student.university_uid.ilike(like))
    rate = fine_rate(get_settings(db))
    rows = query.order_by(Issue.due_date.asc() if status != "returned" else Issue.id.desc()).limit(500).all()
    return [issue_dict(i, rate) for i in rows]


def _check_issue_access(db: Session, user, issue_ids) -> None:
    """Loans can only be changed by staff of the laboratory the loan belongs to."""
    for iid in issue_ids:
        issue = db.get(Issue, iid)
        if issue and not can_access_lab(db, user, issue.lab_id):
            raise HTTPException(403, "This loan belongs to a laboratory you do not have access to")


@router.post("/issues/{issue_id}/renew")
def renew(issue_id: int, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    _check_issue_access(db, user, [issue_id])
    issue = renew_issue(db, user, issue_id)
    return issue_dict(issue, fine_rate(get_settings(db)))


@router.post("/returns")
def return_equipment(data: ReturnIn, db: Session = Depends(get_db), user=Depends(require_roles(*STAFF))):
    _check_issue_access(db, user, [i.issue_id for i in data.items])
    return {"results": return_items(db, user, data.items)}


@router.get("/fines")
def list_fines(db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    rate = fine_rate(get_settings(db))
    out = []
    for i in db.query(Issue).filter(Issue.lab_id == lab.id).order_by(Issue.id.desc()).all():
        d = issue_dict(i, rate)
        if d["fine_total"] > 0 or d["accrued_fine"] > 0:
            out.append(d)
    return out


class SettleIn(BaseModel):
    status: Literal["paid", "waived"]


@router.post("/fines/{issue_id}/settle")
def settle_fine(issue_id: int, data: SettleIn, db: Session = Depends(get_db),
                user=Depends(require_roles("admin", "teacher"))):
    issue = db.get(Issue, issue_id)
    if issue and not can_access_lab(db, user, issue.lab_id):
        raise HTTPException(403, "This loan belongs to a laboratory you do not have access to")
    if not issue or issue.fine_total <= 0:
        raise HTTPException(404, "No recorded fine on this loan")
    if data.status == "waived" and user.role != "admin":
        raise HTTPException(403, "Only an administrator can waive a fine")
    issue.fine_status = data.status
    audit(db, user, f"fine_{data.status}", f"issue #{issue.id}, amount {issue.fine_total}")
    db.commit()
    return issue_dict(issue, fine_rate(get_settings(db)))
