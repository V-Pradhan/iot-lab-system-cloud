import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from . import config
from .db import SessionLocal
from .logic import run_reminders
from .migrate import bootstrap, run_migrations
from .models import User
from .routers import auth_staff, circulation, inventory, labs, registrations, reports, rfid, students
from .security import hash_password

log = logging.getLogger("lab")


def check_production_settings() -> None:
    """On the live server, refuse to start with the example secrets."""
    if config.APP_ENV != "production":
        return
    problems = []
    if config.SECRET_KEY.startswith("dev-only") or len(config.SECRET_KEY) < 32:
        problems.append("SECRET_KEY must be a random string of at least 32 characters")
    if config.DEVICE_KEY == "change-this-secret":
        problems.append("DEVICE_KEY must be changed")
    if problems:
        raise RuntimeError("Unsafe settings for production: " + "; ".join(problems))


def ensure_admin() -> None:
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            if config.APP_ENV == "production" and config.ADMIN_PASSWORD == "admin12345":
                raise RuntimeError("Set ADMIN_PASSWORD to your own value before the first start in production")
            db.add(User(username=config.ADMIN_USERNAME, full_name="Administrator", role="admin",
                        password_hash=hash_password(config.ADMIN_PASSWORD), must_change_password=True))
            db.commit()
            log.warning("Created first admin '%s'. Sign in and change the password.", config.ADMIN_USERNAME)


def reminder_job():
    with SessionLocal() as db:
        return run_reminders(db)


async def reminder_loop():
    await asyncio.sleep(30)
    while True:
        try:
            result = await asyncio.to_thread(reminder_job)
            if result["sent"] or result["failed"]:
                log.info("Reminders: %s", result)
        except Exception:
            log.exception("Reminder job crashed")
        await asyncio.sleep(max(5, config.REMINDER_INTERVAL_MIN) * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_production_settings()
    run_migrations()
    ensure_admin()
    with SessionLocal() as db:
        bootstrap(db)
    task = asyncio.create_task(reminder_loop())
    yield
    task.cancel()


app = FastAPI(title="Electronics Department - Equipment Management", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth_staff, students, inventory, rfid, circulation, reports, labs, registrations):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# Serve the built React app (frontend/dist) from the same server when it exists.
_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.isdir(_dist):
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
