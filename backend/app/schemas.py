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
    class Config:
        from_attributes = True

class DrugBase(BaseModel):
    drug_name: str
    manufacturer: str
    niosh: bool = False

class DrugOut(BaseModel):
    id: int
    class Config:
        from_attributes = True

class PrescriptionBase(BaseModel):
    drug_name: str
    quantity: int
    due_date: date
    priority: str
    state: str


class PrescriptionOut(PrescriptionBase):
    id: int
    patient_id: int
class Config:
    from_attributes = True


class PatientWithRxs(PatientOut):
    prescriptions: List[PrescriptionOut] = []


class AdvanceRequest(BaseModel):
    action: Optional[str] = None # reserved for future custom transitions
