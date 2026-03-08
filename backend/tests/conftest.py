"""
conftest.py — shared pytest fixtures for the Pharmacy API test suite.

Uses SQLite (in-memory) so tests run without a real PostgreSQL instance.
Each test gets a fresh database via function-scoped fixtures.

IMPORTANT: DATABASE_URL must be overridden BEFORE any app module is imported,
because app/database.py calls create_engine() at module level.
"""
import os
# Override the DB URL before ANY app import — prevents psycopg2 lookup
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from decimal import Decimal
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# ── App imports (must come AFTER os.environ override above) ──────────────────
from app.main import app
from app.database import Base, get_db
from app.models import (
    Patient, Prescription, Refill, RefillHist,
    Drug, Stock, Prescriber, InsuranceCompany, Formulary,
    PatientInsurance, RxState, Priority,
)

# ---------------------------------------------------------------------------
# In-memory SQLite engine — StaticPool forces all connections to reuse
# the same underlying SQLite connection (required for in-memory DBs so that
# every session sees the same data).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def engine():
    """Create a fresh in-memory SQLite engine per test with StaticPool."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Enable FK enforcement in SQLite
    @event.listens_for(eng, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()


@pytest.fixture(scope="function")
def db_session(engine):
    """Return a SQLAlchemy session bound to the test engine."""
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(engine):
    """
    FastAPI TestClient with get_db dependency overridden to use
    the in-memory SQLite engine.
    """
    TestSession = sessionmaker(bind=engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Seed helpers — create canonical test entities
# ---------------------------------------------------------------------------

def make_prescriber(db) -> Prescriber:
    p = Prescriber(
        npi=1234567890,
        first_name="Alice",
        last_name="Chen",
        address="100 Medical Dr, Springfield",
        phone_number="555-0100",
        specialty="Internal Medicine",
    )
    db.add(p)
    db.flush()
    return p


def make_drug(
    db,
    name="Lisinopril",
    ndc="12345-678-90",
    cost=Decimal("0.50"),
    niosh=False,
) -> Drug:
    d = Drug(
        drug_name=name,
        ndc=ndc,
        manufacturer="GeneriCo",
        cost=cost,
        niosh=niosh,
        drug_class=2,
        description="ACE inhibitor",
    )
    db.add(d)
    db.flush()
    # Always create a stock entry
    s = Stock(drug_id=d.id, quantity=5000, package_size=100)
    db.add(s)
    db.flush()
    return d


def make_patient(
    db,
    first="John",
    last="Doe",
    dob=date(1980, 1, 15),
    address="123 Main St",
) -> Patient:
    p = Patient(first_name=first, last_name=last, dob=dob, address=address)
    db.add(p)
    db.flush()
    return p


def make_prescription(
    db,
    patient: Patient,
    drug: Drug,
    prescriber: Prescriber,
    original_qty=90,
    remaining_qty=90,
    received: date = None,
) -> Prescription:
    rx = Prescription(
        drug_id=drug.id,
        patient_id=patient.id,
        prescriber_id=prescriber.id,
        original_quantity=original_qty,
        remaining_quantity=remaining_qty,
        date_received=received or date.today(),
        instructions="Take 1 tablet by mouth daily",
        brand_required=False,
    )
    db.add(rx)
    db.flush()
    return rx


def make_refill(
    db,
    prescription: Prescription,
    drug: Drug,
    patient: Patient,
    quantity=30,
    days_supply=30,
    state=RxState.QT,
    priority=Priority.normal,
    due_date: date = None,
) -> Refill:
    r = Refill(
        prescription_id=prescription.id,
        patient_id=patient.id,
        drug_id=drug.id,
        quantity=quantity,
        days_supply=days_supply,
        total_cost=Decimal(str(drug.cost)) * quantity,
        state=state,
        priority=priority,
        due_date=due_date or date.today(),
        source="manual",
    )
    db.add(r)
    db.flush()
    return r


def make_insurance(db, plan_id="INS001", plan_name="Blue Shield") -> InsuranceCompany:
    ins = InsuranceCompany(
        plan_id=plan_id,
        plan_name=plan_name,
        bin_number="610493",
        pcn="ADV",
        phone_number="1-800-555-0200",
    )
    db.add(ins)
    db.flush()
    return ins


def make_formulary(
    db,
    insurance: InsuranceCompany,
    drug: Drug,
    tier=1,
    copay_per_30=Decimal("10.00"),
    not_covered=False,
) -> Formulary:
    f = Formulary(
        insurance_company_id=insurance.id,
        drug_id=drug.id,
        tier=tier,
        copay_per_30=copay_per_30,
        not_covered=not_covered,
    )
    db.add(f)
    db.flush()
    return f


def make_patient_insurance(
    db,
    patient: Patient,
    insurance: InsuranceCompany,
    member_id="MBR123",
    is_primary=True,
    is_active=True,
) -> PatientInsurance:
    pi = PatientInsurance(
        patient_id=patient.id,
        insurance_company_id=insurance.id,
        member_id=member_id,
        group_number="GRP001",
        is_primary=is_primary,
        is_active=is_active,
    )
    db.add(pi)
    db.flush()
    return pi


# ---------------------------------------------------------------------------
# Composite fixtures — a fully wired "ready to fill" scenario
# ---------------------------------------------------------------------------

@pytest.fixture
def base_data(db_session):
    """
    Returns a dict with pre-committed patient, drug, prescriber, and prescription.
    prescription has 90 remaining units.
    """
    db = db_session
    prescriber = make_prescriber(db)
    drug = make_drug(db)
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
    db.commit()
    return {
        "db": db,
        "prescriber": prescriber,
        "drug": drug,
        "patient": patient,
        "prescription": prescription,
    }


@pytest.fixture
def insured_data(db_session):
    """
    Patient with active insurance coverage on their drug.
    Formulary tier 1, $10/30-day copay.
    """
    db = db_session
    prescriber = make_prescriber(db)
    drug = make_drug(db, cost=Decimal("1.00"))
    patient = make_patient(db)
    prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
    insurance = make_insurance(db)
    formulary = make_formulary(db, insurance, drug, tier=1, copay_per_30=Decimal("10.00"))
    patient_ins = make_patient_insurance(db, patient, insurance)
    db.commit()
    return {
        "db": db,
        "prescriber": prescriber,
        "drug": drug,
        "patient": patient,
        "prescription": prescription,
        "insurance": insurance,
        "formulary": formulary,
        "patient_ins": patient_ins,
    }
