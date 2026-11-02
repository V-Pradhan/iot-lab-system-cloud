import csv
import hmac
import io
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..db import get_db
from ..logic import audit, fine_rate, get_settings, issue_dict, run_reminders
from ..mailer import send_email
from ..models import Equipment, Issue, Lab, Notification, RegistrationRequest, ReturnEvent, RfidScan, Student, now
from ..routers.rfid import scan_dict
from ..security import ADMIN, STAFF, get_lab, require_roles

router = APIRouter(prefix="/api")


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    cfg = get_settings(db)
    rate = fine_rate(cfg)
    today = now().replace(hour=0, minute=0, second=0, microsecond=0)
    active = db.query(Issue).filter(Issue.lab_id == lab.id, Issue.status == "issued").all()
    overdue = [i for i in active if i.due_date < today]
    pending_fines = 0.0
    for i in db.query(Issue).filter(Issue.lab_id == lab.id,
                                    (Issue.fine_status == "pending") | (Issue.status == "issued")).all():
        d = issue_dict(i, rate)
        pending_fines += d["accrued_fine"] + (d["fine_total"] if d["fine_status"] == "pending" else 0)
    totals = db.query(func.coalesce(func.sum(Equipment.total_qty), 0),
                      func.coalesce(func.sum(Equipment.available_qty), 0),
                      func.coalesce(func.sum(Equipment.issued_qty), 0)).filter(Equipment.lab_id == lab.id).one()
    low = db.query(Equipment).filter(Equipment.lab_id == lab.id, Equipment.available_qty <= 2, Equipment.total_qty > 0) \
        .order_by(Equipment.available_qty).limit(6).all()
    due_soon = [i for i in active if today <= i.due_date < today + timedelta(days=4)]
    scans = db.query(RfidScan).filter(RfidScan.lab_id == lab.id).order_by(RfidScan.id.desc()).limit(6).all()
    return {
        "lab": {"id": lab.id, "name": lab.name},
        "students": db.query(Student).filter(Student.is_active.is_(True)).count(),
        "equipment_types": db.query(Equipment).filter(Equipment.lab_id == lab.id).count(),
        "units_total": int(totals[0]), "units_available": int(totals[1]), "units_issued": int(totals[2]),
        "active_loans": len(active), "overdue_loans": len(overdue), "due_soon": len(due_soon),
        "pending_fines": round(pending_fines, 2), "currency": cfg["currency"],
        "pending_registrations": db.query(RegistrationRequest).filter(
            RegistrationRequest.lab_id == lab.id, RegistrationRequest.status == "PENDING").count(),
        "issued_today": db.query(Issue).filter(Issue.lab_id == lab.id, Issue.issue_date >= today).count(),
        "returned_today": db.query(ReturnEvent).join(Issue, ReturnEvent.issue_id == Issue.id)
        .filter(Issue.lab_id == lab.id, ReturnEvent.returned_at >= today).count(),
        "low_stock": [{"id": e.id, "name": e.name, "available": e.available_qty, "total": e.total_qty} for e in low],
        "recent_scans": [scan_dict(s) for s in scans],
    }


@router.get("/reports/inventory")
def inventory_report(db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    from .inventory import eq_dict
    rows = [eq_dict(e) for e in db.query(Equipment).filter(Equipment.lab_id == lab.id).order_by(Equipment.name).all()]
    keys = ("total_qty", "available_qty", "issued_qty", "damaged_qty", "missing_qty", "maintenance_qty")
    return {"rows": rows, "totals": {k: sum(r[k] for r in rows) for k in keys}}


def _parse_day(s: Optional[str], end: bool = False) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Dates must look like 2026-10-29")
    return d + timedelta(days=1) if end else d


def _transactions(db: Session, start, end, lab_id: int):
    rows = []
    q = db.query(Issue).filter(Issue.lab_id == lab_id)
    if start:
        q = q.filter(Issue.issue_date >= start)
    if end:
        q = q.filter(Issue.issue_date < end)
    for i in q.all():
        rows.append({"at": i.issue_date, "type": "issued", "student": i.student.name,
                     "uid": i.student.university_uid, "equipment": i.equipment.name,
                     "quantity": i.quantity, "detail": f"due {i.due_date.date()}", "fine": 0.0,
                     "staff": i.issuer.full_name if i.issuer else ""})
    q = db.query(ReturnEvent).join(Issue, ReturnEvent.issue_id == Issue.id).filter(Issue.lab_id == lab_id)
    if start:
        q = q.filter(ReturnEvent.returned_at >= start)
    if end:
        q = q.filter(ReturnEvent.returned_at < end)
    for r in q.all():
        rows.append({"at": r.returned_at, "type": "returned", "student": r.issue.student.name,
                     "uid": r.issue.student.university_uid, "equipment": r.issue.equipment.name,
                     "quantity": r.quantity,
                     "detail": f"{r.condition}, {r.overdue_days} day(s) late", "fine": r.fine_amount,
                     "staff": r.receiver.full_name if r.receiver else ""})
    rows.sort(key=lambda x: x["at"], reverse=True)
    return rows


@router.get("/reports/transactions")
def transactions(start: Optional[str] = None, end: Optional[str] = None, format: str = "json",
                 db: Session = Depends(get_db), lab: Lab = Depends(get_lab), _=Depends(require_roles(*STAFF))):
    rows = _transactions(db, _parse_day(start), _parse_day(end, True), lab.id)
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Date", "Type", "Student", "University UID", "Equipment", "Qty", "Detail", "Fine", "Staff"])
        for r in rows:
            w.writerow([r["at"].strftime("%Y-%m-%d %H:%M"), r["type"], r["student"], r["uid"],
                        r["equipment"], r["quantity"], r["detail"], r["fine"], r["staff"]])
        return Response(buf.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=transactions-{lab.code}.csv"})
    for r in rows:
        r["at"] = r["at"].isoformat()
    return rows[:1000]


# ---------------------------------------------------------- notifications
@router.get("/notifications")
def list_notifications(db: Session = Depends(get_db), _=Depends(require_roles(*ADMIN))):
    rows = db.query(Notification).order_by(Notification.id.desc()).limit(200).all()
    return [{"id": n.id, "issue_id": n.issue_id, "kind": n.kind, "to": n.to_email, "status": n.status,
             "error": n.error, "at": (n.sent_at or n.created_at).isoformat()} for n in rows]


@router.post("/notifications/run")
def run_now(db: Session = Depends(get_db), admin=Depends(require_roles(*ADMIN))):
    result = run_reminders(db)
    audit(db, admin, "run_reminders", str(result))
    db.commit()
    return result


class TestMail(BaseModel):
    to: str


@router.post("/notifications/test")
def test_mail(data: TestMail, _=Depends(require_roles(*ADMIN))):
    try:
        send_email(data.to, "Lab system test email", "If you can read this, email reminders are working.")
    except Exception as e:
        raise HTTPException(400, f"Could not send: {e}")
    return {"ok": True}


@router.api_route("/cron/reminders", methods=["GET", "POST"])
def cron_reminders(token: str = "", db: Session = Depends(get_db)):
    """For a free cron service (e.g. cron-job.org): wakes a sleeping server and sends the daily reminders."""
    if not config.CRON_TOKEN or not hmac.compare_digest(token.encode(), config.CRON_TOKEN.encode()):
        raise HTTPException(403, "Invalid token")
    return run_reminders(db)
