# backend/app/seed.py
from .database import SessionLocal
from .models import Patient, Prescription, Drug, Prescriber, Refill, Priority, RxState, Prescriber, Stock, RefillHist
from datetime import date

db = SessionLocal()

# Add patients
patients = [
    Patient(first_name="Alice", last_name="Smith", dob=date(1990, 5, 1), address="123 Elm St"),
    Patient(first_name="John", last_name="Stockton", dob=date(1982, 3, 14), address="456 Oak Ave"),
    Patient(first_name="Maria", last_name="Lopez", dob=date(1975, 7, 22), address="789 Pine Blvd"),
    Patient(first_name="David", last_name="Kim", dob=date(2000, 12, 10), address="321 Maple Dr"),
    
    Patient(first_name="Emily", last_name="Johnson", dob=date(1995, 8, 3), address="654 Birch Ln"),
    Patient(first_name="Michael", last_name="Brown", dob=date(1988, 11, 19), address="987 Cedar St"),
    Patient(first_name="Sophia", last_name="Davis", dob=date(2002, 2, 28), address="147 Spruce Rd"),
    Patient(first_name="Daniel", last_name="Wilson", dob=date(1979, 6, 12), address="258 Oakwood Dr"),
    Patient(first_name="Olivia", last_name="Martinez", dob=date(1993, 9, 15), address="369 Willow Ave"),
    Patient(first_name="James", last_name="Garcia", dob=date(1985, 4, 20), address="741 Pine St"),
    Patient(first_name="Isabella", last_name="Anderson", dob=date(2001, 1, 5), address="852 Maple Blvd"),
    Patient(first_name="Ethan", last_name="Thomas", dob=date(1998, 7, 9), address="963 Birch Ct"),
    Patient(first_name="Mia", last_name="Taylor", dob=date(1992, 3, 30), address="159 Cedar Ln"),
    Patient(first_name="Alexander", last_name="Moore", dob=date(1977, 10, 22), address="753 Spruce St"),
    Patient(first_name="Charlotte", last_name="Jackson", dob=date(2003, 5, 17), address="357 Elm Dr"),
    Patient(first_name="Benjamin", last_name="White", dob=date(1980, 12, 25), address="951 Oak St"),
    Patient(first_name="Amelia", last_name="Harris", dob=date(1996, 6, 7), address="246 Pine Ave"),
    Patient(first_name="William", last_name="Martin", dob=date(1983, 9, 2), address="135 Cedar Blvd"),
    Patient(first_name="Harper", last_name="Lee", dob=date(1999, 11, 11), address="468 Maple Ln"),
    Patient(first_name="Jackson", last_name="Perez", dob=date(2004, 2, 14), address="579 Birch St"),
]
db.add_all(patients)
db.commit()

# Add prescribers
prescriber1 = Prescriber(first_name="Emily", last_name="Brown")
prescriber2 = Prescriber(first_name="James", last_name="Wilson")
prescriber3 = Prescriber(first_name="Laura", last_name="Johnson")
prescriber4 = Prescriber(first_name="Michael", last_name="Lee")
prescriber5 = Prescriber(first_name="Sarah", last_name="Davis")
prescriber6 = Prescriber(first_name="Daniel", last_name="Miller")
prescriber7 = Prescriber(first_name="Sophia", last_name="Taylor")

db.add_all([prescriber1, prescriber2, prescriber3, prescriber4, prescriber5, prescriber6, prescriber7])
db.commit()


# Add drugs
drugs = [
    Drug(drug_name="Tylenol", manufacturer="Reddy", cost=0.20, niosh=False, drug_class=1),
    Drug(drug_name="Amoxicillin", manufacturer="Pfizer", cost=0.50, niosh=False, drug_class=2),
    Drug(drug_name="Cisplatin", manufacturer="Teva", cost=25.00, niosh=True, drug_class=3),  # chemo
    Drug(drug_name="Metformin", manufacturer="Sun Pharma", cost=0.15, niosh=False, drug_class=5),
    Drug(drug_name="Ibuprofen", manufacturer="Bayer", cost=0.10, niosh=False, drug_class=1),
    Drug(drug_name="Aspirin", manufacturer="Bayer", cost=0.05, niosh=False, drug_class=1),
    Drug(drug_name="Lisinopril", manufacturer="Merck", cost=0.12, niosh=False, drug_class=4),
    Drug(drug_name="Hydrochlorothiazide", manufacturer="Pfizer", cost=0.08, niosh=False, drug_class=4),
    Drug(drug_name="Warfarin", manufacturer="BMS", cost=0.25, niosh=True, drug_class=6),
    Drug(drug_name="Atorvastatin", manufacturer="Pfizer", cost=0.30, niosh=False, drug_class=4),
    Drug(drug_name="Omeprazole", manufacturer="AstraZeneca", cost=0.40, niosh=False, drug_class=4),
    Drug(drug_name="Prednisone", manufacturer="Teva", cost=0.10, niosh=False, drug_class=4),
    Drug(drug_name="Insulin", manufacturer="Novo Nordisk", cost=8.00, niosh=False, drug_class=5),  # expensive biologic
    Drug(drug_name="Methotrexate", manufacturer="Teva", cost=5.00, niosh=True, drug_class=3),
    Drug(drug_name="Alprazolam", manufacturer="Pfizer", cost=0.50, niosh=False, drug_class=7),
    Drug(drug_name="Morphine", manufacturer="Purdue", cost=1.50, niosh=False, drug_class=6),
    Drug(drug_name="Cyclophosphamide", manufacturer="Teva", cost=18.00, niosh=True, drug_class=3),  # chemo
    Drug(drug_name="Ceftriaxone", manufacturer="Roche", cost=2.00, niosh=False, drug_class=2),
    Drug(drug_name="Azithromycin", manufacturer="Pfizer", cost=1.00, niosh=False, drug_class=2),
    Drug(drug_name="Furosemide", manufacturer="Novartis", cost=0.20, niosh=False, drug_class=4),
]


db.add_all(drugs)
db.commit()

# Add Stock
stock_entries = [
    Stock(drug_id=1, quantity=1000),   # Tylenol
    Stock(drug_id=2, quantity=988),    # Amoxicillin
    Stock(drug_id=3, quantity=100),    # Cisplatin (hazardous)
    Stock(drug_id=4, quantity=20),     # Metformin
    Stock(drug_id=5, quantity=500),    # Ibuprofen
    Stock(drug_id=6, quantity=750),    # Lipitor
    Stock(drug_id=7, quantity=200),    # Warfarin
    Stock(drug_id=8, quantity=300),    # Levothyroxine
    Stock(drug_id=9, quantity=400),    # Omeprazole
    Stock(drug_id=10, quantity=150),   # Albuterol
    Stock(drug_id=11, quantity=600),   # Simvastatin
    Stock(drug_id=12, quantity=50),    # Methotrexate (hazardous)
    Stock(drug_id=13, quantity=250),   # Furosemide
    Stock(drug_id=14, quantity=350),   # Gabapentin
    Stock(drug_id=15, quantity=80),    # Cyclophosphamide (hazardous)
    Stock(drug_id=16, quantity=400),   # Lisinopril
    Stock(drug_id=17, quantity=450),   # Prednisone
    Stock(drug_id=18, quantity=100),   # Doxorubicin (hazardous)
    Stock(drug_id=19, quantity=500),   # Amlodipine
    Stock(drug_id=20, quantity=300),   # Metoprolol
]

db.add_all(stock_entries)
db.commit()


# Add prescriptions
prescription1 = Prescription(drug_id=3, original_quantity=30, remaining_quantity=20, patient_id=1, date_received=date(2025, 9, 30), prescriber_id=prescriber1.id)
prescription2 = Prescription(drug_id=1, original_quantity=20, remaining_quantity=10, patient_id=2, date_received=date(2025, 9, 28), prescriber_id=prescriber2.id)
prescription3 = Prescription(drug_id=4, original_quantity=90, remaining_quantity=90, patient_id=3, date_received=date(2025, 9, 29), prescriber_id=prescriber1.id)
prescription4 = Prescription(drug_id=4, original_quantity=60, remaining_quantity=60, patient_id=4, date_received=date(2025, 8, 5), prescriber_id=prescriber1.id)
prescription5 = Prescription(drug_id=2, original_quantity=15, remaining_quantity=15, patient_id=1, date_received=date(2025, 8, 10), prescriber_id=prescriber3.id)
prescription6 = Prescription(drug_id=5, original_quantity=50, remaining_quantity=50, patient_id=2, date_received=date(2025, 9, 2), prescriber_id=prescriber4.id)
prescription7 = Prescription(drug_id=6, original_quantity=25, remaining_quantity=25, patient_id=3, date_received=date(2025, 9, 5), prescriber_id=prescriber5.id)
prescription8 = Prescription(drug_id=7, original_quantity=10, remaining_quantity=10, patient_id=4, date_received=date(2025, 9, 10), prescriber_id=prescriber6.id)
prescription9 = Prescription(drug_id=8, original_quantity=40, remaining_quantity=40, patient_id=1, date_received=date(2025, 9, 12), prescriber_id=prescriber7.id)
prescription10 = Prescription(drug_id=9, original_quantity=30, remaining_quantity=30, patient_id=2, date_received=date(2025, 9, 15), prescriber_id=prescriber4.id)

db.add_all([prescription1, prescription2, prescription3, prescription4, prescription5, prescription6, prescription7, prescription8, prescription9, prescription10])
db.commit()

refill_hist1 = RefillHist(prescription_id=prescription1.id, patient_id=1, drug_id=3, quantity=10, days_supply=5, completed_date=date(2025, 9, 1), sold_date=date(2025, 9, 2))
refill_hist2 = RefillHist(prescription_id=prescription2.id, patient_id=2, drug_id=1, quantity=10, days_supply=10, completed_date=date(2025, 9, 15), sold_date=date(2025, 9, 16))
refill_hist3 = RefillHist(prescription_id=prescription3.id, patient_id=3, drug_id=4, quantity=30, days_supply=30, completed_date=date(2025, 9, 30), sold_date=date(2025, 10, 1))
refill_hist4 = RefillHist(prescription_id=prescription5.id, patient_id=1, drug_id=2, quantity=15, days_supply=15, completed_date=date(2025, 8, 25), sold_date=date(2025, 8, 26))
refill_hist5 = RefillHist(prescription_id=prescription6.id, patient_id=2, drug_id=5, quantity=50, days_supply=50, completed_date=date(2025, 8, 20), sold_date=date(2025, 8, 21))

db.add_all([refill_hist1, refill_hist2, refill_hist3, refill_hist4, refill_hist5])
db.commit()

refill1 = Refill(prescription_id=prescription1.id, patient_id=1, drug_id=3, due_date=date(2025, 9, 1), quantity=10, days_supply=5, priority=Priority.high, state=RxState.QT)
refill2 = Refill(prescription_id=prescription2.id, patient_id=2, drug_id=1, due_date=date(2025, 9, 15), quantity=10, days_supply=10, priority=Priority.normal, state=RxState.QV1)
refill3 = Refill(prescription_id=prescription3.id, patient_id=3, drug_id=4, due_date=date(2025, 9, 30), quantity=30, days_supply=30, priority=Priority.low, state=RxState.QP)
refill5 = Refill(prescription_id=prescription6.id, patient_id=2, drug_id=5, due_date=date(2025, 10, 10), quantity=50, days_supply=50, priority=Priority.high, state=RxState.QT)

db.add_all([refill1, refill2, refill3, refill5])
db.commit()

db.close()

