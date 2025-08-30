from sqlalchemy import Column, Integer, String, Date, Enum, ForeignKey
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
    DONE = "DONE"


class Patient(Base):
    __tablename__ = "patients"


    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    dob = Column(Date)
    address = Column(String)


    prescriptions = relationship("Prescription", back_populates="patient")


class Prescription(Base):
    __tablename__ = "prescriptions"


    id = Column(Integer, primary_key=True, index=True)
    drug_name = Column(String, index=True)
    quantity = Column(Integer)
    due_date = Column(Date)
    priority = Column(Enum(Priority), default=Priority.normal)
    state = Column(Enum(RxState), default=RxState.QT, index=True)
    
    
    patient_id = Column(Integer, ForeignKey("patients.id"))
    patient = relationship("Patient", back_populates="prescriptions")
