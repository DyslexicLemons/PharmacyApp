from pydantic import BaseModel
from datetime import date
from typing import List, Optional


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: date
    address: str


class PatientOut(PatientBase):
    id: int
    first_name: str
    last_name: str
    class Config:
        from_attributes = True


class PrescriberBase(BaseModel):
    first_name: str
    last_name: str


class PrescriberOut(PrescriberBase):
    id: int
    first_name: str
    last_name: str
    class Config:
        from_attributes = True

class DrugBase(BaseModel):
    drug_name: str
    manufacturer: str
    niosh: bool = False

class DrugOut(BaseModel):
    id: int
    drug_name: str
    manufacturer: str
    niosh: bool

    class Config:
        from_attributes = True

class PrescriptionBase(BaseModel):
    drug_name: str
    original_quantity: int
    remaining_quantity: int
    date_received: date

class PrescriptionOut(PrescriptionBase):
    id: int
    patient_id: int
    drug_name: str
    remaining_quantity: int
    date_received: date

    class Config:
        from_attributes = True


class RefillBase(BaseModel):
    prescription_id: int
    patient_id: int
    drug_id: int
    due_date: date
    quantity: int
    priority: str
    state: str
    completed_date: date

class RefillOut(BaseModel):
    id: int
    prescription_id: int
    patient: PatientOut
    drug: DrugOut
    prescriber: Optional[PrescriberOut] = None
    due_date: date
    quantity: int
    priority: str
    state: str
    completed_date: Optional[date] = None

    class Config:
        from_attributes = True
    

class PatientWithRxs(PatientOut):
    prescriptions: List[PrescriptionOut] = []

    class Config:
        from_attributes = True

class AdvanceRequest(BaseModel):
    action: Optional[str] = None # reserved for future custom transitions
