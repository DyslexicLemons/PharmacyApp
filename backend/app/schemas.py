from decimal import Decimal
from pydantic import BaseModel, field_validator
from datetime import date
from typing import Generic, List, Optional, TypeVar

# ---- Generic paginated response ----

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    limit: int
    offset: int


# ---- Auth schemas (moved from main.py) ----

class LoginRequest(BaseModel):
    username: str
    password: str


class CodeLoginRequest(BaseModel):
    code: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


class LoginResponse(BaseModel):
    success: bool
    username: str
    is_admin: bool
    quick_code: str
    access_token: str
    token_type: str = "bearer"


# ---- Audit log output ----

class AuditLogOut(BaseModel):
    id: int
    timestamp: str
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    prescription_id: Optional[int] = None
    details: Optional[str] = None
    performed_by: Optional[str] = None

    class Config:
        from_attributes = True


# Valid priority strings accepted by the API
VALID_PRIORITIES = {"low", "normal", "high", "stat"}


def _validate_priority(v: str) -> str:
    if v.lower() not in VALID_PRIORITIES:
        raise ValueError(f"priority must be one of {sorted(VALID_PRIORITIES)}")
    return v.lower()


def _validate_positive_int(name: str, v: int) -> int:
    if v <= 0:
        raise ValueError(f"{name} must be greater than 0")
    return v


class PatientBase(BaseModel):
    first_name: str
    last_name: str
    dob: date
    address: str
    city: Optional[str] = None
    state: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def capitalize_name(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("address", mode="before")
    @classmethod
    def capitalize_address(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("city", mode="before")
    @classmethod
    def capitalize_city(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().title() if v else v

    @field_validator("state", mode="before")
    @classmethod
    def uppercase_state(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().upper() if v else v


class PatientCreate(PatientBase):
    pass

class PatientOut(PatientBase):
    id: int
    first_name: str
    last_name: str
    class Config:
        from_attributes = True


class PrescriberBase(BaseModel):
    npi: int
    first_name: str
    last_name: str
    address: str
    phone_number: str
    specialty: Optional[str] = None

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def capitalize_name(cls, v: str) -> str:
        return v.strip().title()

    @field_validator("address", mode="before")
    @classmethod
    def capitalize_address(cls, v: str) -> str:
        return v.strip().title()

class PrescriberOut(PrescriberBase):
    id: int
    npi: int
    first_name: str
    last_name: str
    address: str
    phone_number: str
    specialty: Optional[str] = None
    class Config:
        from_attributes = True

class DrugBase(BaseModel):
    drug_name: str
    ndc: Optional[str] = None
    manufacturer: str
    cost: Decimal
    niosh: bool = False
    drug_class: int
    description: Optional[str] = None

class DrugOut(BaseModel):
    id: int
    drug_name: str
    ndc: Optional[str] = None
    manufacturer: str
    cost: Decimal
    niosh: bool
    drug_class: int
    description: Optional[str] = None

    class Config:
        from_attributes = True


class StockBase(BaseModel):
    drug_id: int
    quantity: int

class StockOut(BaseModel):
    drug_id: int
    quantity: int
    package_size: int
    drug: DrugOut

    class Config:
        from_attributes = True


# ---- Insurance / Billing ----

class InsuranceCompanyOut(BaseModel):
    id: int
    plan_id: str
    plan_name: str
    bin_number: Optional[str] = None
    pcn: Optional[str] = None
    phone_number: Optional[str] = None

    class Config:
        from_attributes = True


class FormularyOut(BaseModel):
    id: int
    drug_id: int
    drug: DrugOut
    tier: int
    copay_per_30: Decimal
    not_covered: bool

    class Config:
        from_attributes = True


class PatientInsuranceOut(BaseModel):
    id: int
    patient_id: int
    insurance_company: InsuranceCompanyOut
    member_id: str
    group_number: Optional[str] = None
    is_primary: bool
    is_active: bool

    class Config:
        from_attributes = True


class PatientInsuranceCreate(BaseModel):
    insurance_company_id: int
    member_id: str
    group_number: Optional[str] = None
    is_primary: bool = True


class BillingCalculateRequest(BaseModel):
    drug_id: int
    insurance_id: int  # PatientInsurance.id
    quantity: int
    days_supply: int

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("quantity", v)

    @field_validator("days_supply")
    @classmethod
    def days_supply_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("days_supply", v)


class BillingCalculateResponse(BaseModel):
    cash_price: Decimal
    insurance_price: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    tier: Optional[int] = None
    not_covered: bool = False
    plan_name: Optional[str] = None


# ---- Refills / Prescriptions ----

class LatestRefillOut(BaseModel):
    quantity: int
    days_supply: int
    sold_date: Optional[date] = None
    total_cost: Decimal
    completed_date: Optional[date] = None
    next_pickup: Optional[date] = None
    state: Optional[str] = None
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None

    class Config:
        from_attributes = True


class RefillHistSimpleOut(BaseModel):
    id: int
    quantity: int
    days_supply: int
    completed_date: Optional[date] = None
    sold_date: Optional[date] = None
    total_cost: Decimal
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance: Optional["PatientInsuranceOut"] = None

    class Config:
        from_attributes = True


class PrescriptionBase(BaseModel):
    drug_id: int
    brand_required: bool
    original_quantity: int
    remaining_quantity: int
    date_received: date
    instructions: str

class PrescriptionOut(PrescriptionBase):
    id: int
    patient: PatientOut
    drug: DrugOut
    prescriber: Optional[PrescriberOut] = None
    brand_required: bool
    remaining_quantity: int
    date_received: date
    expiration_date: Optional[date] = None
    picture: Optional[str] = None
    picture_path: Optional[str] = None
    picture_url: Optional[str] = None

    class Config:
        from_attributes = True


class PrescriptionOut2(PrescriptionBase):
    id: int
    brand_required: bool
    patient_id: int
    prescriber_id: int
    drug: DrugOut
    remaining_quantity: int
    date_received: date
    expiration_date: Optional[date] = None
    picture: Optional[str] = None
    picture_path: Optional[str] = None
    picture_url: Optional[str] = None
    latest_refill: Optional[LatestRefillOut] = None
    refill_history: List[RefillHistSimpleOut] = []

    class Config:
        from_attributes = True


class PrescriptionUpdate(BaseModel):
    expiration_date: Optional[date] = None
    instructions: Optional[str] = None


class PrescriptionPictureUpdate(BaseModel):
    picture: str  # base64 data URL, e.g. "data:image/jpeg;base64,..."


class PrescriptionDetailOut(PrescriptionOut2):
    patient: PatientOut

    class Config:
        from_attributes = True


class PrescriptionCreate(BaseModel):
    date: date
    patient_id: int
    drug_id: int
    brand_required: int
    directions: str  # mapped to Prescription.instructions in the endpoint
    refill_quantity: int
    total_refills: int
    npi: int

    @field_validator("refill_quantity")
    @classmethod
    def refill_quantity_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("refill_quantity", v)

    @field_validator("total_refills")
    @classmethod
    def total_refills_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("total_refills", v)


class RefillBase(BaseModel):
    prescription_id: int
    patient_id: int
    drug_id: int
    due_date: date
    quantity: int
    days_supply: int
    total_cost: Decimal
    priority: str
    state: str
    completed_date: date

class RefillOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    due_date: date
    quantity: int
    days_supply: int
    total_cost: Decimal
    priority: str
    state: str
    completed_date: Optional[date] = None
    bin_number: Optional[int] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejection_date: Optional[date] = None
    source: str = "manual"
    insurance_id: Optional[int] = None
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance: Optional[PatientInsuranceOut] = None

    class Config:
        from_attributes = True


class RefillHistBase(BaseModel):
    prescription_id: int
    patient_id: int
    drug_id: int
    quantity: int
    days_supply: int
    total_cost: Decimal
    completed_date: date
    sold_date: date

class RefillHistOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    quantity: int
    days_supply: int
    total_cost: Decimal
    completed_date: date
    sold_date: Optional[date] = None
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance: Optional[PatientInsuranceOut] = None

    class Config:
        from_attributes = True




class PatientWithRxs(PatientOut):
    prescriptions: List[PrescriptionOut2] = []
    insurances: List[PatientInsuranceOut] = []

    class Config:
        from_attributes = True

class AdvanceRequest(BaseModel):
    action: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejected_by: Optional[str] = None
    schedule_next_fill: bool = False


class JSONPrescriptionUpload(BaseModel):
    """Schema for external JSON prescription uploads that go to QT queue"""
    date: date
    patient: dict  # {first_name, last_name, dob}
    prescriber: dict  # {npi, first_name, last_name}
    drug: dict  # {name, manufacturer}
    directions: str
    refill_quantity: int
    total_refills: int
    brand_required: bool = False
    priority: str = "normal"

    @field_validator("refill_quantity")
    @classmethod
    def refill_quantity_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("refill_quantity", v)

    @field_validator("total_refills")
    @classmethod
    def total_refills_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("total_refills", v)

    @field_validator("priority")
    @classmethod
    def priority_must_be_valid(cls, v: str) -> str:
        return _validate_priority(v)


class ManualPrescriptionCreate(BaseModel):
    """Schema for manual prescription entry that goes to QP, HOLD, or SCHEDULED"""
    patient_id: int
    drug_id: int
    prescriber_id: int
    quantity: int
    days_supply: int
    total_refills: int
    brand_required: bool = False
    priority: str = "normal"
    initial_state: str = "QP"  # "QP", "HOLD", or "SCHEDULED"
    date_received: Optional[date] = None  # defaults to today if not provided
    due_date: Optional[date] = None
    expiration_date: Optional[date] = None
    instructions: str
    picture: Optional[str] = None

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("quantity", v)

    @field_validator("days_supply")
    @classmethod
    def days_supply_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("days_supply", v)

    @field_validator("total_refills")
    @classmethod
    def total_refills_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("total_refills", v)

    @field_validator("priority")
    @classmethod
    def priority_must_be_valid(cls, v: str) -> str:
        return _validate_priority(v)

    @field_validator("initial_state")
    @classmethod
    def initial_state_must_be_valid(cls, v: str) -> str:
        allowed = {"QP", "HOLD", "SCHEDULED"}
        if v not in allowed:
            raise ValueError(f"initial_state must be one of {sorted(allowed)}")
        return v


class ConflictCheckResponse(BaseModel):
    """Response for duplicate/conflict checking"""
    has_conflict: bool
    active_refills: List[dict] = []
    recent_fills: List[dict] = []
    message: Optional[str] = None


class RefillEditRequest(BaseModel):
    """Schema for editing a refill in QT, QP, or HOLD state."""
    quantity: Optional[int] = None
    days_supply: Optional[int] = None
    priority: Optional[str] = None
    due_date: Optional[date] = None
    instructions: Optional[str] = None
    brand_required: Optional[bool] = None

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            return _validate_positive_int("quantity", v)
        return v

    @field_validator("days_supply")
    @classmethod
    def days_supply_must_be_positive(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            return _validate_positive_int("days_supply", v)
        return v

    @field_validator("priority")
    @classmethod
    def priority_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            return _validate_priority(v)
        return v


class FillScriptRequest(BaseModel):
    """Schema for filling an existing prescription"""
    quantity: int
    days_supply: int
    priority: str = "normal"
    scheduled: bool = False  # True → SCHEDULED state; False → auto-determine (QT/QV1/QP)
    due_date: Optional[date] = None
    insurance_id: Optional[int] = None  # PatientInsurance.id for billing

    @field_validator("quantity")
    @classmethod
    def quantity_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("quantity", v)

    @field_validator("days_supply")
    @classmethod
    def days_supply_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("days_supply", v)

    @field_validator("priority")
    @classmethod
    def priority_must_be_valid(cls, v: str) -> str:
        return _validate_priority(v)
