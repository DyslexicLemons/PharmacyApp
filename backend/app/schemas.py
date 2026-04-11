from decimal import Decimal
from pydantic import BaseModel, computed_field, field_validator, Field
from datetime import date, datetime, timezone
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
    role: str = "technician"  # admin | pharmacist | technician


class LoginResponse(BaseModel):
    success: bool
    username: str
    is_admin: bool
    role: str
    quick_code: str | None = None
    access_token: str
    token_type: str = "bearer"


# ---- System config ----

class SystemConfigOut(BaseModel):
    bin_count: int
    simulation_enabled: bool = False
    sim_arrival_rate: int = 2
    sim_reject_rate: int = 10

    class Config:
        from_attributes = True


class SystemConfigUpdate(BaseModel):
    bin_count: Optional[int] = Field(None, ge=60, le=300)
    simulation_enabled: Optional[bool] = None
    sim_arrival_rate: Optional[int] = Field(None, ge=1, le=10)
    sim_reject_rate: Optional[int] = Field(None, ge=0, le=50)


# ---- Simulation workers ----

class SimWorkerRefillContext(BaseModel):
    """Minimal context about the refill a worker is currently processing."""
    id: int
    prescription_id: int
    drug_name: str
    patient_name: str

    class Config:
        from_attributes = True


class SimWorkerOut(BaseModel):
    id: int
    name: str
    role: str
    is_active: bool
    speed: int
    current_station: Optional[str] = None
    busy_until: Optional[datetime] = None
    task_started_at: Optional[datetime] = None
    current_refill_id: Optional[int] = None
    current_refill: Optional[SimWorkerRefillContext] = None
    # Server-computed progress fields — eliminates client/server clock skew
    progress_pct: Optional[float] = None   # 0.0–100.0, or None if not busy
    secs_remaining: Optional[float] = None  # seconds left, or None if not busy

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_with_refill(cls, worker: object) -> "SimWorkerOut":
        """Build from ORM, resolving the nested refill context fields."""
        import typing
        refill = getattr(worker, "current_refill", None)
        ctx: typing.Optional[SimWorkerRefillContext] = None
        if refill is not None:
            drug = getattr(refill, "drug", None)
            patient = getattr(refill, "patient", None)
            drug_name = getattr(drug, "drug_name", "Unknown") if drug else "Unknown"
            first = getattr(patient, "first_name", "") if patient else ""
            last = getattr(patient, "last_name", "") if patient else ""
            patient_name = f"{first} {last}".strip() or "Unknown"
            ctx = SimWorkerRefillContext(
                id=refill.id,
                prescription_id=refill.prescription_id,
                drug_name=drug_name,
                patient_name=patient_name,
            )

        busy_until = getattr(worker, "busy_until", None)
        task_started_at = getattr(worker, "task_started_at", None)
        now = datetime.now(timezone.utc)

        progress_pct: Optional[float] = None
        secs_remaining: Optional[float] = None
        if busy_until is not None:
            secs_remaining = max(0.0, (busy_until - now).total_seconds())
            if task_started_at is not None:
                total = (busy_until - task_started_at).total_seconds()
                elapsed = (now - task_started_at).total_seconds()
                progress_pct = min(100.0, max(0.0, (elapsed / total * 100) if total > 0 else 100.0))

        return cls.model_validate({
            "id": worker.id,
            "name": worker.name,
            "role": worker.role,
            "is_active": worker.is_active,
            "speed": worker.speed,
            "current_station": getattr(worker, "current_station", None),
            "busy_until": busy_until,
            "task_started_at": task_started_at,
            "current_refill_id": getattr(worker, "current_refill_id", None),
            "current_refill": ctx,
            "progress_pct": progress_pct,
            "secs_remaining": secs_remaining,
        })


class SimWorkerCreate(BaseModel):
    name: str
    role: str  # "technician" or "pharmacist"
    speed: int = Field(5, ge=1, le=10)
    is_active: bool = True
    current_station: Optional[str] = None  # triage | fill | verify_1 | verify_2 | window


class SimWorkerUpdate(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    speed: Optional[int] = Field(None, ge=1, le=10)
    current_station: Optional[str] = None  # triage | fill | verify_1 | verify_2 | window


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


class PatientSearchResult(BaseModel):
    """Redacted patient record returned by list/search endpoints.

    DOB and address are omitted intentionally — full demographics are only
    available via GET /patients/{pid} (individual lookup with audit logging).
    """
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
    drug_form: Optional[str] = None

class DrugOut(BaseModel):
    id: int
    drug_name: str
    ndc: Optional[str] = None
    manufacturer: str
    cost: Decimal
    niosh: bool
    drug_class: int
    description: Optional[str] = None
    drug_form: Optional[str] = None

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
    rts_count: int = 0
    rts_quantity: int = 0

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
    id: Optional[int] = None
    quantity: int
    days_supply: int
    sold_date: Optional[datetime] = None
    total_cost: Decimal
    completed_date: Optional[datetime] = None
    next_pickup: Optional[date] = None
    state: Optional[str] = None
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    due_date: Optional[datetime] = None
    priority: Optional[str] = None
    insurance: Optional["PatientInsuranceOut"] = None

    class Config:
        from_attributes = True


class RefillHistSimpleOut(BaseModel):
    id: int
    quantity: int
    days_supply: int
    completed_date: Optional[datetime] = None
    sold_date: Optional[datetime] = None
    total_cost: Decimal
    copay_amount: Optional[Decimal] = None
    insurance_paid: Optional[Decimal] = None
    insurance: Optional["PatientInsuranceOut"] = None

    class Config:
        from_attributes = True


class PrescriptionBase(BaseModel):
    drug_id: int
    daw_code: int = 0
    original_quantity: int
    remaining_quantity: int
    date_received: date
    instructions: str

class PrescriptionOut(PrescriptionBase):
    id: int
    patient: PatientOut
    drug: DrugOut
    prescriber: Optional[PrescriberOut] = None
    daw_code: int
    remaining_quantity: int
    date_received: date
    expiration_date: Optional[date] = None
    picture_path: Optional[str] = None
    picture_url: Optional[str] = None

    class Config:
        from_attributes = True


class PrescriptionOut2(PrescriptionBase):
    id: int
    daw_code: int
    patient_id: int
    prescriber_id: int
    drug: DrugOut
    remaining_quantity: int
    date_received: date
    expiration_date: Optional[date] = None
    picture_path: Optional[str] = None
    picture_url: Optional[str] = None
    latest_refill: Optional[LatestRefillOut] = None
    refill_history: List[RefillHistSimpleOut] = []
    is_inactive: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_expired(self) -> bool:
        """True when the expiration date has passed and the Rx was not manually inactivated."""
        if self.is_inactive:
            return False
        return self.expiration_date is not None and self.expiration_date < date.today()

    class Config:
        from_attributes = True


class InactivateRequest(BaseModel):
    username: str
    password: str


class PrescriptionUpdate(BaseModel):
    expiration_date: Optional[date] = None
    instructions: Optional[str] = None


class PrescriptionDetailOut(PrescriptionOut2):
    patient: PatientOut

    class Config:
        from_attributes = True


class PrescriptionCreate(BaseModel):
    date: date
    patient_id: int
    drug_id: int
    daw_code: int = 0
    directions: str  # mapped to Prescription.instructions in the endpoint
    refill_quantity: int
    total_refills: int
    npi: int
    brand_required: bool = False

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
    due_date: Optional[datetime] = None
    quantity: int
    days_supply: int
    total_cost: Decimal
    priority: str
    state: str
    completed_date: Optional[datetime] = None

class RefillOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    due_date: Optional[datetime] = None
    quantity: int
    days_supply: int
    total_cost: Decimal
    priority: str
    state: str
    completed_date: Optional[datetime] = None
    bin_number: Optional[int] = None
    rejected_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    rejection_date: Optional[date] = None
    triage_reason: Optional[str] = None
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
    completed_date: datetime
    sold_date: datetime

class RefillHistOut(BaseModel):
    id: int
    prescription: PrescriptionOut
    patient: PatientOut
    drug: DrugOut
    quantity: int
    days_supply: int
    total_cost: Decimal
    completed_date: datetime
    sold_date: Optional[datetime] = None
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
    rejection_reason: Optional[str] = Field(default=None, max_length=500)
    rejected_by: Optional[str] = Field(default=None, max_length=200)
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
    daw_code: int = 0
    priority: str = "normal"
    brand_required: bool = False

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
    daw_code: int = 0
    priority: str = "normal"
    initial_state: str = "QV1"  # "QV1", "HOLD", or "SCHEDULED"
    date_received: Optional[date] = None  # defaults to today if not provided
    due_date: Optional[datetime] = None
    expiration_date: Optional[date] = None
    instructions: str

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
        allowed = {"QV1", "HOLD", "SCHEDULED"}
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
    due_date: Optional[datetime] = None
    instructions: Optional[str] = None
    daw_code: Optional[int] = None

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


class ShipmentItemIn(BaseModel):
    drug_id: int
    bottles_received: int
    units_per_bottle: int = 100

    @field_validator("bottles_received")
    @classmethod
    def bottles_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("bottles_received", v)

    @field_validator("units_per_bottle")
    @classmethod
    def units_must_be_positive(cls, v: int) -> int:
        return _validate_positive_int("units_per_bottle", v)


class ShipmentCreate(BaseModel):
    items: List["ShipmentItemIn"]
    username: str
    password: str


class ShipmentItemOut(BaseModel):
    id: int
    drug_id: int
    drug: DrugOut
    bottles_received: int
    units_per_bottle: int

    class Config:
        from_attributes = True


class ShipmentOut(BaseModel):
    id: int
    performed_at: datetime
    performed_by: str
    items: List[ShipmentItemOut] = []

    class Config:
        from_attributes = True


class QueueStateCounts(BaseModel):
    QT: int = 0
    QV1: int = 0
    QP: int = 0
    QV2: int = 0
    READY: int = 0
    HOLD: int = 0
    SCHEDULED: int = 0
    REJECTED: int = 0


class QueuePriorityBucket(BaseModel):
    pastdue: int = 0
    stat: int = 0
    high: int = 0
    normal: int = 0


class QueueSummaryOut(BaseModel):
    generated_at: str
    refills_by_state: QueueStateCounts
    priority_breakdown: dict[str, QueuePriorityBucket] = {}  # keyed by state (QT, QV1, QP, QV2)
    total_active: int        # QT + QV1 + QP + QV2 + READY + HOLD + SCHEDULED
    overdue_scheduled: int   # SCHEDULED with due_date < today
    expiring_soon_30d: int   # active prescriptions expiring within 30 days


class FillScriptRequest(BaseModel):
    """Schema for filling an existing prescription"""
    quantity: int
    days_supply: int
    priority: str = "normal"
    scheduled: bool = False  # True → SCHEDULED state; False → auto-determine (QT/QV1/QP)
    due_date: Optional[datetime] = None
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


# ---- Return to Stock ----

class RTSRequest(BaseModel):
    refill_id: int


class RTSLookupOut(BaseModel):
    refill_id: int
    drug_name: str
    ndc: Optional[str] = None
    quantity: int
    patient_name: str
    bin_number: Optional[int] = None
    completed_date: Optional[datetime] = None


class ReturnToStockOut(BaseModel):
    id: int
    refill_id: int
    drug_id: int
    drug: DrugOut
    quantity: int
    returned_at: datetime
    returned_by: str

    class Config:
        from_attributes = True
