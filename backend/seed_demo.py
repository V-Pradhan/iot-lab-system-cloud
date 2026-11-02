"""Optional: add sample equipment (to the first laboratory) and one sample student.  Run:  python seed_demo.py"""
from app.db import SessionLocal
from app.migrate import bootstrap, run_migrations
from app.models import Equipment, Lab, Student

run_migrations()
items = [("Arduino Uno R3", "Microcontroller", 20), ("ESP8266 NodeMCU", "Microcontroller", 15),
         ("Raspberry Pi 4", "Single-board computer", 8), ("DHT11 Sensor", "Sensor", 30),
         ("Ultrasonic Sensor HC-SR04", "Sensor", 25), ("Breadboard", "Prototyping", 40),
         ("Jumper Wire Set", "Prototyping", 50), ("Digital Multimeter", "Instrument", 10)]
with SessionLocal() as db:
    bootstrap(db)
    lab = db.query(Lab).order_by(Lab.id).first()
    for name, cat, qty in items:
        if not db.query(Equipment).filter_by(lab_id=lab.id, name=name).first():
            db.add(Equipment(lab_id=lab.id, name=name, category=cat, total_qty=qty, available_qty=qty))
    if not db.query(Student).filter_by(university_uid="DEMO001").first():
        db.add(Student(name="Demo Student", university_uid="DEMO001", class_section="IoT-A", mobile="9999999999",
                       email="demo@example.com", registered_lab_id=lab.id))
    db.commit()
print("Demo data added to", lab.name)
