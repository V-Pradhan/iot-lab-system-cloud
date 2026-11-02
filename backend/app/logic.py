"""Business rules: settings, fines, issuing, returning, renewing, reminders."""
import hashlib
import hmac
import math
import logging
import secrets
import threading
from datetime import timedelta
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import config, state
from .mailer import send_email
from .models import (AuditLog, DeviceMessage, Equipment, Issue, IssueCode, Lab, Notification, ReturnEvent,
                     RfidScan, Setting, Student, User, now)

log = logging.getLogger("lab")

DEFAULTS = {
    "fine_per_day": "5",        # per unit, per overdue day
    "loan_days": "30",
    "renew_days": "30",
    "reminder_days": "7,1",     # days before due date
    "renew_after_due": "false",  # may overdue loans be renewed?
    "currency": "Rs ",
}


def get_settings(db: Session) -> dict:
    cfg = dict(DEFAULTS)
    for s in db.query(Setting).all():
        cfg[s.key] = s.value
    return cfg


def fine_rate(cfg: dict) -> float:
    try:
        return float(cfg["fine_per_day"])
    except ValueError:
        return 0.0


def audit(db: Session, user: Optional[User], action: str, detail: str = "") -> None:
    db.add(AuditLog(user_id=user.id if user else None, action=action, detail=detail[:500]))


def overdue_days(due, ref) -> int:
    return max(0, (ref.date() - due.date()).days)


def outstanding(i: Issue) -> int:
    return i.quantity - i.returned_qty


def issue_dict(i: Issue, rate: float) -> dict:
    out = outstanding(i)
    od = overdue_days(i.due_date, now()) if i.status == "issued" else 0
    accrued = round(od * rate * out, 2) if out > 0 else 0.0
    return {
        "id": i.id,
        "student": {"id": i.student.id, "name": i.student.name,
                    "university_uid": i.student.university_uid,
                    "class_section": i.student.class_section},
        "equipment": {"id": i.equipment.id, "name": i.equipment.name},
        "quantity": i.quantity,
        "returned_qty": i.returned_qty,
        "outstanding": out,
        "issue_date": i.issue_date.isoformat(),
        "due_date": i.due_date.isoformat(),
        "renewed": i.renewed,
        "status": i.status,
        "overdue_days": od,
        "accrued_fine": accrued,
        "fine_total": round(i.fine_total, 2),
        "fine_status": i.fine_status,
        "issued_by": i.issuer.full_name if i.issuer else "",
        "notes": i.notes,
    }


# ----------------------------------------------------------------- issuing
def issue_items(db: Session, staff: User, student: Student, items: list,
                request_id: Optional[str], notes: str, lab: Lab) -> List[Issue]:
    if not student.is_active:
        raise HTTPException(400, "This student account is inactive")
    if request_id:  # idempotency: a repeated click returns the same result
        prior = db.query(Issue).filter(Issue.request_id.like(f"{request_id}:%")).all()
        if prior:
            return prior

    merged = {}
    for it in items:
        merged[it.equipment_id] = merged.get(it.equipment_id, 0) + it.quantity

    cfg = get_settings(db)
    loan_days = int(cfg["loan_days"])
    t = now()
    created = []
    for idx, (eq_id, qty) in enumerate(sorted(merged.items())):
        eq = db.query(Equipment).filter(Equipment.id == eq_id).with_for_update().first()
        if not eq:
            raise HTTPException(404, f"Equipment #{eq_id} not found")
        if eq.lab_id != lab.id:
            raise HTTPException(400, f"{eq.name} does not belong to {lab.name}")
        if qty > eq.available_qty:
            raise HTTPException(400, f"Only {eq.available_qty} x {eq.name} available (requested {qty})")
        eq.available_qty -= qty
        eq.issued_qty += qty
        issue = Issue(student_id=student.id, equipment_id=eq.id, lab_id=lab.id, quantity=qty,
                      issue_date=t, due_date=t + timedelta(days=loan_days),
                      issued_by=staff.id, notes=notes[:255],
                      request_id=f"{request_id}:{idx}" if request_id else None)
        db.add(issue)
        created.append(issue)
        audit(db, staff, "issue", f"{qty} x {eq.name} to {student.name} ({student.university_uid})")
    db.commit()
    after_issue(db, staff, student, created)
    return created


# --------------------------------------------------------------- returning
def return_items(db: Session, staff: User, items: list) -> List[dict]:
    cfg = get_settings(db)
    rate = fine_rate(cfg)
    results = []
    done = []
    for it in sorted(items, key=lambda x: x.issue_id):
        issue = db.query(Issue).filter(Issue.id == it.issue_id).with_for_update().first()
        if not issue:
            raise HTTPException(404, f"Issue #{it.issue_id} not found")
        if issue.status != "issued":
            raise HTTPException(400, f"Issue #{issue.id} is already closed")
        if it.quantity > outstanding(issue):
            raise HTTPException(400, f"Only {outstanding(issue)} unit(s) still outstanding on issue #{issue.id}")
        eq = db.query(Equipment).filter(Equipment.id == issue.equipment_id).with_for_update().first()

        t = now()
        od = overdue_days(issue.due_date, t)
        fine = round(od * rate * it.quantity, 2)

        eq.issued_qty -= it.quantity
        if it.condition == "good":
            eq.available_qty += it.quantity
        elif it.condition == "damaged":
            eq.damaged_qty += it.quantity
        else:
            eq.missing_qty += it.quantity

        issue.returned_qty += it.quantity
        issue.fine_total = round(issue.fine_total + fine, 2)
        if issue.fine_total > 0 and issue.fine_status == "none":
            issue.fine_status = "pending"
        if outstanding(issue) == 0:
            issue.status = "returned"
            issue.closed_at = t

        db.add(ReturnEvent(issue_id=issue.id, quantity=it.quantity, condition=it.condition,
                           overdue_days=od, fine_amount=fine, returned_at=t, received_by=staff.id))
        audit(db, staff, "return",
              f"{it.quantity} x {eq.name} ({it.condition}) from issue #{issue.id}, fine {fine}")
        results.append({"issue_id": issue.id, "equipment": eq.name, "quantity": it.quantity,
                        "condition": it.condition, "overdue_days": od, "fine": fine})
        done.append((issue, it.quantity, it.condition, od, fine))
    db.commit()
    after_return(db, staff, done)
    return results


# ---------------------------------------------------------------- renewing
def renew_issue(db: Session, staff: User, issue_id: int) -> Issue:
    cfg = get_settings(db)
    issue = db.query(Issue).filter(Issue.id == issue_id).with_for_update().first()
    if not issue:
        raise HTTPException(404, "Issue not found")
    if issue.status != "issued":
        raise HTTPException(400, "This loan is already closed")
    if issue.renewed:
        raise HTTPException(400, "This loan was already renewed once")
    if cfg["renew_after_due"].lower() != "true" and overdue_days(issue.due_date, now()) > 0:
        raise HTTPException(400, "Overdue loans cannot be renewed. Return the items first.")
    issue.due_date = issue.due_date + timedelta(days=int(cfg["renew_days"]))
    issue.renewed = True
    issue.renewed_at = now()
    audit(db, staff, "renew", f"issue #{issue.id} new due {issue.due_date.date()}")
    db.commit()
    return issue


# ------------------------------------------------- issue verification code
def items_fingerprint(items) -> str:
    """Canonical text for a list of (equipment_id, quantity); the code is bound to exactly this list."""
    merged = {}
    for it in items:
        merged[it.equipment_id] = merged.get(it.equipment_id, 0) + it.quantity
    return ",".join(f"{k}:{v}" for k, v in sorted(merged.items()))


def _hash_code(student_id: int, code: str, fingerprint: str) -> str:
    msg = f"{student_id}:{code}:{fingerprint}".encode()
    return hmac.new(config.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "the registered email"


def require_recent_scan(db: Session, student: Student, lab_id: int) -> None:
    """Equipment can only be issued if this student's own card was tapped on the reader recently."""
    since = now() - timedelta(minutes=config.SCAN_VALID_MIN)
    hit = (db.query(RfidScan.id)
           .filter(RfidScan.student_id == student.id, RfidScan.result == "recognised",
                   RfidScan.lab_id == lab_id, RfidScan.created_at >= since).first())
    if not hit:
        raise HTTPException(400, "Scan this student's card on this laboratory's reader first "
                                 f"(valid for {config.SCAN_VALID_MIN} minutes).")


def send_issue_code(db: Session, staff: User, student: Student, items: list, lab: Lab) -> dict:
    """Email ONE fresh 6-digit code that approves the whole list of items, and nothing else."""
    if not student.is_active:
        raise HTTPException(400, "This student account is inactive")
    if not student.email:
        raise HTTPException(400, "This student has no email address on record")
    require_recent_scan(db, student, lab.id)

    merged = {}
    for it in items:
        merged[it.equipment_id] = merged.get(it.equipment_id, 0) + it.quantity
    if not merged:
        raise HTTPException(400, "Add at least one item before sending the code")
    lines = []
    for eq_id, qty in sorted(merged.items()):
        eq = db.get(Equipment, eq_id)
        if not eq:
            raise HTTPException(404, f"Equipment #{eq_id} not found")
        if eq.lab_id != lab.id:
            raise HTTPException(400, f"{eq.name} does not belong to {lab.name}")
        if qty > eq.available_qty:
            raise HTTPException(400, f"Only {eq.available_qty} x {eq.name} available (requested {qty})")
        lines.append(f"  - {qty} x {eq.name}")
    fingerprint = items_fingerprint(items)

    t = now()
    last = (db.query(IssueCode).filter(IssueCode.student_id == student.id)
            .order_by(IssueCode.id.desc()).first())
    if last:
        wait = config.CODE_COOLDOWN_SEC - (t - last.created_at).total_seconds()
        if wait > 0:
            raise HTTPException(429, f"Please wait {math.ceil(wait)} second(s) before sending another code")

    cfg = get_settings(db)
    due = (t + timedelta(days=int(cfg["loan_days"]))).strftime("%d %b %Y")
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db.query(IssueCode).filter(IssueCode.student_id == student.id, IssueCode.used.is_(False)).update({"used": True})
    db.add(IssueCode(student_id=student.id, code_hash=_hash_code(student.id, code, fingerprint),
                     sent_to=student.email, created_by=staff.id, created_at=t,
                     expires_at=t + timedelta(minutes=config.CODE_MINUTES), attempts=0, used=False))
    db.flush()
    n = sum(merged.values())
    try:
        send_email(
            student.email,
            f"Lab equipment code: {code} ({len(merged)} item(s), {n} unit(s))",
            f"Hello {student.name},\n\nYou are collecting the following equipment:\n\n" + "\n".join(lines) +
            f"\n\nReturn by: {due}\n\nYour verification code for this whole list is:\n\n    {code}\n\n"
            f"Give it to the lab staff only if the list above is correct. It works once, only for this exact "
            f"list, and expires in {config.CODE_MINUTES} minutes. If you did not ask for equipment, ignore "
            f"this email.\n\nElectronics Department, University Institute of Computing",
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(502, f"Could not send the email: {e}")
    audit(db, staff, "send_issue_code", f"to {student.name} ({student.university_uid}) for {fingerprint}")
    db.commit()
    return {"sent_to": mask_email(student.email), "expires_in": config.CODE_MINUTES * 60,
            "cooldown": config.CODE_COOLDOWN_SEC, "items": len(merged), "units": n}


def consume_issue_code(db: Session, student: Student, code: str, fingerprint: str) -> None:
    """Check the code against this exact item list. Marked used here, committed together with the issue."""
    row = (db.query(IssueCode).filter(IssueCode.student_id == student.id, IssueCode.used.is_(False))
           .order_by(IssueCode.id.desc()).first())
    if not row or row.expires_at < now():
        raise HTTPException(400, "No valid code. Send the code to the student's email.")
    if row.attempts >= config.CODE_MAX_ATTEMPTS:
        raise HTTPException(400, "Too many wrong attempts. Send a new code.")
    if not hmac.compare_digest(row.code_hash, _hash_code(student.id, code, fingerprint)):
        row.attempts += 1
        left = config.CODE_MAX_ATTEMPTS - row.attempts
        audit(db, None, "issue_code_wrong", f"student {student.university_uid}")
        db.commit()
        raise HTTPException(400, f"Wrong code, or the item list changed after the code was sent. "
                                 f"{left} attempt(s) left." if left > 0
                            else "Wrong code. Too many attempts, send a new code.")
    row.used = True


# ------------------------------------------- OLED messages and student emails
def fit(text: str, n: int = 21) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "."


def push_display(db: Session, lab_id: int, title: str, l1: str = "", l2: str = "", l3: str = "", ms: int = 4000) -> None:
    """Queue a screen for the readers of one lab. A reader fetches it within a few seconds."""
    m = DeviceMessage(lab_id=lab_id, title=fit(title), line1=fit(l1), line2=fit(l2), line3=fit(l3), show_ms=ms)
    db.add(m)
    db.flush()
    state.latest_msg[lab_id] = max(state.latest_msg.get(lab_id, 0), m.id)
    db.query(DeviceMessage).filter(DeviceMessage.created_at < now() - timedelta(days=1)).delete()


def run_background(fn) -> None:
    """Run fn off the request thread (an email must never slow down or break an issue/return)."""
    threading.Thread(target=fn, daemon=True).start()


def email_in_background(kind: str, to: str, subject: str, body: str) -> None:
    def work():
        from .db import SessionLocal
        with SessionLocal() as db:
            n = Notification(issue_id=None, kind=kind, to_email=to)
            db.add(n)
            try:
                send_email(to, subject, body)
                n.status, n.sent_at = "sent", now()
            except Exception as e:
                n.status, n.error = "failed", str(e)[:500]
            db.commit()
    run_background(work)


def _pending(db: Session, student_id: int, exclude=()) -> list:
    rows = []
    for i in (db.query(Issue).filter(Issue.student_id == student_id, Issue.status == "issued")
              .order_by(Issue.due_date).all()):
        out = outstanding(i)
        if i.id in exclude or out <= 0:
            continue
        rows.append((i, out, (i.due_date.date() - now().date()).days))
    return rows


def _pending_line(i: Issue, out: int, left: int, rate: float, cur: str, show_lab: bool = False) -> str:
    due = i.due_date.strftime("%d %b %Y")
    where = f" [{i.lab.name}]" if show_lab and i.lab else ""
    if left > 0:
        return f"  - {out} x {i.equipment.name}{where}: due {due} ({left} day(s) left)"
    if left == 0:
        return f"  - {out} x {i.equipment.name}{where}: DUE TODAY ({due})"
    return (f"  - {out} x {i.equipment.name}{where}: was due {due}, OVERDUE by {-left} day(s), "
            f"fine so far {cur}{round(-left * rate * out, 2):.2f}")


def _pending_block(db, student_id, rate, cur, heading, exclude=(), none_text="") -> str:
    rows = _pending(db, student_id, exclude)
    if not rows:
        return f"\n{none_text}\n" if none_text else ""
    show = db.query(Lab).count() > 1
    return f"\n{heading}\n" + "\n".join(_pending_line(i, o, l, rate, cur, show) for i, o, l in rows) + "\n"


_SIGN = "\nElectronics Department, University Institute of Computing"


def after_issue(db: Session, staff: User, student: Student, created: List[Issue]) -> None:
    """OLED screens + one receipt email listing everything issued. Never raises."""
    try:
        cfg = get_settings(db)
        rate, cur = fine_rate(cfg), cfg["currency"]
        n = len(created)
        for idx, i in enumerate(created, 1):
            push_display(db, i.lab_id, "ISSUED", student.name, i.equipment.name,
                         f"Qty {i.quantity}" + (f"  ({idx}/{n})" if n > 1 else ""))
        db.commit()
        if student.email:
            lines = "\n".join(f"  - {i.quantity} x {i.equipment.name}  (return by {i.due_date.strftime('%d %b %Y')})"
                              for i in created)
            body = (f"Hello {student.name},\n\nThe following equipment was issued to you on "
                    f"{now().strftime('%d %b %Y, %H:%M')} by {staff.full_name} at {created[0].lab.name if created[0].lab else 'the laboratory'}:\n\n{lines}\n"
                    + _pending_block(db, student.id, rate, cur, "Your other pending items:", {i.id for i in created})
                    + _SIGN)
            units = sum(i.quantity for i in created)
            email_in_background(f"issue_receipt_{created[0].id}", student.email,
                                f"Equipment issued: {units} unit(s) in {n} item(s)", body)
    except Exception:
        db.rollback()
        log.exception("after_issue failed")


_RET_TITLE = {"good": "RETURNED", "damaged": "RETURNED DAMAGED", "missing": "MARKED MISSING"}


def after_return(db: Session, staff: User, done: list) -> None:
    """OLED screens + one receipt email per student for what was just returned. Never raises."""
    try:
        cfg = get_settings(db)
        rate, cur = fine_rate(cfg), cfg["currency"]
        by_student = {}
        for issue, qty, cond, od, fine in done:
            by_student.setdefault(issue.student_id, []).append((issue, qty, cond, od, fine))
            extra = f"  Fine {cur}{fine:g}" if fine > 0 else ""
            push_display(db, issue.lab_id, _RET_TITLE[cond], issue.student.name, issue.equipment.name, f"Qty {qty}{extra}")
        db.commit()
        for sid, rows in by_student.items():
            student = rows[0][0].student
            if not student.email:
                continue
            lines, total = [], 0.0
            for issue, qty, cond, od, fine in rows:
                note = {"good": "returned in good condition", "damaged": "returned DAMAGED",
                        "missing": "marked MISSING"}[cond]
                late = f", {od} day(s) late, fine {cur}{fine:.2f}" if od > 0 else ""
                lines.append(f"  - {qty} x {issue.equipment.name}: {note}{late}")
                total += fine
            fine_text = f"\nFine charged now: {cur}{total:.2f}. Please settle it at the department.\n" if total > 0 else ""
            body = (f"Hello {student.name},\n\nWe received the following from you on "
                    f"{now().strftime('%d %b %Y, %H:%M')} (handled by {staff.full_name}):\n\n" + "\n".join(lines) + "\n"
                    + fine_text
                    + _pending_block(db, sid, rate, cur, "Still pending with you:", (),
                                     "You have no other pending items. Thank you!")
                    + _SIGN)
            email_in_background(f"return_receipt_{rows[0][0].id}_{int(now().timestamp())}", student.email,
                                f"Equipment returned: {sum(r[1] for r in rows)} unit(s)", body)
    except Exception:
        db.rollback()
        log.exception("after_return failed")


def run_reminders(db: Session) -> dict:
    """One email per student per day listing everything pending, when any item is due soon or overdue."""
    cfg = get_settings(db)
    rate, cur = fine_rate(cfg), cfg["currency"]
    days = [int(x) for x in cfg["reminder_days"].split(",") if x.strip().isdigit()]
    today = now().date()
    show_lab = db.query(Lab).count() > 1
    by_student = {}
    for i in db.query(Issue).filter(Issue.status == "issued").all():
        if outstanding(i) > 0:
            by_student.setdefault(i.student_id, []).append(i)

    sent = failed = skipped = 0
    for sid, issues in by_student.items():
        student = issues[0].student
        due_now, others = [], []
        for i in sorted(issues, key=lambda x: x.due_date):
            left = (i.due_date.date() - today).days
            hit = left in days or (left < 0 and (-left == 1 or (-left) % 7 == 0))
            (due_now if hit else others).append((i, outstanding(i), left))
        if not due_now:
            continue
        if not student.email:
            skipped += 1
            continue
        kind = f"digest_s{sid}_{today}"
        n = db.query(Notification).filter(Notification.kind == kind).first()
        if n and n.status == "sent":
            continue
        if not n:
            n = Notification(issue_id=None, kind=kind, to_email=student.email)
            db.add(n)
        overdue = any(left < 0 for _, _, left in due_now)
        body = (f"Hello {student.name},\n\n"
                + ("Some of your lab equipment is OVERDUE or due very soon.\n\nNeeds your attention:\n"
                   if overdue else "Some of your lab equipment is due soon.\n\nNeeds your attention:\n")
                + "\n".join(_pending_line(i, o, l, rate, cur, show_lab) for i, o, l in due_now) + "\n")
        if others:
            body += "\nOther items you still have:\n" + "\n".join(_pending_line(i, o, l, rate, cur, show_lab) for i, o, l in others) + "\n"
        body += f"\nLate fine: {cur}{rate:g} per unit per day. Please return the items to the laboratory.\n" + _SIGN
        subject = ("OVERDUE lab equipment: " if overdue else "Reminder, lab equipment due: ") + \
                  ", ".join(f"{o} x {i.equipment.name}" for i, o, _ in due_now)[:120]
        try:
            send_email(student.email, subject, body)
            n.status, n.sent_at, n.error = "sent", now(), ""
            sent += 1
        except Exception as e:
            n.status, n.error = "failed", str(e)[:500]
            failed += 1
        db.commit()
    return {"sent": sent, "failed": failed, "skipped_no_email": skipped}
