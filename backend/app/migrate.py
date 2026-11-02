"""Idempotent start-up migration.

Creates missing tables, adds the new columns to tables from older versions, creates the default
laboratory and moves all existing data into it. Safe to run on every start, on an empty database
(first run) or on a database made by the previous version (data is kept).
"""
import logging

from sqlalchemy import inspect, text

from . import config
from .db import Base, engine
from .models import Device, Lab, StaffLab, User
from .security import hash_device_key

log = logging.getLogger("lab")

NEW_COLUMNS = {
    "equipment": {"lab_id": "INTEGER NULL"},
    "issues": {"lab_id": "INTEGER NULL"},
    "rfid_scans": {"lab_id": "INTEGER NULL"},
    "device_messages": {"lab_id": "INTEGER NULL"},
    "students": {"course": "VARCHAR(80) NOT NULL DEFAULT ''", "department": "VARCHAR(80) NOT NULL DEFAULT ''",
                 "registered_lab_id": "INTEGER NULL"},
}


def _add_missing_columns() -> None:
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in NEW_COLUMNS.items():
            if not insp.has_table(table):
                continue
            have = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in have:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
                    log.warning("Migration: added %s.%s", table, name)


def _fix_equipment_unique() -> None:
    """Equipment names were unique across the whole system; now they are unique per laboratory."""
    insp = inspect(engine)
    if not insp.has_table("equipment"):
        return
    idx = insp.get_indexes("equipment")
    ucs = insp.get_unique_constraints("equipment")
    old = {i["name"] for i in idx if i.get("unique") and list(i["column_names"]) == ["name"]}
    old |= {u["name"] for u in ucs if list(u["column_names"]) == ["name"]}
    has_new = any(i.get("unique") and set(i["column_names"]) == {"lab_id", "name"} for i in idx) or \
        any(set(u["column_names"]) == {"lab_id", "name"} for u in ucs)
    with engine.begin() as conn:
        if engine.dialect.name == "mysql":
            for n in old:
                if n:
                    conn.execute(text(f"ALTER TABLE equipment DROP INDEX `{n}`"))
                    log.warning("Migration: dropped global unique index %s on equipment.name", n)
        if engine.dialect.name == "sqlite" and old:
            # SQLite cannot drop a constraint, so rebuild the table (only old trial databases need this)
            conn.execute(text("CREATE TABLE equipment_new (id INTEGER NOT NULL PRIMARY KEY, lab_id INTEGER, "
                              "name VARCHAR(120) NOT NULL, category VARCHAR(60) NOT NULL DEFAULT '', total_qty INTEGER NOT NULL DEFAULT 0, "
                              "available_qty INTEGER NOT NULL DEFAULT 0, issued_qty INTEGER NOT NULL DEFAULT 0, "
                              "damaged_qty INTEGER NOT NULL DEFAULT 0, missing_qty INTEGER NOT NULL DEFAULT 0, "
                              "maintenance_qty INTEGER NOT NULL DEFAULT 0, notes VARCHAR(255) NOT NULL DEFAULT '', "
                              "FOREIGN KEY(lab_id) REFERENCES labs (id), CONSTRAINT uq_equipment_lab_name UNIQUE (lab_id, name))"))
            conn.execute(text("INSERT INTO equipment_new (id, lab_id, name, category, total_qty, available_qty, issued_qty, "
                              "damaged_qty, missing_qty, maintenance_qty, notes) SELECT id, lab_id, name, category, total_qty, "
                              "available_qty, issued_qty, damaged_qty, missing_qty, maintenance_qty, notes FROM equipment"))
            conn.execute(text("DROP TABLE equipment"))
            conn.execute(text("ALTER TABLE equipment_new RENAME TO equipment"))
            conn.execute(text("CREATE INDEX ix_equipment_lab_id ON equipment (lab_id)"))
            log.warning("Migration: rebuilt equipment table with per-laboratory unique names")
        elif not has_new:
            conn.execute(text("CREATE UNIQUE INDEX uq_equipment_lab_name ON equipment (lab_id, name)"))


def bootstrap(db) -> None:
    lab = db.query(Lab).order_by(Lab.id).first()
    first_time = lab is None
    if first_time:
        lab = Lab(name=config.DEFAULT_LAB_NAME, code=config.DEFAULT_LAB_CODE)
        db.add(lab)
        db.flush()
        log.warning("Created the first laboratory: %s (%s)", lab.name, lab.code)
    for table in ("equipment", "rfid_scans", "device_messages"):
        db.execute(text(f"UPDATE {table} SET lab_id = :l WHERE lab_id IS NULL"), {"l": lab.id})
    db.execute(text("UPDATE issues SET lab_id = (SELECT e.lab_id FROM equipment e WHERE e.id = issues.equipment_id) "
                    "WHERE lab_id IS NULL"))
    if first_time:
        for u in db.query(User).filter(User.role != "admin").all():
            db.add(StaffLab(user_id=u.id, lab_id=lab.id))
        if db.query(Device).count() == 0:
            db.add(Device(device_id="LAB-RFID-01", name="Main reader", lab_id=lab.id,
                          key_hash=hash_device_key(config.DEVICE_KEY)))
    db.commit()


def run_migrations() -> None:
    Base.metadata.create_all(engine)
    _add_missing_columns()
    _fix_equipment_unique()
