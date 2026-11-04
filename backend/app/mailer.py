
"""Email delivery using SMTP or the Gmail API.

EMAIL_PROVIDER=smtp       Use an SMTP server.
EMAIL_PROVIDER=gmail_api  Use Gmail API over HTTPS.
"""

import base64
import hashlib
import logging
import smtplib
import time

from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import config


logger = logging.getLogger(__name__)

# Cache the access token in memory.
_token = {
    "value": None,
    "exp": 0.0,
}


def _build(to: str, subject: str, body: str, sender: str) -> EmailMessage:
    """Build a plain-text email."""
    msg = EmailMessage()
    msg["From"] = formataddr((config.MAIL_FROM_NAME, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    return msg


# ---------------------------------------------------------------------------
# SMTP
# ---------------------------------------------------------------------------

def _send_smtp(to: str, subject: str, body: str) -> None:
    """Send email using SMTP."""

    if not (config.SMTP_HOST and config.SMTP_FROM):
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST and SMTP_FROM."
        )

    msg = _build(to, subject, body, config.SMTP_FROM)

    if config.SMTP_PORT == 465:
        server = smtplib.SMTP_SSL(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=20,
        )
    else:
        server = smtplib.SMTP(
            config.SMTP_HOST,
            config.SMTP_PORT,
            timeout=20,
        )
        server.starttls()

    with server:
        if config.SMTP_USER:
            server.login(
                config.SMTP_USER,
                config.SMTP_PASSWORD,
            )

        server.send_message(msg)


# ---------------------------------------------------------------------------
# Gmail API authentication
# ---------------------------------------------------------------------------

def _access_token(force: bool = False) -> str:
    """Obtain an access token using the configured refresh token."""

    # Reuse an unexpired access token unless a forced refresh is requested.
    if (
        not force
        and _token["value"]
        and time.time() < _token["exp"] - 60
    ):
        return _token["value"]

    # Validate required configuration.
    required = {
        "GMAIL_CLIENT_ID": config.GMAIL_CLIENT_ID,
        "GMAIL_CLIENT_SECRET": config.GMAIL_CLIENT_SECRET,
        "GMAIL_REFRESH_TOKEN": config.GMAIL_REFRESH_TOKEN,
        "GMAIL_SENDER": config.GMAIL_SENDER,
    }

    missing = [
        name for name, value in required.items()
        if not value or not value.strip()
    ]

    if missing:
        raise RuntimeError(
            "Gmail API configuration is incomplete. Missing: "
            + ", ".join(missing)
        )

    # Safe diagnostic information. Never log actual credentials.
    client_fingerprint = hashlib.sha256(
        config.GMAIL_CLIENT_ID.encode("utf-8")
    ).hexdigest()[:12]

    logger.warning(
        "GMAIL DIAGNOSTICS: provider=%s "
        "client_id_fingerprint=%s "
        "client_id_length=%s "
        "client_secret_present=%s "
        "refresh_token_present=%s "
        "sender_present=%s",
        config.EMAIL_PROVIDER,
        client_fingerprint,
        len(config.GMAIL_CLIENT_ID),
        bool(config.GMAIL_CLIENT_SECRET),
        bool(config.GMAIL_REFRESH_TOKEN),
        bool(config.GMAIL_SENDER),
    )

    # Exchange the refresh token for a new access token.
    token_url = "https://oauth2.googleapis.com/token"

    try:
        response = httpx.post(
            token_url,
            timeout=25,
            data={
                "client_id": config.GMAIL_CLIENT_ID,
                "client_secret": config.GMAIL_CLIENT_SECRET,
                "refresh_token": config.GMAIL_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
        )

    except httpx.HTTPError as exc:
        logger.exception(
            "Gmail OAuth token endpoint connection failed."
        )
        raise RuntimeError(
            f"Could not connect to Google's OAuth service: "
            f"{type(exc).__name__}"
        ) from exc

    if response.status_code != 200:
        # Clear any previously cached token.
        _token["value"] = None
        _token["exp"] = 0.0

        try:
            error_data = response.json()
        except ValueError:
            error_data = {}

        error_code = error_data.get("error", "unknown_error")
        error_description = error_data.get(
            "error_description",
            "No error description supplied.",
        )

        logger.error(
            "Gmail OAuth failed: HTTP %s, error=%s, description=%s",
            response.status_code,
            error_code,
            error_description,
        )

        raise RuntimeError(
            f"Gmail sign-in failed ({response.status_code}): "
            f"{error_code} - {error_description}"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Google returned an invalid token response."
        ) from exc

    access_token = data.get("access_token")

    if not access_token:
        raise RuntimeError(
            "Google authentication response did not contain "
            "an access token."
        )

    expires_in = int(data.get("expires_in", 3600))

    _token["value"] = access_token
    _token["exp"] = time.time() + expires_in

    logger.info(
        "Gmail OAuth authentication successful. "
        "Access token expires in %s seconds.",
        expires_in,
    )

    return access_token


# ---------------------------------------------------------------------------
# Gmail API email delivery
# ---------------------------------------------------------------------------

def _send_gmail_api(
    to: str,
    subject: str,
    body: str,
) -> None:
    """Send an email through the Gmail API."""

    msg = _build(
        to,
        subject,
        body,
        config.GMAIL_SENDER,
    )

    raw = base64.urlsafe_b64encode(
        msg.as_bytes()
    ).decode("utf-8")

    url = (
        "https://gmail.googleapis.com/"
        "gmail/v1/users/me/messages/send"
    )

    for attempt in range(2):

        access_token = _access_token(
            force=(attempt == 1)
        )

        try:
            response = httpx.post(
                url,
                json={"raw": raw},
                timeout=25,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )

        except httpx.HTTPError as exc:
            logger.exception(
                "Gmail API request failed."
            )
            raise RuntimeError(
                f"Gmail API connection failed: "
                f"{type(exc).__name__}"
            ) from exc

        # If the access token is rejected, refresh it once.
        if response.status_code == 401 and attempt == 0:
            logger.warning(
                "Gmail API returned 401. Refreshing access token once."
            )
            _token["value"] = None
            _token["exp"] = 0.0
            continue

        if response.status_code >= 300:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {}

            error_message = error_data.get(
                "error", response.text[:200]
            )

            logger.error(
                "Gmail API send failed: HTTP %s, error=%s",
                response.status_code,
                str(error_message)[:200],
            )

            raise RuntimeError(
                f"Gmail API error {response.status_code}: "
                f"{str(error_message)[:200]}"
            )

        logger.info(
            "Gmail API email successfully accepted for delivery."
        )
        return

    raise RuntimeError(
        "Gmail API authentication failed after token refresh."
    )


# ---------------------------------------------------------------------------
# Public email function
# ---------------------------------------------------------------------------

def send_email(
    to: str,
    subject: str,
    body: str,
) -> None:
    """Send one email using the configured provider."""

    provider = config.EMAIL_PROVIDER.strip().lower()

    if provider == "gmail_api":
        logger.info("Sending email using Gmail API.")
        _send_gmail_api(to, subject, body)

    elif provider == "smtp":
        logger.info("Sending email using SMTP.")
        _send_smtp(to, subject, body)

    else:
        raise RuntimeError(
            f"Unsupported EMAIL_PROVIDER: {provider}"
        )
