from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DATABASE_URL, DB_SSL

if DATABASE_URL.startswith("sqlite"):
    kwargs = {"connect_args": {"check_same_thread": False}}
else:
    kwargs = {"pool_pre_ping": True, "pool_recycle": 1800}
    if DB_SSL:
        import certifi
        kwargs["connect_args"] = {"ssl_ca": certifi.where(), "ssl_verify_cert": True, "ssl_verify_identity": True}

engine = create_engine(DATABASE_URL, **kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
