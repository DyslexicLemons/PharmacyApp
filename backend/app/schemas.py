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
    drug_class: int

class DrugOut(BaseModel):
    id: int
    drug_name: str
    manufacturer: str
    niosh: bool
    drug_class: int

    class Config:
        from_attributes = True


class StockBase(BaseModel):
    drug_id: int
    quantity: int

class StockOut(BaseModel):
    drug_id: int
    quantity: int
    drug: DrugOut

    class Config:
        from_attributes = True


class LatestRefillOut(BaseModel):
    quantity: int
    days_supply: int
    sold_date: Optional[date] = None
    completed_date: Optional[date] = None
    next_pickup: Optional[date] = None
    state: Optional[str] = None

    class Config:
        from_attributes = True


class PrescriptionBase(BaseModel):
    drug_id: int
    original_quantity: int
    remaining_quantity: int
    date_received: date

class PrescriptionOut(PrescriptionBase):
    id: int
    patient: PatientOut
    drug: DrugOut
    remaining_quantity: int
    date_received: date

    class Config:
        from_attributes = True
        

class PrescriptionOut2(PrescriptionBase):
    id: int
    patient_id: int
    drug: DrugOut
    remaining_quantity: int
    date_received: date
    latest_refill: Optional[LatestRefillOut] = None

    class Config:
        from_attributes = True


class RefillBase(BaseModel):
    prescription_id: int
    patient_id: int
    drug_id: int
    due_date: date
    quantity: int
    days_supply: int
    priority: str
    state: str
    completed_date: date

class RefillOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    prescriber: Optional[PrescriberOut] = None
    due_date: date
    quantity: int
    days_supply: int
    priority: str
    state: str
    completed_date: Optional[date] = None

    class Config:
        from_attributes = True


class RefillHistBase(BaseModel):
    prescription_id: int
    patient_id: int
    drug_id: int
    quantity: int
    days_supply: int
    completed_date: date
    sold_date: date

class RefillHistOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    quantity: int
    days_supply: int
    completed_date: date
    sold_date: Optional[date] = None

    class Config:
        from_attributes = True


    

class PatientWithRxs(PatientOut):
    prescriptions: List[PrescriptionOut2] = []

    class Config:
        from_attributes = True

class AdvanceRequest(BaseModel):
    action: Optional[str] = None # reserved for future custom transitions
