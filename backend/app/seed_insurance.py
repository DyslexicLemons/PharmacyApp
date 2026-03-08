# backend/app/seed_insurance.py
#
# Run once after the main seed:
#   cd backend && python -m app.seed_insurance
#
# Seeds:
#   - 15 additional realistic prescribers (with specialties)
#   - 5 insurance companies
#   - Formulary entries (all 20 drugs x 5 companies)
#   - Sample patient insurance assignments

from .database import SessionLocal
from .models import Prescriber, InsuranceCompany, Formulary, PatientInsurance, Patient
from decimal import Decimal

db = SessionLocal()

# ─────────────────────────────────────────────
# PRESCRIBERS  (realistic NPI-style numbers)
# ─────────────────────────────────────────────
new_prescribers = [
    # General Practice / Family Medicine
    Prescriber(npi=1234567890, first_name="Robert",    last_name="Chen",      specialty="Family Medicine",        phone_number="(555) 201-0001", address="100 Main St, Suite 1A"),
    Prescriber(npi=2345678901, first_name="Patricia",  last_name="Nguyen",    specialty="Family Medicine",        phone_number="(555) 201-0002", address="200 Elm Ave"),
    Prescriber(npi=3456789012, first_name="Thomas",    last_name="Rivera",    specialty="Internal Medicine",      phone_number="(555) 201-0003", address="300 Oak Blvd"),
    Prescriber(npi=4567890123, first_name="Jennifer",  last_name="Patel",     specialty="Internal Medicine",      phone_number="(555) 201-0004", address="400 Pine Rd"),
    # Cardiology
    Prescriber(npi=5678901234, first_name="William",   last_name="Okafor",    specialty="Cardiology",             phone_number="(555) 201-0005", address="500 Heart Way, Suite 3B"),
    Prescriber(npi=6789012345, first_name="Susan",     last_name="Kowalski",  specialty="Cardiology",             phone_number="(555) 201-0006", address="600 Cardiac Dr"),
    # Endocrinology
    Prescriber(npi=7890123456, first_name="Kevin",     last_name="Yamamoto",  specialty="Endocrinology",          phone_number="(555) 201-0007", address="700 Endo Ave"),
    Prescriber(npi=8901234567, first_name="Angela",    last_name="Gutierrez", specialty="Endocrinology",          phone_number="(555) 201-0008", address="800 Metabolism Blvd"),
    # Oncology
    Prescriber(npi=9012345678, first_name="David",     last_name="Abramson",  specialty="Oncology",               phone_number="(555) 201-0009", address="900 Cancer Center Dr, Suite 5"),
    Prescriber(npi=1023456789, first_name="Michelle",  last_name="Park",      specialty="Oncology",               phone_number="(555) 201-0010", address="1000 Oncology Way"),
    # Psychiatry
    Prescriber(npi=1123456780, first_name="Gregory",   last_name="Hoffman",   specialty="Psychiatry",             phone_number="(555) 201-0011", address="1100 Mind St, Suite 2"),
    Prescriber(npi=1223456781, first_name="Rachel",    last_name="Simmons",   specialty="Psychiatry",             phone_number="(555) 201-0012", address="1200 Behavioral Blvd"),
    # Pain Management / Neurology
    Prescriber(npi=1323456782, first_name="Carlos",    last_name="Mendez",    specialty="Pain Management",        phone_number="(555) 201-0013", address="1300 Pain Clinic Rd"),
    Prescriber(npi=1423456783, first_name="Linda",     last_name="Thompson",  specialty="Neurology",              phone_number="(555) 201-0014", address="1400 Neuro Center Dr"),
    # Pulmonology / Rheumatology
    Prescriber(npi=1523456784, first_name="Andrew",    last_name="Wallace",   specialty="Pulmonology",            phone_number="(555) 201-0015", address="1500 Lung Health Ave"),
]

db.add_all(new_prescribers)
db.commit()
print(f"Added {len(new_prescribers)} prescribers.")

# ─────────────────────────────────────────────
# INSURANCE COMPANIES (5)
# ─────────────────────────────────────────────
companies = [
    InsuranceCompany(
        plan_id="BCBS-PPO-2024",
        plan_name="BlueCross BlueShield PPO",
        bin_number="610339",
        pcn="ADV",
        phone_number="(800) 521-2227",
    ),
    InsuranceCompany(
        plan_id="AETNA-HMO-2024",
        plan_name="Aetna Health HMO",
        bin_number="011219",
        pcn="AETNA",
        phone_number="(800) 872-3862",
    ),
    InsuranceCompany(
        plan_id="CIGNA-EPO-2024",
        plan_name="Cigna Healthcare EPO",
        bin_number="610602",
        pcn="CIGNA",
        phone_number="(800) 244-6224",
    ),
    InsuranceCompany(
        plan_id="UHC-PPO-2024",
        plan_name="UnitedHealthcare PPO",
        bin_number="610494",
        pcn="9999",
        phone_number="(844) 368-6379",
    ),
    InsuranceCompany(
        plan_id="HUM-HMO-2024",
        plan_name="Humana Gold HMO",
        bin_number="610373",
        pcn="HUMANA",
        phone_number="(800) 833-6917",
    ),
]

db.add_all(companies)
db.commit()
print(f"Added {len(companies)} insurance companies.")

# Reload to get IDs
bcbs, aetna, cigna, uhc, humana = db.query(InsuranceCompany).order_by(InsuranceCompany.id).all()[-5:]

# ─────────────────────────────────────────────
# FORMULARY
# Drug IDs (from seed.py):
#  1  Tylenol            – Generic OTC
#  2  Amoxicillin        – Generic antibiotic
#  3  Cisplatin          – Specialty chemo (Tier 4)
#  4  Metformin          – Generic (Tier 1)
#  5  Ibuprofen          – Generic OTC (Tier 1)
#  6  Aspirin            – Generic OTC (Tier 1)
#  7  Lisinopril         – Generic ACE inhibitor (Tier 1)
#  8  Hydrochlorothiazide– Generic diuretic (Tier 1)
#  9  Warfarin           – Generic blood thinner (Tier 1)
# 10  Atorvastatin       – Preferred brand statin (Tier 2)
# 11  Omeprazole         – Preferred brand PPI (Tier 2)
# 12  Prednisone         – Generic steroid (Tier 1)
# 13  Insulin            – Non-preferred brand (Tier 3)
# 14  Methotrexate       – Specialty (Tier 4)
# 15  Alprazolam         – Controlled (Tier 2)
# 16  Morphine           – Controlled opioid (Tier 3)
# 17  Cyclophosphamide   – Specialty chemo (Tier 4)
# 18  Ceftriaxone        – Brand antibiotic (Tier 2)
# 19  Azithromycin       – Brand antibiotic (Tier 2)
# 20  Furosemide         – Generic diuretic (Tier 1)
#
# Tier copay-per-30:
#   BCBS:   T1=$10  T2=$40  T3=$75  T4=$150
#   Aetna:  T1=$12  T2=$45  T3=$80  T4=$175
#   Cigna:  T1=$8   T2=$35  T3=$70  T4=$150
#   UHC:    T1=$15  T2=$50  T3=$85  T4=$200
#   Humana: T1=$10  T2=$42  T3=$78  T4=$160
#
# Not-covered exceptions:
#   Aetna:  Morphine (16) – requires separate opioid benefit
#   Cigna:  Cisplatin (3) – specialty pharmacy required (not covered here)
#   UHC:    Morphine (16) – requires prior auth, excluded by default
#   Humana: Cyclophosphamide (17) – not covered
# ─────────────────────────────────────────────

def formulary_row(company, drug_id, tier, copay_per_30, not_covered=False):
    return Formulary(
        insurance_company_id=company.id,
        drug_id=drug_id,
        tier=tier,
        copay_per_30=Decimal(str(copay_per_30)),
        not_covered=not_covered,
    )

# Tier assignments per drug_id
# (drug_id, tier)
DRUG_TIERS = {
    1:  1,   # Tylenol
    2:  1,   # Amoxicillin
    3:  4,   # Cisplatin
    4:  1,   # Metformin
    5:  1,   # Ibuprofen
    6:  1,   # Aspirin
    7:  1,   # Lisinopril
    8:  1,   # Hydrochlorothiazide
    9:  1,   # Warfarin
    10: 2,   # Atorvastatin
    11: 2,   # Omeprazole
    12: 1,   # Prednisone
    13: 3,   # Insulin
    14: 4,   # Methotrexate
    15: 2,   # Alprazolam
    16: 3,   # Morphine
    17: 4,   # Cyclophosphamide
    18: 2,   # Ceftriaxone
    19: 2,   # Azithromycin
    20: 1,   # Furosemide
}

TIER_COPAYS = {
    bcbs.id:   {1: "10.00", 2: "40.00", 3: "75.00",  4: "150.00"},
    aetna.id:  {1: "12.00", 2: "45.00", 3: "80.00",  4: "175.00"},
    cigna.id:  {1: "8.00",  2: "35.00", 3: "70.00",  4: "150.00"},
    uhc.id:    {1: "15.00", 2: "50.00", 3: "85.00",  4: "200.00"},
    humana.id: {1: "10.00", 2: "42.00", 3: "78.00",  4: "160.00"},
}

NOT_COVERED = {
    aetna.id:  {16},          # Morphine
    cigna.id:  {3},           # Cisplatin
    uhc.id:    {16},          # Morphine
    humana.id: {17},          # Cyclophosphamide
}

formulary_entries = []
for company in [bcbs, aetna, cigna, uhc, humana]:
    not_covered_set = NOT_COVERED.get(company.id, set())
    copay_map = TIER_COPAYS[company.id]
    for drug_id, tier in DRUG_TIERS.items():
        nc = drug_id in not_covered_set
        copay = copay_map[tier] if not nc else "0.00"
        formulary_entries.append(formulary_row(company, drug_id, tier, copay, nc))

db.add_all(formulary_entries)
db.commit()
print(f"Added {len(formulary_entries)} formulary entries.")

# ─────────────────────────────────────────────
# PATIENT INSURANCE ASSIGNMENTS
# Assign sample insurances to the first 10 patients
# ─────────────────────────────────────────────
patients = db.query(Patient).order_by(Patient.id).limit(10).all()

sample_assignments = [
    # patient 1 – Alice Smith – BCBS primary
    PatientInsurance(patient_id=patients[0].id, insurance_company_id=bcbs.id,
                     member_id="BCBS-001-A8821", group_number="GRP-10042", is_primary=True,  is_active=True),
    # patient 1 – Alice Smith – Aetna secondary
    PatientInsurance(patient_id=patients[0].id, insurance_company_id=aetna.id,
                     member_id="AET-001-X7731", group_number="GRP-20011", is_primary=False, is_active=True),

    # patient 2 – John Stockton – UHC primary
    PatientInsurance(patient_id=patients[1].id, insurance_company_id=uhc.id,
                     member_id="UHC-002-B3344", group_number="GRP-30055", is_primary=True,  is_active=True),

    # patient 3 – Maria Lopez – Cigna primary
    PatientInsurance(patient_id=patients[2].id, insurance_company_id=cigna.id,
                     member_id="CGN-003-C9921", group_number="GRP-40066", is_primary=True,  is_active=True),

    # patient 4 – David Kim – Humana primary
    PatientInsurance(patient_id=patients[3].id, insurance_company_id=humana.id,
                     member_id="HUM-004-D1155", group_number="GRP-50077", is_primary=True,  is_active=True),

    # patient 5 – Emily Johnson – Aetna primary
    PatientInsurance(patient_id=patients[4].id, insurance_company_id=aetna.id,
                     member_id="AET-005-E4422", group_number="GRP-60088", is_primary=True,  is_active=True),

    # patient 6 – Michael Brown – BCBS primary
    PatientInsurance(patient_id=patients[5].id, insurance_company_id=bcbs.id,
                     member_id="BCBS-006-F7733", group_number="GRP-10042", is_primary=True,  is_active=True),

    # patient 7 – Sophia Davis – UHC primary
    PatientInsurance(patient_id=patients[6].id, insurance_company_id=uhc.id,
                     member_id="UHC-007-G2211", group_number="GRP-30055", is_primary=True,  is_active=True),

    # patient 8 – Daniel Wilson – Cigna primary
    PatientInsurance(patient_id=patients[7].id, insurance_company_id=cigna.id,
                     member_id="CGN-008-H6644", group_number="GRP-40066", is_primary=True,  is_active=True),

    # patient 9 – Olivia Martinez – Humana primary
    PatientInsurance(patient_id=patients[8].id, insurance_company_id=humana.id,
                     member_id="HUM-009-I9988", group_number="GRP-50077", is_primary=True,  is_active=True),

    # patient 10 – James Garcia – BCBS primary + Cigna secondary
    PatientInsurance(patient_id=patients[9].id, insurance_company_id=bcbs.id,
                     member_id="BCBS-010-J3377", group_number="GRP-10042", is_primary=True,  is_active=True),
    PatientInsurance(patient_id=patients[9].id, insurance_company_id=cigna.id,
                     member_id="CGN-010-J8855", group_number="GRP-40066", is_primary=False, is_active=True),
]

db.add_all(sample_assignments)
db.commit()
print(f"Added {len(sample_assignments)} patient insurance assignments.")

db.close()
print("Insurance seed complete.")
