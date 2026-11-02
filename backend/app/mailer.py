"""Sending e-mail.

EMAIL_PROVIDER=smtp       any SMTP server (fine on your own PC)
EMAIL_PROVIDER=gmail_api  the Gmail API over HTTPS. Use this on free cloud hosts, which block SMTP ports.
"""
import base64
import smtplib
import time
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import config

_token = {"value": None, "exp": 0.0}


def _build(to: str, subject: str, body: str, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((config.MAIL_FROM_NAME, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


# --------------------------------------------------------------------------- SMTP
def _send_smtp(to: str, subject: str, body: str) -> None:
    if not (config.SMTP_HOST and config.SMTP_FROM):
        raise RuntimeError("SMTP is not configured (set SMTP_HOST / SMTP_FROM)")
    msg = _build(to, subject, body, config.SMTP_FROM)
    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
    else:
        server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20)
        server.starttls()
    with server:
        if config.SMTP_USER:
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
        server.send_message(msg)


# --------------------------------------------------------------------------- Gmail API
def _access_token(force: bool = False) -> str:
    if not force and _token["value"] and time.time() < _token["exp"] - 60:
        return _token["value"]
    if not (config.GMAIL_CLIENT_ID and config.GMAIL_CLIENT_SECRET and config.GMAIL_REFRESH_TOKEN and config.GMAIL_SENDER):
        raise RuntimeError("Gmail API is not configured (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER)")
    r = httpx.post("https://oauth2.googleapis.com/token", timeout=20, data={
        "client_id": config.GMAIL_CLIENT_ID, "client_secret": config.GMAIL_CLIENT_SECRET,
        "refresh_token": config.GMAIL_REFRESH_TOKEN, "grant_type": "refresh_token"})
    if r.status_code != 200:
        raise RuntimeError(f"Gmail sign-in failed ({r.status_code}): {r.text[:200]}")
    data = r.json()
    _token["value"] = data["access_token"]
    _token["exp"] = time.time() + int(data.get("expires_in", 3600))
    return _token["value"]


def _send_gmail_api(to: str, subject: str, body: str) -> None:
    raw = base64.urlsafe_b64encode(_build(to, subject, body, config.GMAIL_SENDER).as_bytes()).decode()
    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    for attempt in (0, 1):
        r = httpx.post(url, json={"raw": raw}, timeout=20, headers={"Authorization": f"Bearer {_access_token(force=attempt == 1)}"})
        if r.status_code == 401 and attempt == 0:
            continue                       # token expired: refresh once and retry
        if r.status_code >= 300:
            raise RuntimeError(f"Gmail API error {r.status_code}: {r.text[:200]}")
        return


def send_email(to: str, subject: str, body: str) -> None:
    """Send one plain-text e-mail. Raises on any failure so callers can record it."""
    if config.EMAIL_PROVIDER == "gmail_api":
        _send_gmail_api(to, subject, body)
    else:
        _send_smtp(to, subject, body)
