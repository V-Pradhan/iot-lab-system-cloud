import os
from dotenv import load_dotenv

load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


DATABASE_URL = env("DATABASE_URL", "sqlite:///./lab.db")
SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")
TOKEN_HOURS = int(env("TOKEN_HOURS", "10"))
DEVICE_KEY = env("DEVICE_KEY", "change-this-secret")
TIMEZONE = env("TIMEZONE", "Asia/Kolkata")
CORS_ORIGINS = [o.strip() for o in env("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]

ADMIN_USERNAME = env("ADMIN_USERNAME", "admin").lower()
ADMIN_PASSWORD = env("ADMIN_PASSWORD", "admin12345")

SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER")
SMTP_PASSWORD = env("SMTP_PASSWORD")
SMTP_FROM = env("SMTP_FROM") or env("SMTP_USER")
REMINDER_INTERVAL_MIN = int(env("REMINDER_INTERVAL_MIN", "60"))

# Issue verification (emailed one-time code + mandatory card scan)
CODE_MINUTES = int(env("CODE_MINUTES", "5"))            # how long a code stays valid
CODE_MAX_ATTEMPTS = int(env("CODE_MAX_ATTEMPTS", "3"))  # wrong tries before the code is dead
CODE_COOLDOWN_SEC = int(env("CODE_COOLDOWN_SEC", "10"))  # minimum gap between code emails
SCAN_VALID_MIN = int(env("SCAN_VALID_MIN", "10"))       # card scan must be this recent to issue


# ----- cloud deployment -----
APP_ENV = env("APP_ENV", "development")                 # set to "production" on the live server
DB_SSL = env("DB_SSL", "false").lower() == "true"       # TiDB Cloud and most hosted MySQL need this
PUBLIC_URL = env("PUBLIC_URL", "").rstrip("/")          # e.g. https://your-app.onrender.com
CRON_TOKEN = env("CRON_TOKEN", "")                      # lets a free cron service trigger reminders

# ----- e-mail: "smtp" (local PC) or "gmail_api" (needed on free cloud hosts, which block SMTP) -----
EMAIL_PROVIDER = env("EMAIL_PROVIDER", "smtp")
MAIL_FROM_NAME = env("MAIL_FROM_NAME", "Electronics Department")
GMAIL_CLIENT_ID = env("GMAIL_CLIENT_ID")
GMAIL_CLIENT_SECRET = env("GMAIL_CLIENT_SECRET")
GMAIL_REFRESH_TOKEN = env("GMAIL_REFRESH_TOKEN")
GMAIL_SENDER = env("GMAIL_SENDER")                      # the Gmail address that sends the mail

# ----- laboratories -----
DEFAULT_LAB_NAME = env("DEFAULT_LAB_NAME", "Electronics Laboratory")
DEFAULT_LAB_CODE = env("DEFAULT_LAB_CODE", "ELEC").upper()
