# backend/app/seed_drugs.py
"""
Seed 100 additional drugs into the drugs table and randomly assign
stock entries for roughly 80% of them.

Run from backend/:
    .venv/Scripts/python -m app.seed_drugs
"""
import random
from decimal import Decimal

from .database import SessionLocal
from .models import Drug, DrugForm, Stock

random.seed(42)

# (drug_name, ndc, manufacturer, cost, niosh, drug_class, description, drug_form)
DRUG_DATA = [
    # Class 1 — OTC / Analgesics
    ("Acetaminophen 500mg",  "00182-0436-01", "Amneal",       "0.08",  False, 1, "White caplet, imprint 'AM 500'",             DrugForm.tablet),
    ("Naproxen 220mg",       "00280-2920-01", "Bayer",        "0.12",  False, 1, "Blue oval tablet, imprint 'ALEVE'",           DrugForm.tablet),
    ("Diphenhydramine 25mg", "00280-0407-10", "Bayer",        "0.06",  False, 1, "Pink oval capsule, imprint 'DPH 25'",         DrugForm.capsule),
    ("Cetirizine 10mg",      "00573-0168-10", "Perrigo",      "0.15",  False, 1, "White oval tablet, imprint 'CE 10'",          DrugForm.tablet),
    ("Loratadine 10mg",      "00085-1241-01", "Schering",     "0.14",  False, 1, "White round tablet, imprint 'L 10'",          DrugForm.tablet),
    ("Fexofenadine 180mg",   "00088-1090-47", "Sanofi",       "0.35",  False, 1, "Peach oval tablet, imprint 'FX 180'",         DrugForm.tablet),
    ("Famotidine 20mg",      "00006-0963-54", "Merck",        "0.10",  False, 1, "Beige round tablet, imprint 'MSD 963'",       DrugForm.tablet),
    ("Ranitidine 150mg",     "00173-0394-40", "GSK",          "0.08",  False, 1, "Tan round tablet, imprint 'R 150'",           DrugForm.tablet),
    ("Calcium Carbonate 500mg","00536-1027-85","Major",       "0.04",  False, 1, "White oval tablet, imprint 'CALTRATE'",       DrugForm.tablet),
    ("Magnesium Oxide 400mg","00904-5788-60", "Major",        "0.05",  False, 1, "White oval tablet, imprint 'MG 400'",         DrugForm.tablet),
    # Class 2 — Antibiotics
    ("Amoxicillin-Clavulanate 875mg","00029-6980-21","GSK",   "1.20",  False, 2, "White oval tablet, imprint 'AUGMENTIN 875'",  DrugForm.tablet),
    ("Doxycycline 100mg",    "00069-0590-50", "Pfizer",       "0.45",  False, 2, "Yellow capsule, imprint 'PFIZER 095'",        DrugForm.capsule),
    ("Ciprofloxacin 500mg",  "00026-8512-51", "Bayer",        "0.80",  False, 2, "White oval tablet, imprint 'CIPRO 500'",      DrugForm.tablet),
    ("Metronidazole 500mg",  "00054-8527-25", "Roxane",       "0.30",  False, 2, "White oval tablet, imprint 'MET 500'",        DrugForm.tablet),
    ("Clindamycin 300mg",    "00009-0395-02", "Pfizer",       "0.90",  False, 2, "Blue/white capsule, imprint 'CLEOCIN 300'",   DrugForm.capsule),
    ("Trimethoprim-Sulfamethoxazole 800/160mg","00049-0140-20","Pfizer","0.25",False,2,"White oval tablet, imprint 'TMP-SMX'",  DrugForm.tablet),
    ("Nitrofurantoin 100mg", "00015-5901-60", "Actavis",      "0.60",  False, 2, "Yellow capsule, imprint 'NITRO 100'",         DrugForm.capsule),
    ("Levofloxacin 500mg",   "00045-1526-50", "Janssen",      "1.50",  False, 2, "Peach oval tablet, imprint 'LEVA 500'",       DrugForm.tablet),
    ("Clarithromycin 500mg", "00074-3368-60", "Abbott",       "1.10",  False, 2, "Yellow oval tablet, imprint 'KT'",            DrugForm.tablet),
    ("Cephalexin 500mg",     "00781-2604-20", "Sandoz",       "0.55",  False, 2, "Light green capsule, imprint 'CEPHALEXIN 500'", DrugForm.capsule),
    ("Penicillin VK 500mg",  "00093-4185-05", "Teva",         "0.15",  False, 2, "White oval tablet, imprint 'TVA 93 4185'",    DrugForm.tablet),
    ("Vancomycin 250mg",     "00074-3340-01", "Abbott",       "4.50",  False, 2, "Blue capsule, imprint 'VANCOMYCIN 250'",      DrugForm.capsule),
    ("Linezolid 600mg",      "00049-3980-28", "Pfizer",       "28.00", False, 2, "White oval tablet, imprint 'ZYVOX 600'",      DrugForm.tablet),
    # Class 3 — Chemotherapy / NIOSH Hazardous
    ("Carboplatin 50mg/5mL", "00703-4290-11", "Teva",         "18.00", True,  3, "Clear solution in vial - NIOSH HAZARDOUS",   DrugForm.injection),
    ("Paclitaxel 30mg/5mL",  "00703-4980-11", "Teva",         "45.00", True,  3, "Clear solution in vial - NIOSH HAZARDOUS",   DrugForm.injection),
    ("Docetaxel 20mg/0.5mL", "00004-1929-01", "Roche",        "55.00", True,  3, "Clear solution in vial - NIOSH HAZARDOUS",   DrugForm.injection),
    ("Fluorouracil 500mg/10mL","00703-4158-11","Teva",        "12.00", True,  3, "Clear solution in vial - NIOSH HAZARDOUS",   DrugForm.injection),
    ("Gemcitabine 200mg",    "00002-7501-01", "Lilly",        "22.00", True,  3, "White lyophilized powder - NIOSH HAZARDOUS", DrugForm.injection),
    ("Oxaliplatin 50mg",     "00069-9140-11", "Pfizer",       "38.00", True,  3, "Lyophilized powder in vial - NIOSH HAZARDOUS", DrugForm.injection),
    ("Imatinib 400mg",       "00078-0423-15", "Novartis",     "90.00", True,  3, "Yellow oval tablet, imprint 'GLIVEC 400' - NIOSH HAZARDOUS", DrugForm.tablet),
    ("Lenalidomide 25mg",    "59148-0007-05", "Celgene",      "300.00",True,  3, "Blue/white capsule - NIOSH HAZARDOUS",       DrugForm.capsule),
    ("Thalidomide 100mg",    "59148-0009-10", "Celgene",      "85.00", True,  3, "White capsule - NIOSH HAZARDOUS",            DrugForm.capsule),
    # Class 4 — Cardiovascular / Chronic Disease
    ("Amlodipine 10mg",      "00069-1540-68", "Pfizer",       "0.10",  False, 4, "White round tablet, imprint 'NORVASC 10'",   DrugForm.tablet),
    ("Metoprolol Succinate 50mg","00186-1088-05","AstraZeneca","0.20", False, 4, "White oval tablet, imprint 'A/ME 50'",        DrugForm.tablet),
    ("Carvedilol 25mg",      "00007-4140-20", "GSK",          "0.15",  False, 4, "White oval tablet, imprint 'COREG 25'",       DrugForm.tablet),
    ("Losartan 50mg",        "00006-0952-54", "Merck",        "0.18",  False, 4, "White oval tablet, imprint 'MSD 952'",        DrugForm.tablet),
    ("Valsartan 160mg",      "00078-0358-15", "Novartis",     "0.25",  False, 4, "Dark grey oval tablet, imprint 'NVR DO'",     DrugForm.tablet),
    ("Ramipril 10mg",        "00088-2103-28", "Sanofi",       "0.22",  False, 4, "Yellow oblong capsule, imprint 'ALTACE 10'",  DrugForm.capsule),
    ("Enalapril 10mg",       "00006-0713-54", "Merck",        "0.12",  False, 4, "Peach triangular tablet, imprint 'MSD 713'",  DrugForm.tablet),
    ("Spironolactone 25mg",  "00025-1971-31", "Pfizer",       "0.15",  False, 4, "Tan round tablet, imprint 'ALDACTONE 25'",   DrugForm.tablet),
    ("Digoxin 0.125mg",      "00173-0242-55", "GSK",          "0.20",  False, 4, "Yellow round tablet, imprint 'LANOXIN X3A'", DrugForm.tablet),
    ("Amiodarone 200mg",     "00187-0020-30", "Upsher-Smith", "0.50",  False, 4, "White round tablet, imprint 'CORDARONE 200'", DrugForm.tablet),
    ("Diltiazem 120mg",      "00065-0617-01", "Mylan",        "0.30",  False, 4, "White round tablet, imprint 'DILTIAZEM 120'", DrugForm.tablet),
    ("Pravastatin 40mg",     "00003-0182-58", "BMS",          "0.18",  False, 4, "Green oval tablet, imprint 'PRAVACHOL 40'",  DrugForm.tablet),
    ("Rosuvastatin 20mg",    "00310-0755-90", "AstraZeneca",  "0.35",  False, 4, "Pink round tablet, imprint 'CRESTOR 20'",    DrugForm.tablet),
    ("Simvastatin 40mg",     "00006-0543-54", "Merck",        "0.10",  False, 4, "Peach oval tablet, imprint 'ZOCOR 40'",      DrugForm.tablet),
    ("Ezetimibe 10mg",       "00006-0263-54", "Merck",        "0.80",  False, 4, "White capsule-shaped tablet, imprint 'ZETIA 10'", DrugForm.tablet),
    ("Fenofibrate 145mg",    "00074-6214-90", "Abbott",       "0.60",  False, 4, "White oval tablet, imprint 'TRICOR 145'",    DrugForm.tablet),
    ("Clopidogrel 75mg",     "63653-1050-18", "Sanofi",       "0.25",  False, 4, "Pink round tablet, imprint 'PLAVIX 75'",     DrugForm.tablet),
    ("Apixaban 5mg",         "00003-0893-51", "BMS",          "7.50",  False, 4, "Yellow round tablet, imprint 'ELIQUIS 5'",   DrugForm.tablet),
    ("Rivaroxaban 20mg",     "50458-0579-30", "Janssen",      "8.00",  False, 4, "Dark red oval tablet, imprint 'XARELTO 20'", DrugForm.tablet),
    ("Dabigatran 150mg",     "00597-0149-30", "Boehringer",   "7.20",  False, 4, "Blue/cream capsule, imprint 'PRADAXA 150'",  DrugForm.capsule),
    # Class 5 — Endocrine / Metabolic
    ("Levothyroxine 100mcg", "00048-1040-03", "AbbVie",       "0.18",  False, 5, "Yellow round tablet, imprint 'SYNTHROID 100'", DrugForm.tablet),
    ("Levothyroxine 50mcg",  "00048-1020-03", "AbbVie",       "0.16",  False, 5, "White round tablet, imprint 'SYNTHROID 50'",  DrugForm.tablet),
    ("Glipizide 10mg",       "00069-2810-66", "Pfizer",       "0.10",  False, 5, "White round tablet, imprint 'GLUCOTROL 10'", DrugForm.tablet),
    ("Glyburide 5mg",        "00009-0041-02", "Pfizer",       "0.08",  False, 5, "White oval tablet, imprint 'MICRONASE 5'",   DrugForm.tablet),
    ("Sitagliptin 100mg",    "00006-0277-54", "Merck",        "4.50",  False, 5, "Beige round tablet, imprint 'JANUVIA 100'",  DrugForm.tablet),
    ("Empagliflozin 10mg",   "00597-0200-30", "Boehringer",   "9.00",  False, 5, "Pale yellow oval tablet, imprint 'JARDIANCE 10'", DrugForm.tablet),
    ("Dulaglutide 1.5mg/0.5mL","00002-1433-80","Lilly",      "30.00", False, 5, "Single-dose pen injector - REFRIGERATE",      DrugForm.injection),
    ("Semaglutide 1mg/0.5mL","00169-4175-11","Novo Nordisk",  "40.00", False, 5, "Solution in pre-filled pen - REFRIGERATE",    DrugForm.injection),
    ("Pioglitazone 30mg",    "64764-0300-60", "Takeda",       "0.25",  False, 5, "White round tablet, imprint 'ACTOS 30'",      DrugForm.tablet),
    ("Desmopressin 0.2mg",   "00078-0116-15", "Novartis",     "1.20",  False, 5, "White oval tablet, imprint 'DDAVP 0.2'",      DrugForm.tablet),
    ("Methimazole 10mg",     "00054-4084-25", "Roxane",       "0.30",  False, 5, "White round tablet, imprint 'TAPAZOLE 10'",   DrugForm.tablet),
    # Class 6 — Pain / Opioids
    ("Oxycodone 5mg",        "59011-0105-10", "Purdue",       "0.80",  False, 6, "Round blue tablet, imprint 'OC 5' - CONTROLLED SUBSTANCE",                        DrugForm.tablet),
    ("Hydrocodone-Acetaminophen 5/325mg","35356-0008-10","Epic","0.60",False, 6, "White oblong tablet, imprint 'VICODIN' - CONTROLLED SUBSTANCE",                   DrugForm.tablet),
    ("Tramadol 50mg",        "00009-5272-04", "Pfizer",       "0.20",  False, 6, "White round tablet, imprint 'TR 50'",                                             DrugForm.tablet),
    ("Buprenorphine 8mg",    "12496-1283-01", "Reckitt",      "5.00",  False, 6, "Orange hexagonal film, imprint 'N8' - CONTROLLED SUBSTANCE",                      DrugForm.film),
    ("Naloxone 0.4mg/mL",    "00469-0485-10", "Hospira",      "3.50",  False, 6, "Clear solution in vial",                                                          DrugForm.injection),
    ("Fentanyl 50mcg/hr patch","00093-7710-56","Teva",        "12.00", True,  6, "Transdermal patch - NIOSH HAZARDOUS CONTROLLED SUBSTANCE",                        DrugForm.patch),
    ("Methadone 10mg",       "00054-4571-25", "Roxane",       "0.25",  False, 6, "White round tablet, imprint 'METHADONE 10'",                                      DrugForm.tablet),
    ("Gabapentin 300mg",     "00025-2580-60", "Pfizer",       "0.12",  False, 6, "Yellow/white capsule, imprint 'NEURONTIN 300'",                                   DrugForm.capsule),
    ("Pregabalin 150mg",     "00071-1015-68", "Pfizer",       "1.80",  False, 6, "White capsule, imprint 'PGN 150'",                                                DrugForm.capsule),
    ("Cyclobenzaprine 10mg", "00009-0071-02", "Pfizer",       "0.15",  False, 6, "Yellow round tablet, imprint 'FLEXERIL 10'",                                      DrugForm.tablet),
    # Class 7 — CNS / Controlled Substances
    ("Zolpidem 10mg",        "00024-5930-10", "Sanofi",       "0.40",  False, 7, "White oval tablet, imprint 'AMB 10' - CONTROLLED SUBSTANCE",                      DrugForm.tablet),
    ("Lorazepam 1mg",        "00009-0581-02", "Pfizer",       "0.30",  False, 7, "White round tablet, imprint 'WYETH 81' - CONTROLLED SUBSTANCE",                   DrugForm.tablet),
    ("Clonazepam 0.5mg",     "00069-1651-66", "Pfizer",       "0.20",  False, 7, "Orange round tablet, imprint 'KLONOPIN 0.5' - CONTROLLED SUBSTANCE",              DrugForm.tablet),
    ("Diazepam 5mg",         "00009-0353-02", "Pfizer",       "0.15",  False, 7, "Yellow round tablet, imprint 'VALIUM 5' - CONTROLLED SUBSTANCE",                  DrugForm.tablet),
    ("Methylphenidate 20mg", "00056-0516-60", "McNeil",       "0.50",  False, 7, "White round tablet, imprint 'RITALIN 20' - CONTROLLED SUBSTANCE",                 DrugForm.tablet),
    ("Amphetamine-Dextroamphetamine 20mg","57844-0110-01","Shire","2.50",False,7,"Peach round tablet, imprint 'ADDERALL 20' - CONTROLLED SUBSTANCE",               DrugForm.tablet),
    ("Atomoxetine 40mg",     "00002-3229-30", "Lilly",        "4.00",  False, 7, "Gold/blue capsule, imprint 'STRATTERA 40'",                                       DrugForm.capsule),
    ("Sertraline 100mg",     "00049-4910-66", "Pfizer",       "0.20",  False, 7, "White oval tablet, imprint 'ZOLOFT 100'",                                         DrugForm.tablet),
    ("Escitalopram 20mg",    "00456-2020-30", "Forest",       "0.25",  False, 7, "White round tablet, imprint 'LEXAPRO 20'",                                        DrugForm.tablet),
    ("Fluoxetine 20mg",      "00777-3105-02", "Dista",        "0.15",  False, 7, "Green/white capsule, imprint 'DISTA 3105'",                                       DrugForm.capsule),
    ("Bupropion XL 300mg",   "00173-0717-55", "GSK",          "0.35",  False, 7, "Purple round tablet, imprint 'WELLBUTRIN XL 300'",                                DrugForm.tablet),
    ("Duloxetine 60mg",      "00002-3237-30", "Lilly",        "0.80",  False, 7, "Blue/grey capsule, imprint 'CYMBALTA 60'",                                        DrugForm.capsule),
    ("Venlafaxine XR 150mg", "00008-4105-60", "Wyeth",        "0.45",  False, 7, "Peach capsule, imprint 'EFFEXOR XR 150'",                                         DrugForm.capsule),
    ("Mirtazapine 30mg",     "00052-0106-30", "Organon",      "0.20",  False, 7, "Red-brown round tablet, imprint 'REMERON 30'",                                    DrugForm.tablet),
    ("Quetiapine 200mg",     "00310-0273-60", "AstraZeneca",  "0.90",  False, 7, "Peach round tablet, imprint 'SEROQUEL 200'",                                      DrugForm.tablet),
    ("Aripiprazole 10mg",    "59148-0005-60", "BMS",          "2.50",  False, 7, "Pink rectangular tablet, imprint 'ABILIFY 10'",                                   DrugForm.tablet),
    ("Olanzapine 10mg",      "00002-4116-30", "Lilly",        "0.60",  False, 7, "White round tablet, imprint 'ZYPREXA 10'",                                        DrugForm.tablet),
    ("Risperidone 2mg",      "50458-0321-30", "Janssen",      "0.40",  False, 7, "Orange round tablet, imprint 'RISPERDAL 2'",                                      DrugForm.tablet),
    ("Lithium Carbonate 300mg","00074-6788-13","Abbott",       "0.10",  False, 7, "Peach capsule, imprint 'ESKALITH 300'",                                           DrugForm.capsule),
    ("Topiramate 100mg",     "50458-0046-10", "Janssen",      "0.30",  False, 7, "Yellow round tablet, imprint 'TOPAMAX 100'",                                      DrugForm.tablet),
    ("Lamotrigine 150mg",    "00173-0637-60", "GSK",          "0.35",  False, 7, "Peach round tablet, imprint 'LAMICTAL 150'",                                      DrugForm.tablet),
    ("Valproic Acid 500mg",  "00074-6214-13", "Abbott",       "0.40",  False, 7, "Peach oval tablet, imprint 'DEPAKOTE 500'",                                       DrugForm.tablet),
    ("Levetiracetam 500mg",  "00131-2626-37", "Actavis",      "0.20",  False, 7, "Blue oval tablet, imprint 'KEPPRA 500'",                                          DrugForm.tablet),
    ("Donepezil 10mg",       "00062-1539-30", "Eisai",        "0.50",  False, 7, "Yellow round tablet, imprint 'ARICEPT 10'",                                       DrugForm.tablet),
    ("Sumatriptan 100mg",    "00007-4137-02", "GSK",          "2.00",  False, 7, "Pink triangular tablet, imprint 'IMITREX 100'",                                   DrugForm.tablet),
    ("Ondansetron 8mg",      "00173-0447-00", "GSK",          "0.40",  False, 7, "Yellow oval tablet, imprint 'GX CG2'",                                            DrugForm.tablet),
    ("Promethazine 25mg",    "00008-0227-02", "Wyeth",        "0.10",  False, 7, "White round tablet, imprint 'PHENERGAN 25'",                                      DrugForm.tablet),
]

assert len(DRUG_DATA) == 100, f"Expected 100 drugs, got {len(DRUG_DATA)}"


def run() -> None:
    db = SessionLocal()
    try:
        drugs = [
            Drug(
                drug_name=name,
                ndc=ndc,
                manufacturer=manufacturer,
                cost=Decimal(cost),
                niosh=niosh,
                drug_class=drug_class,
                description=description,
                drug_form=drug_form,
            )
            for name, ndc, manufacturer, cost, niosh, drug_class, description, drug_form in DRUG_DATA
        ]
        db.add_all(drugs)
        db.flush()  # get IDs assigned

        # Add stock for ~80% of the new drugs (randomly chosen)
        package_sizes = [30, 50, 100, 250, 500]
        stock_entries = []
        for drug in drugs:
            if random.random() < 0.80:
                pkg = random.choice(package_sizes)
                qty = random.randint(1, 10) * pkg  # 1–10 full packages
                stock_entries.append(Stock(drug_id=drug.id, quantity=qty, package_size=pkg))

        db.add_all(stock_entries)
        db.commit()

        stocked = len(stock_entries)
        print(f"Inserted {len(drugs)} drugs and {stocked} stock entries.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
