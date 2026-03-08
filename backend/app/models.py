from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Date, DateTime, Enum, ForeignKey, Float, Numeric
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime, timezone
import enum


class Priority(str, enum.Enum):
    low = "Low"
    normal = "Normal"
    high = "High"
    stat = "Stat"


class RxState(str, enum.Enum):
    QT = "QT" # Queue Triage
    QV1 = "QV1" # Verify 1
    QP = "QP" # Prep/Fill
    QV2 = "QV2" # Final Verify
    READY = "READY" # Ready for Pickup (with bin assignment)
    HOLD = "HOLD" # On Hold
    SCHEDULED = "SCHEDULED" # Scheduled for future fill
    REJECTED = "REJECTED" # Rejected/Failed Verification
    SOLD = "SOLD"


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    dob = Column(Date)
    address = Column(String)

    prescriptions = relationship("Prescription", back_populates="patient", lazy="selectin")
    refills = relationship("Refill", back_populates="patient", lazy="selectin")
    refill_history = relationship("RefillHist", back_populates="patient", lazy="selectin")
    insurances = relationship("PatientInsurance", back_populates="patient", lazy="selectin")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    brand_required = Column(Boolean)
    original_quantity = Column(Integer)
    remaining_quantity = Column(Integer)
    date_received = Column(Date)
    instructions = Column(String, nullable=True)  # sig/directions for the dispensed drug

    patient_id = Column(Integer, ForeignKey("patients.id"))
    patient = relationship("Patient", back_populates="prescriptions")
    prescriber_id = Column(Integer, ForeignKey("prescribers.id"))
    prescriber = relationship("Prescriber", back_populates="prescriptions")
    refills = relationship("Refill", back_populates="prescription", lazy="selectin")
    refill_history = relationship("RefillHist", back_populates="prescription", lazy="selectin")
    drug = relationship("Drug", back_populates="prescriptions")



class Refill(Base):
    __tablename__ = "refills"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"))
    patient_id = Column(Integer, ForeignKey("patients.id"))
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    due_date = Column(Date)
    quantity = Column(Integer)
    days_supply = Column(Integer)
    total_cost = Column(Numeric(10, 2), nullable=False)
    priority = Column(Enum(Priority), default=Priority.normal)
    state = Column(Enum(RxState), default=RxState.QT, index=True)
    completed_date = Column(Date)

    # Workflow fields
    bin_number = Column(Integer, nullable=True)
    rejected_by = Column(String, nullable=True)
    rejection_reason = Column(String, nullable=True)
    rejection_date = Column(Date, nullable=True)
    source = Column(String, default="manual")

    # Billing fields
    insurance_id = Column(Integer, ForeignKey("patient_insurance.id"), nullable=True)
    copay_amount = Column(Numeric(10, 2), nullable=True)
    insurance_paid = Column(Numeric(10, 2), nullable=True)

    # relationships
    prescription = relationship("Prescription", back_populates="refills", lazy="joined")
    patient = relationship("Patient", back_populates="refills", lazy="joined")
    drug = relationship("Drug", back_populates="refills", lazy="joined")
    insurance = relationship("PatientInsurance", lazy="joined")


class RefillHist(Base):
    __tablename__ = "refill_hist"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"))
    patient_id = Column(Integer, ForeignKey("patients.id"))
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    quantity = Column(Integer)
    days_supply = Column(Integer)
    completed_date = Column(Date)
    sold_date = Column(Date)
    total_cost = Column(Numeric(10, 2), nullable=False)

    # Billing fields
    insurance_id = Column(Integer, ForeignKey("patient_insurance.id"), nullable=True)
    copay_amount = Column(Numeric(10, 2), nullable=True)
    insurance_paid = Column(Numeric(10, 2), nullable=True)

    # relationships
    prescription = relationship("Prescription", back_populates="refill_history", lazy="joined")
    patient = relationship("Patient", back_populates="refill_history", lazy="joined")
    drug = relationship("Drug", back_populates="refill_history", lazy="joined")
    insurance = relationship("PatientInsurance", lazy="joined")



class Prescriber(Base):
    __tablename__ = "prescribers"

    id = Column(Integer, primary_key=True, index=True)
    npi = Column(BigInteger)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    address = Column(String)
    phone_number = Column(String)
    specialty = Column(String, nullable=True)
    prescriptions = relationship("Prescription", back_populates="prescriber", lazy="selectin")


class Drug(Base):
    __tablename__ = "drugs"
    id = Column(Integer, primary_key=True, index=True)
    drug_name = Column(String, index=True)
    ndc = Column(String, nullable=True)
    manufacturer = Column(String)
    cost = Column(Numeric(10, 2), nullable=False)
    niosh = Column(Boolean, default=False)
    drug_class = Column(Integer)
    description = Column(String, nullable=True)

    refills = relationship("Refill", back_populates="drug", lazy="selectin")
    stock = relationship("Stock", back_populates="drug", uselist=False)
    refill_history = relationship("RefillHist", back_populates="drug", lazy="selectin")
    prescriptions = relationship("Prescription", back_populates="drug")
    formulary_entries = relationship("Formulary", back_populates="drug")


class Stock(Base):
    __tablename__ = "stock"

    drug_id = Column(Integer, ForeignKey("drugs.id"), primary_key=True)
    quantity = Column(Integer, default=0)
    package_size = Column(Integer, default=100)

    drug = relationship("Drug", lazy="joined")


class InsuranceCompany(Base):
    __tablename__ = "insurance_companies"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(String, unique=True, index=True)
    plan_name = Column(String)
    bin_number = Column(String, nullable=True)
    pcn = Column(String, nullable=True)
    phone_number = Column(String, nullable=True)

    formulary = relationship("Formulary", back_populates="insurance_company", lazy="selectin")
    patient_insurances = relationship("PatientInsurance", back_populates="insurance_company")


class Formulary(Base):
    __tablename__ = "formulary"

    id = Column(Integer, primary_key=True, index=True)
    insurance_company_id = Column(Integer, ForeignKey("insurance_companies.id"))
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    tier = Column(Integer)  # 1=Preferred Generic, 2=Preferred Brand, 3=Non-Preferred, 4=Specialty
    copay_per_30 = Column(Numeric(10, 2))  # Patient's copay for a 30-day supply
    not_covered = Column(Boolean, default=False)

    insurance_company = relationship("InsuranceCompany", back_populates="formulary")
    drug = relationship("Drug", back_populates="formulary_entries")


class PatientInsurance(Base):
    __tablename__ = "patient_insurance"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"))
    insurance_company_id = Column(Integer, ForeignKey("insurance_companies.id"))
    member_id = Column(String)
    group_number = Column(String, nullable=True)
    is_primary = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)

    patient = relationship("Patient", back_populates="insurances")
    insurance_company = relationship("InsuranceCompany", back_populates="patient_insurances", lazy="joined")


class AuditLog(Base):
    """Immutable audit trail for all significant pharmacy actions."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    # Human-readable action name, e.g. FILL_CREATED, STATE_TRANSITION, PATIENT_CREATED
    action = Column(String, nullable=False, index=True)
    # What kind of record was affected
    entity_type = Column(String, nullable=True)   # "refill" | "prescription" | "patient"
    entity_id = Column(Integer, nullable=True)
    # Free-form detail string (keep short — one line describing what changed)
    details = Column(String, nullable=True)
