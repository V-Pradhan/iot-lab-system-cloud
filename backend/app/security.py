import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from typing import List, Optional

from .config import SECRET_KEY, TOKEN_HOURS
from .db import get_db
from .models import Lab, StaffLab, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm="HS256")


def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not creds:
        raise HTTPException(401, "Not signed in")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=["HS256"])
        user = db.get(User, int(payload["sub"]))
    except Exception:
        raise HTTPException(401, "Session expired. Sign in again.")
    if not user or not user.is_active:
        raise HTTPException(401, "Account disabled")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(403, "You do not have permission for this action")
        return user
    return checker


STAFF = ("admin", "teacher", "lab_assistant")
ADMIN = ("admin",)


def hash_device_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def accessible_labs(db: Session, user: User) -> List[Lab]:
    """Administrators can use every active lab; other staff only the labs assigned to them."""
    q = db.query(Lab).filter(Lab.is_active.is_(True))
    if user.role != "admin":
        q = q.join(StaffLab, StaffLab.lab_id == Lab.id).filter(StaffLab.user_id == user.id)
    return q.order_by(Lab.id).all()


def get_lab(x_lab_id: Optional[int] = Header(default=None), user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> Lab:
    """The laboratory the staff member is currently working in (sent by the web app in X-Lab-Id)."""
    labs = accessible_labs(db, user)
    if not labs:
        raise HTTPException(403, "No laboratory is assigned to your account. Ask the administrator.")
    if x_lab_id is None:
        return labs[0]
    for lab in labs:
        if lab.id == x_lab_id:
            return lab
    raise HTTPException(403, "You do not have access to this laboratory")


def can_access_lab(db: Session, user: User, lab_id: Optional[int]) -> bool:
    return lab_id is not None and any(l.id == lab_id for l in accessible_labs(db, user))
