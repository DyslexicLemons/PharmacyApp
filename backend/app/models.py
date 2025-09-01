from sqlalchemy import Column, Integer, String, Boolean, Date, Enum, ForeignKey, Float
from sqlalchemy.orm import relationship
from .database import Base
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
    DONE = "DONE" # Ready to be sold
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


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    drug_id = Column(Integer, ForeignKey("drugs.id"))
    original_quantity = Column(Integer)
    remaining_quantity = Column(Integer)
    date_received = Column(Date)

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
    priority = Column(Enum(Priority), default=Priority.normal)
    state = Column(Enum(RxState), default=RxState.QT, index=True)
    completed_date = Column(Date)

    # relationships
    prescription = relationship("Prescription", back_populates="refills", lazy="joined")
    patient = relationship("Patient", back_populates="refills", lazy="joined")
    drug = relationship("Drug", back_populates="refills", lazy="joined")


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

    # relationships
    prescription = relationship("Prescription", back_populates="refill_history", lazy="joined")
    patient = relationship("Patient", back_populates="refill_history", lazy="joined")
    drug = relationship("Drug", back_populates="refill_history", lazy="joined")



class Prescriber(Base):
    __tablename__ = "prescribers"

    id = Column(Integer, primary_key=True, index=True)
    npi = Column(Integer)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    address = Column(String)
    phone_number = Column(String)
    prescriptions = relationship("Prescription", back_populates="prescriber", lazy="selectin")


class Drug(Base):
    __tablename__ = "drugs"
    id = Column(Integer, primary_key=True, index=True)
    drug_name = Column(String, index=True)
    manufacturer = Column(String)
    cost = Column(Float)
    niosh = Column(Boolean, default=False)
    drug_class = Column(Integer)

    refills = relationship("Refill", back_populates="drug", lazy="selectin")
    stock = relationship("Stock", back_populates="drug", uselist=False)  # 1:1
    refill_history = relationship("RefillHist", back_populates="drug", lazy="selectin")
    prescriptions = relationship("Prescription", back_populates="drug")


class Stock(Base):
    __tablename__ = "stock"

    drug_id = Column(Integer, ForeignKey("drugs.id"), primary_key=True)  # enforce 1:1 mapping
    quantity = Column(Integer, default=0)

    drug = relationship("Drug", lazy="joined")  # fetch full drug info

