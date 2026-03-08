# backend/app/seed.py
from .database import SessionLocal
from .models import Patient, Prescription, Drug, Prescriber, Refill, Priority, RxState, Prescriber, Stock, RefillHist
from datetime import date, timedelta
from decimal import Decimal

today = date.today()

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
prescribers = [
    Prescriber(npi=123456789, first_name="Emily", last_name="Brown", phone_number="(555) 123-4567", address="123 Main St"),
    Prescriber(npi=987654321, first_name="James", last_name="Wilson", phone_number="(555) 987-6543", address="456 Oak Ave"),
    Prescriber(npi=555444333, first_name="Laura", last_name="Johnson", phone_number="(555) 555-4443", address="789 Pine Rd"),
    Prescriber(npi=111222333, first_name="Michael", last_name="Lee", phone_number="(555) 111-2223", address="345 Birch Ln"),
    Prescriber(npi=666777888, first_name="Sarah", last_name="Davis", phone_number="(555) 666-7778", address="456 Elm St"),
    Prescriber(npi=333444555, first_name="Daniel", last_name="Miller", phone_number="(555) 333-4445", address="789 Oak Ave"),
    Prescriber(npi=888999000, first_name="Sophia", last_name="Taylor", phone_number="(555) 888-9990", address="123 Maple Rd")
]

db.add_all(prescribers)
db.commit()


# Add drugs
drugs = [
    Drug(drug_name="Tylenol", manufacturer="Reddy", cost=Decimal("0.20"), niosh=False, drug_class=1,
         description="White round tablet, imprint '325'"),
    Drug(drug_name="Amoxicillin", manufacturer="Pfizer", cost=Decimal("0.50"), niosh=False, drug_class=2,
         description="Pink oval capsule, imprint 'AMOX 500'"),
    Drug(drug_name="Cisplatin", manufacturer="Teva", cost=Decimal("25.00"), niosh=True, drug_class=3,
         description="Clear solution in vial - NIOSH HAZARDOUS"),
    Drug(drug_name="Metformin", manufacturer="Sun Pharma", cost=Decimal("0.15"), niosh=False, drug_class=5,
         description="White round tablet, imprint 'M 500'"),
    Drug(drug_name="Ibuprofen", manufacturer="Bayer", cost=Decimal("0.10"), niosh=False, drug_class=1,
         description="Brown oval tablet, imprint 'IBU 200'"),
    Drug(drug_name="Aspirin", manufacturer="Bayer", cost=Decimal("0.05"), niosh=False, drug_class=1,
         description="White round tablet, imprint 'BAYER'"),
    Drug(drug_name="Lisinopril", manufacturer="Merck", cost=Decimal("0.12"), niosh=False, drug_class=4,
         description="Pink round tablet, imprint 'L 10'"),
    Drug(drug_name="Hydrochlorothiazide", manufacturer="Pfizer", cost=Decimal("0.08"), niosh=False, drug_class=4,
         description="White round tablet, imprint 'H 25'"),
    Drug(drug_name="Warfarin", manufacturer="BMS", cost=Decimal("0.25"), niosh=True, drug_class=6,
         description="Tan round tablet, imprint 'W 5' - BLOOD THINNER"),
    Drug(drug_name="Atorvastatin", manufacturer="Pfizer", cost=Decimal("0.30"), niosh=False, drug_class=4,
         description="White oval tablet, imprint 'PD 155'"),
    Drug(drug_name="Omeprazole", manufacturer="AstraZeneca", cost=Decimal("0.40"), niosh=False, drug_class=4,
         description="Purple and pink capsule, imprint 'A/OM 20'"),
    Drug(drug_name="Prednisone", manufacturer="Teva", cost=Decimal("0.10"), niosh=False, drug_class=4,
         description="White round tablet, imprint 'P 5'"),
    Drug(drug_name="Insulin", manufacturer="Novo Nordisk", cost=Decimal("8.00"), niosh=False, drug_class=5,
         description="Clear solution in pen injector - REFRIGERATE"),
    Drug(drug_name="Methotrexate", manufacturer="Teva", cost=Decimal("5.00"), niosh=True, drug_class=3,
         description="Yellow round tablet, imprint 'MTX' - NIOSH HAZARDOUS"),
    Drug(drug_name="Alprazolam", manufacturer="Pfizer", cost=Decimal("0.50"), niosh=False, drug_class=7,
         description="White oval tablet, imprint 'X 2' - CONTROLLED SUBSTANCE"),
    Drug(drug_name="Morphine", manufacturer="Purdue", cost=Decimal("1.50"), niosh=False, drug_class=6,
         description="White round tablet, imprint 'M 15' - CONTROLLED SUBSTANCE"),
    Drug(drug_name="Cyclophosphamide", manufacturer="Teva", cost=Decimal("18.00"), niosh=True, drug_class=3,
         description="White round tablet in blister pack - NIOSH HAZARDOUS"),
    Drug(drug_name="Ceftriaxone", manufacturer="Roche", cost=Decimal("2.00"), niosh=False, drug_class=2,
         description="White powder in vial for injection"),
    Drug(drug_name="Azithromycin", manufacturer="Pfizer", cost=Decimal("1.00"), niosh=False, drug_class=2,
         description="Pink oval tablet, imprint 'ZITH 250'"),
    Drug(drug_name="Furosemide", manufacturer="Novartis", cost=Decimal("0.20"), niosh=False, drug_class=4,
         description="White round tablet, imprint 'F 40'"),
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
# Add prescriptions
prescription1 = Prescription(drug_id=3, brand_required=False, original_quantity=30, remaining_quantity=20,
                             patient_id=1, date_received=today - timedelta(days=190), prescriber_id=1,
                             instructions="Administer 1 vial by intravenous infusion every 4 weeks as directed by oncologist")  # Cisplatin - edge case: IV chemo, qty/days supply not directly tied to instruction frequency
prescription2 = Prescription(drug_id=1, brand_required=False, original_quantity=20, remaining_quantity=10,
                             patient_id=2, date_received=today - timedelta(days=185), prescriber_id=2,
                             instructions="Take 2 tablets by mouth every 4 to 6 hours as needed for pain, not to exceed 8 tablets per day")  # Tylenol - edge case: ~2.5 days at max dose, but days_supply=10
prescription3 = Prescription(drug_id=4, brand_required=False, original_quantity=90, remaining_quantity=90,
                             patient_id=3, date_received=today - timedelta(days=180), prescriber_id=1,
                             instructions="Take 1 tablet by mouth three times daily with meals")  # Metformin - 90 qty / 3/day = 30 days supply
prescription4 = Prescription(drug_id=4, brand_required=False, original_quantity=60, remaining_quantity=60,
                             patient_id=4, date_received=today - timedelta(days=210), prescriber_id=1,
                             instructions="Take 2 tablets by mouth twice daily with meals")  # Metformin - edge case: same drug, 60 qty / 4/day = 15 days
prescription5 = Prescription(drug_id=2, brand_required=False, original_quantity=15, remaining_quantity=15,
                             patient_id=1, date_received=today - timedelta(days=205), prescriber_id=3,
                             instructions="Take 1 capsule by mouth three times daily until finished")  # Amoxicillin - edge case: 15 qty / 3/day = 5 days, but days_supply=10
prescription6 = Prescription(drug_id=5, brand_required=False, original_quantity=50, remaining_quantity=50,
                             patient_id=2, date_received=today - timedelta(days=200), prescriber_id=4,
                             instructions="Take 1 tablet by mouth every 8 hours with food as needed for pain")  # Ibuprofen - edge case: 50 qty / 3/day = ~17 days, but days_supply=50
prescription7 = Prescription(drug_id=6, brand_required=False, original_quantity=25, remaining_quantity=25,
                             patient_id=3, date_received=today - timedelta(days=175), prescriber_id=5,
                             instructions="Take 1 tablet by mouth daily for cardiovascular protection")  # Aspirin - 25 qty / 1/day = 25 days, days_supply=30 slight edge case
prescription8 = Prescription(drug_id=7, brand_required=False, original_quantity=10, remaining_quantity=10,
                             patient_id=4, date_received=today - timedelta(days=170), prescriber_id=6,
                             instructions="Take 1 tablet by mouth once daily for blood pressure")  # Lisinopril - edge case: 10 qty / 1/day = 10 days, but days_supply=30
prescription9 = Prescription(drug_id=8, brand_required=False, original_quantity=40, remaining_quantity=40,
                             patient_id=1, date_received=today - timedelta(days=165), prescriber_id=7,
                             instructions="Take 1 tablet by mouth once daily in the morning")  # Hydrochlorothiazide - edge case: 40 qty / 1/day = 40 days, but days_supply=30
prescription10 = Prescription(drug_id=9, brand_required=False, original_quantity=30, remaining_quantity=30,
                              patient_id=2, date_received=today - timedelta(days=160), prescriber_id=4,
                              instructions="Take 1 tablet by mouth daily, INR monitoring required")  # Warfarin - 30 qty / 1/day = 30 days supply

db.add_all([prescription1, prescription2, prescription3, prescription4, prescription5, prescription6, prescription7, prescription8, prescription9, prescription10])
db.commit()

refill_hist1 = RefillHist(
    prescription_id=prescription1.id, patient_id=1, drug_id=3,
    quantity=10, days_supply=5,
    completed_date=today - timedelta(days=185), sold_date=today - timedelta(days=184),
    total_cost=Decimal("250.00")
)

refill_hist2 = RefillHist(
    prescription_id=prescription2.id, patient_id=2, drug_id=1,
    quantity=10, days_supply=10,
    completed_date=today - timedelta(days=180), sold_date=today - timedelta(days=179),
    total_cost=Decimal("2.00")
)

refill_hist3 = RefillHist(
    prescription_id=prescription3.id, patient_id=3, drug_id=4,
    quantity=30, days_supply=30,
    completed_date=today - timedelta(days=175), sold_date=today - timedelta(days=174),
    total_cost=Decimal("4.50")
)

refill_hist4 = RefillHist(
    prescription_id=prescription5.id, patient_id=1, drug_id=2,
    quantity=15, days_supply=15,
    completed_date=today - timedelta(days=200), sold_date=today - timedelta(days=199),
    total_cost=Decimal("7.50")
)

refill_hist5 = RefillHist(
    prescription_id=prescription6.id, patient_id=2, drug_id=5,
    quantity=50, days_supply=50,
    completed_date=today - timedelta(days=195), sold_date=today - timedelta(days=194),
    total_cost=Decimal("5.00")
)
db.add_all([refill_hist1, refill_hist2, refill_hist3, refill_hist4, refill_hist5])
db.commit()

refill1 = Refill(
    prescription_id=prescription1.id, patient_id=1, drug_id=3,
    due_date=today - timedelta(days=5), quantity=10, days_supply=5,
    priority=Priority.high, state=RxState.QT,
    total_cost=Decimal("250.00")
)

refill2 = Refill(
    prescription_id=prescription2.id, patient_id=2, drug_id=1,
    due_date=today + timedelta(days=5), quantity=10, days_supply=10,
    priority=Priority.normal, state=RxState.QV1,
    total_cost=Decimal("2.00")
)

refill3 = Refill(
    prescription_id=prescription3.id, patient_id=3, drug_id=4,
    due_date=today + timedelta(days=30), quantity=30, days_supply=30,
    priority=Priority.low, state=RxState.QP,
    total_cost=Decimal("4.50")
)

refill5 = Refill(
    prescription_id=prescription6.id, patient_id=2, drug_id=5,
    due_date=today - timedelta(days=3), quantity=50, days_supply=50,
    priority=Priority.high, state=RxState.QT,
    total_cost=Decimal("5.00"),
    source="external"  # External prescription via JSON
)

# Add refill in QV2 state
refill6 = Refill(
    prescription_id=prescription7.id, patient_id=3, drug_id=6,
    due_date=today + timedelta(days=10), quantity=25, days_supply=30,
    priority=Priority.normal, state=RxState.QV2,
    total_cost=Decimal("1.25"),
    source="manual"
)

# Add refill in READY state with bin assignment
refill7 = Refill(
    prescription_id=prescription8.id, patient_id=4, drug_id=7,
    due_date=today - timedelta(days=2), quantity=10, days_supply=30,
    priority=Priority.stat, state=RxState.READY,
    total_cost=Decimal("1.44"),
    bin_number=42,  # Assigned bin
    source="manual"
)

# Add refill in HOLD state
refill8 = Refill(
    prescription_id=prescription9.id, patient_id=1, drug_id=8,
    due_date=today + timedelta(days=3), quantity=40, days_supply=30,
    priority=Priority.normal, state=RxState.HOLD,
    total_cost=Decimal("3.20"),
    source="manual"
)

# Add refill in REJECTED state
refill9 = Refill(
    prescription_id=prescription10.id, patient_id=2, drug_id=9,
    due_date=today + timedelta(days=1), quantity=30, days_supply=30,
    priority=Priority.normal, state=RxState.REJECTED,
    total_cost=Decimal("7.50"),
    rejected_by="PharmD Smith",
    rejection_reason="Incorrect quantity - prescriber authorization needed",
    rejection_date=today - timedelta(days=5),
    source="external"
)

# Add another READY refill
refill10 = Refill(
    prescription_id=prescription5.id, patient_id=1, drug_id=2,
    due_date=today - timedelta(days=1), quantity=15, days_supply=10,
    priority=Priority.high, state=RxState.READY,
    total_cost=Decimal("7.50"),
    bin_number=17,
    source="manual"
)

db.add_all([refill1, refill2, refill3, refill5, refill6, refill7, refill8, refill9, refill10])
db.commit()

db.close()

