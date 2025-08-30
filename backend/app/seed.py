# backend/app/seed.py
from .database import SessionLocal, engine
from .models import Patient, Prescription
from datetime import date

db = SessionLocal()

# Add patients
patient1 = Patient(first_name="Alice", last_name="Smith", dob=date(1990, 5, 1), address="123 Elm St")
db.add(patient1)
db.commit()
db.refresh(patient1)

# Add prescriptions
prescription1 = Prescription(
    drug_name="Ibuprofen",
    quantity=20,
    due_date=date(2025, 9, 1),
    priority="high",
    state="QT",
    patient_id=patient1.id
)
db.add(prescription1)
db.commit()
db.close()
