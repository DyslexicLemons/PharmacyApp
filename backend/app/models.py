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


class DrugForm(str, enum.Enum):
    """Physical/delivery form of a drug — drives SIG code translation defaults."""
    tablet = "Tablet"
    capsule = "Capsule"
    liquid = "Liquid"          # oral solution / suspension
    injection = "Injection"    # vial, syringe, pen injector
    patch = "Patch"            # transdermal patch
    film = "Film"              # sublingual / buccal film
    topical = "Topical"        # cream, ointment, gel
    inhaler = "Inhaler"        # MDI / DPI
    drops = "Drops"            # eye, ear, or nasal drops
    suppository = "Suppository"
    powder = "Powder"          # oral powder / granules
    unknown = "Unknown"


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
    RTS = "RTS"  # Returned to Stock


class Patient(Base):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    dob = Column(Date)
    address = Column(String)
    city = Column(String, nullable=True)
    state = Column(String, nullable=True)

    prescriptions = relationship("Prescription", back_populates="patient", lazy="selectin")
    refills = relationship("Refill", back_populates="patient", lazy="noload")
    refill_history = relationship("RefillHist", back_populates="patient", lazy="noload")
    insurances = relationship("PatientInsurance", back_populates="patient", lazy="selectin")


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    daw_code = Column(Integer, default=0)  # Dispense As Written code (0-9)
    original_quantity = Column(Integer)
    remaining_quantity = Column(Integer)
    date_received = Column(Date)
    expiration_date = Column(Date, nullable=True)
    instructions = Column(String, nullable=True)  # sig/directions for the dispensed drug
    picture_path = Column(String, nullable=True)  # filesystem path relative to uploads/ dir

    is_inactive = Column(Boolean, default=False, nullable=False, server_default="false")

    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    patient = relationship("Patient", back_populates="prescriptions")
    prescriber_id = Column(Integer, ForeignKey("prescribers.id"))
    prescriber = relationship("Prescriber", back_populates="prescriptions")
    refills = relationship("Refill", back_populates="prescription", lazy="selectin")
    refill_history = relationship("RefillHist", back_populates="prescription", lazy="selectin")
    drug = relationship("Drug", back_populates="prescriptions")



class Refill(Base):
    __tablename__ = "refills"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    due_date = Column(DateTime(timezone=True), nullable=True)
    quantity = Column(Integer)
    days_supply = Column(Integer)
    total_cost = Column(Numeric(10, 2), nullable=False)
    priority = Column(Enum(Priority, values_callable=lambda x: [e.value for e in x]), default=Priority.normal)
    state = Column(Enum(RxState), default=RxState.QT, index=True)
    completed_date = Column(DateTime(timezone=True))

    # Workflow fields
    bin_number = Column(Integer, nullable=True)
    rejected_by = Column(String, nullable=True)
    rejection_reason = Column(String, nullable=True)
    rejection_date = Column(Date, nullable=True)
    triage_reason = Column(String, nullable=True)
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

    @property
    def drug_name(self) -> str:
        return self.drug.drug_name if self.drug else "Unknown"

    @property
    def patient_name(self) -> str:
        if self.patient:
            first = self.patient.first_name or ""
            last = self.patient.last_name or ""
            return f"{first} {last}".strip() or "Unknown"
        return "Unknown"


class RefillHist(Base):
    __tablename__ = "refill_hist"

    id = Column(Integer, primary_key=True, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"))
    patient_id = Column(Integer, ForeignKey("patients.id"))
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    quantity = Column(Integer)
    days_supply = Column(Integer)
    completed_date = Column(DateTime(timezone=True))
    sold_date = Column(DateTime(timezone=True))
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
    npi = Column(BigInteger, unique=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    address = Column(String)
    phone_number = Column(String)
    specialty = Column(String, nullable=True)
    prescriptions = relationship("Prescription", back_populates="prescriber", lazy="noload")


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
    drug_form = Column(Enum(DrugForm, values_callable=lambda x: [e.value for e in x]), nullable=True, default=DrugForm.unknown)

    refills = relationship("Refill", back_populates="drug", lazy="noload")
    stock = relationship("Stock", back_populates="drug", uselist=False)
    refill_history = relationship("RefillHist", back_populates="drug", lazy="noload")
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


class User(Base):
    """Application users for login authentication."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    role = Column(String, nullable=False, default="technician")  # admin | pharmacist | technician


class QuickCode(Base):
    """Short-lived 3-character login codes generated after successful authentication."""
    __tablename__ = "quick_codes"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(3), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)

    user = relationship("User")


class InventoryShipment(Base):
    """Header record for a drug inventory shipment/receiving event."""
    __tablename__ = "inventory_shipments"

    id = Column(Integer, primary_key=True, index=True)
    performed_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    performed_by = Column(String, nullable=False)
    performed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    items = relationship("InventoryShipmentItem", back_populates="shipment", lazy="selectin")


class InventoryShipmentItem(Base):
    """Line item within an inventory shipment — one row per drug received."""
    __tablename__ = "inventory_shipment_items"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(Integer, ForeignKey("inventory_shipments.id"), nullable=False)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False)
    bottles_received = Column(Integer, nullable=False)
    units_per_bottle = Column(Integer, nullable=False, default=100)

    shipment = relationship("InventoryShipment", back_populates="items")
    drug = relationship("Drug", lazy="joined")


class SystemConfig(Base):
    """Singleton table (always id=1) holding pharmacy-wide configuration."""
    __tablename__ = "system_config"

    id = Column(Integer, primary_key=True, default=1)
    bin_count = Column(Integer, nullable=False, default=100)

    # Simulation settings
    simulation_enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    sim_arrival_rate = Column(Integer, nullable=False, default=2)   # max new Rxs per arrival cycle
    sim_reject_rate = Column(Integer, nullable=False, default=10)   # % chance pharmacist rejects at QV1


class SimWorkerRole(str, enum.Enum):
    technician = "technician"
    pharmacist = "pharmacist"


class StationName(str, enum.Enum):
    triage = "triage"       # QT queue — technician intake/triage
    fill = "fill"           # QP queue — technician prep/fill
    verify_1 = "verify_1"  # QV1 queue — pharmacist first verification
    verify_2 = "verify_2"  # QV2 queue — pharmacist final verification
    window = "window"      # READY — patient pickup window


class SimWorker(Base):
    """A virtual pharmacy worker used in simulation.

    Speed (1–10) controls how many refills this worker processes per Celery
    cycle.  is_active lets you bench a worker without deleting them.

    current_station tracks where in the pharmacy the worker is physically
    located. Moving between stations takes 5–10 seconds (busy_until records
    when the worker arrives and becomes available again).
    """
    __tablename__ = "sim_workers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    role = Column(Enum(SimWorkerRole), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    speed = Column(Integer, nullable=False, default=5)  # items per cycle, 1–10
    current_station = Column(Enum(StationName), nullable=True)
    busy_until = Column(DateTime(timezone=True), nullable=True)  # None = available now
    task_started_at = Column(DateTime(timezone=True), nullable=True)  # when current travel began
    current_refill_id = Column(Integer, ForeignKey("refills.id"), nullable=True, index=True)
    current_refill = relationship("Refill", foreign_keys=[current_refill_id], lazy="joined")


class ReturnToStock(Base):
    """Record of a filled prescription returned to stock from the READY bin."""
    __tablename__ = "return_to_stock"

    id = Column(Integer, primary_key=True, index=True)
    refill_id = Column(Integer, ForeignKey("refills.id"), nullable=False, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    returned_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    returned_by = Column(String, nullable=False)
    returned_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    refill = relationship("Refill", lazy="joined")
    drug = relationship("Drug", lazy="joined")


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
    # Optional link to the prescription (RX) this action is about
    prescription_id = Column(Integer, nullable=True, index=True)
    # Who performed the action
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    performed_by = Column(String, nullable=True)  # denormalized username for historical accuracy
