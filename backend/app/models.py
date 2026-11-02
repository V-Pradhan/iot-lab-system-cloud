from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .config import TIMEZONE
from .db import Base


def now() -> datetime:
    """Current local time (naive) in the configured timezone."""
    return datetime.now(ZoneInfo(TIMEZONE)).replace(tzinfo=None)


class User(Base):
    """Staff accounts: administrator, teacher, lab_assistant."""
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(120), default="")
    employee_id: Mapped[Optional[str]] = mapped_column(String(30), unique=True, nullable=True)
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Student(Base):
    """Borrowers. They cannot log in."""
    __tablename__ = "students"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    university_uid: Mapped[str] = mapped_column(String(30), unique=True)
    class_section: Mapped[str] = mapped_column(String(40))
    mobile: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(120))
    course: Mapped[str] = mapped_column(String(80), default="")
    department: Mapped[str] = mapped_column(String(80), default="")
    registered_lab_id: Mapped[Optional[int]] = mapped_column(ForeignKey("labs.id"), nullable=True)
    rfid_uid: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Equipment(Base):
    """Quantity-based stock. total = available + issued + damaged + missing + maintenance."""
    __tablename__ = "equipment"
    __table_args__ = (UniqueConstraint("lab_id", "name", name="uq_equipment_lab_name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[Optional[int]] = mapped_column(ForeignKey("labs.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60), default="")
    total_qty: Mapped[int] = mapped_column(Integer, default=0)
    available_qty: Mapped[int] = mapped_column(Integer, default=0)
    issued_qty: Mapped[int] = mapped_column(Integer, default=0)
    damaged_qty: Mapped[int] = mapped_column(Integer, default=0)
    missing_qty: Mapped[int] = mapped_column(Integer, default=0)
    maintenance_qty: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(String(255), default="")


class Issue(Base):
    """One equipment line issued to one student."""
    __tablename__ = "issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    lab_id: Mapped[Optional[int]] = mapped_column(ForeignKey("labs.id"), nullable=True, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    returned_qty: Mapped[int] = mapped_column(Integer, default=0)
    issue_date: Mapped[datetime] = mapped_column(DateTime, default=now)
    due_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    renewed: Mapped[bool] = mapped_column(Boolean, default=False)
    renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="issued", index=True)  # issued | returned
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[Optional[str]] = mapped_column(String(80), unique=True, nullable=True)
    fine_total: Mapped[float] = mapped_column(Float, default=0.0)
    fine_status: Mapped[str] = mapped_column(String(10), default="none")  # none|pending|paid|waived
    notes: Mapped[str] = mapped_column(String(255), default="")

    student = relationship("Student")
    equipment = relationship("Equipment")
    lab = relationship("Lab")
    issuer = relationship("User", foreign_keys=[issued_by])
    returns = relationship("ReturnEvent", back_populates="issue", order_by="ReturnEvent.id")


class ReturnEvent(Base):
    __tablename__ = "return_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    condition: Mapped[str] = mapped_column(String(10), default="good")  # good|damaged|missing
    overdue_days: Mapped[int] = mapped_column(Integer, default=0)
    fine_amount: Mapped[float] = mapped_column(Float, default=0.0)
    returned_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    received_by: Mapped[int] = mapped_column(ForeignKey("users.id"))

    issue = relationship("Issue", back_populates="returns")
    receiver = relationship("User")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (UniqueConstraint("issue_id", "kind", name="uq_notification_issue_kind"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[Optional[int]] = mapped_column(ForeignKey("issues.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(80))
    to_email: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending|sent|failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")


class RfidScan(Base):
    __tablename__ = "rfid_scans"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(40))
    lab_id: Mapped[Optional[int]] = mapped_column(ForeignKey("labs.id"), nullable=True, index=True)
    uid: Mapped[str] = mapped_column(String(20), index=True)
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("students.id"), nullable=True)
    result: Mapped[str] = mapped_column(String(20))  # recognised|unregistered|inactive|captured|in_use
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    student = relationship("Student")


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class IssueCode(Base):
    """One-time code emailed to a student before equipment can be issued to them."""
    __tablename__ = "issue_codes"
    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    sent_to: Mapped[str] = mapped_column(String(120))
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class DeviceMessage(Base):
    """A screen for the reader's OLED (issue / return details). Readers poll for new ones."""
    __tablename__ = "device_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[Optional[int]] = mapped_column(ForeignKey("labs.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(30))
    line1: Mapped[str] = mapped_column(String(40), default="")
    line2: Mapped[str] = mapped_column(String(40), default="")
    line3: Mapped[str] = mapped_column(String(40), default="")
    show_ms: Mapped[int] = mapped_column(Integer, default=4000)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Lab(Base):
    """A laboratory that uses the system. Stock, loans, readers and staff access are kept per lab."""
    __tablename__ = "labs"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)   # used in the registration QR link
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class StaffLab(Base):
    """Which laboratories a teacher or lab assistant may work in (administrators see all)."""
    __tablename__ = "staff_labs"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id"), primary_key=True)


class Device(Base):
    """One RFID reader. It has its own key and belongs to exactly one lab."""
    __tablename__ = "devices"
    id: Mapped[int] = mapped_column(primary_key=True)
    device_id: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100), default="")
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id"), index=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_seen: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    lab = relationship("Lab")


class RegistrationRequest(Base):
    """A student's self-registration (from the QR form). Staff approve it and link the RFID card."""
    __tablename__ = "registration_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    university_uid: Mapped[str] = mapped_column(String(30), index=True)
    course: Mapped[str] = mapped_column(String(80), default="")
    department: Mapped[str] = mapped_column(String(80), default="")
    class_section: Mapped[str] = mapped_column(String(40), default="")
    mobile: Mapped[str] = mapped_column(String(20))
    email: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING|APPROVED|REJECTED|NEEDS_CORRECTION
    note: Mapped[str] = mapped_column(String(300), default="")
    student_id: Mapped[Optional[int]] = mapped_column(ForeignKey("students.id"), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    lab = relationship("Lab")


class InventoryLog(Base):
    """Every change to stock (who, what, old and new quantities, why)."""
    __tablename__ = "inventory_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    lab_id: Mapped[int] = mapped_column(ForeignKey("labs.id"), index=True)
    equipment_id: Mapped[int] = mapped_column(ForeignKey("equipment.id"), index=True)
    equipment_name: Mapped[str] = mapped_column(String(120))
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(20))        # add | update
    change: Mapped[str] = mapped_column(String(400), default="")
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    user = relationship("User")
