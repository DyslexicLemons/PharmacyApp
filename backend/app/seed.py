# backend/app/seed.py
from .database import SessionLocal
from .models import Patient, Prescription, Drug, Prescriber, Refill, Priority, RxState, Prescriber, Stock, RefillHist
from datetime import date

db = SessionLocal()

# Add patients
patient1 = Patient(first_name="Alice", last_name="Smith", dob=date(1990, 5, 1), address="123 Elm St")
patient2 = Patient(first_name="John", last_name="Stockton", dob=date(1982, 3, 14), address="456 Oak Ave")
patient3 = Patient(first_name="Maria", last_name="Lopez", dob=date(1975, 7, 22), address="789 Pine Blvd")
patient4 = Patient(first_name="David", last_name="Kim", dob=date(2000, 12, 10), address="321 Maple Dr")

db.add_all([patient1, patient2, patient3, patient4])
db.commit()

# Add prescribers
prescriber1 = Prescriber(first_name="Emily", last_name="Brown")
prescriber2 = Prescriber(first_name="James", last_name="Wilson")
db.add_all([prescriber1, prescriber2])
db.commit()


# Add drugs
drug1 = Drug(drug_name="Tylenol", manufacturer="Reddy", niosh=False, drug_class=1)
drug2 = Drug(drug_name="Amoxicillin", manufacturer="Pfizer", niosh=False, drug_class=2)
drug3 = Drug(drug_name="Cisplatin", manufacturer="Teva", niosh=True, drug_class=3)  # hazardous drug
drug4 = Drug(drug_name="Metformin", manufacturer="Sun Pharma", niosh=False, drug_class=5)

db.add_all([drug1, drug2, drug3, drug4])
db.commit()

# Add Stock
stock1 = Stock(drug_id=1,quantity=1000)
stock2 = Stock(drug_id=2,quantity=988)
stock3 = Stock(drug_id=3,quantity=100)
stock4 = Stock(drug_id=4,quantity=20)

db.add_all([stock1, stock2, stock3, stock4])
db.commit()


# Add prescriptions
prescription1 = Prescription(
    drug_name="Ibuprofen",
    original_quantity=30,
    remaining_quantity=20,
    patient_id=patient1.id,
    date_received=date(2025, 9, 30),
    prescriber_id = prescriber1.id
)
prescription2 = Prescription(
    drug_name="Amoxicillin",
    original_quantity=20,
    remaining_quantity=10,
    patient_id=patient2.id,
    date_received=date(2025, 9, 28),
    prescriber_id = prescriber2.id
)
prescription3 = Prescription(
    drug_name="Metformin",
    original_quantity=90,
    remaining_quantity=90,
    patient_id=patient3.id,
    date_received=date(2025, 9, 29),
    prescriber_id = prescriber1.id
)

db.add_all([prescription1, prescription2, prescription3])
db.commit()

refill_hist1 = RefillHist(
    prescription_id=prescription1.id,
    patient_id=patient1.id,
    drug_id=drug1.id,
    quantity=10,
    completed_date=date(2025, 9, 1),
    sold_date=date(2025, 9, 2)
)

refill_hist2 = RefillHist(
    prescription_id=prescription2.id,
    patient_id=patient2.id,
    drug_id=drug2.id,
    quantity=10,
    completed_date=date(2025, 9, 15),
    sold_date=date(2025, 9, 16)
)

refill_hist3 = RefillHist(
    prescription_id=prescription3.id,
    patient_id=patient3.id,
    drug_id=drug4.id,
    quantity=30,
    completed_date=date(2025, 9, 30),
    sold_date=date(2025, 10, 1)
)

db.add_all([refill_hist1, refill_hist2, refill_hist3])
db.commit()

# Add refills
refill1 = Refill(
    prescription_id=prescription1.id,
    patient_id=patient1.id,
    drug_id=drug1.id,
    due_date=date(2025, 9, 1),
    quantity=10,
    priority=Priority.high,
    state=RxState.QT,
)
refill2 = Refill(
    prescription_id=prescription2.id,
    patient_id=patient2.id,
    drug_id=drug2.id,
    due_date=date(2025, 9, 15),
    quantity=10,
    priority=Priority.normal,
    state=RxState.QV1,
)
refill3 = Refill(
    prescription_id=prescription3.id,
    patient_id=patient3.id,
    drug_id=drug4.id,
    due_date=date(2025, 9, 30),
    quantity=30,
    priority=Priority.low,
    state=RxState.QP,
)

db.add_all([refill1, refill2, refill3])
db.commit()

db.close()

