"""
test_unit.py — Pure unit tests for schemas, validators, and helper functions.

No database or HTTP client required — these test Python logic in isolation.
"""
import pytest
from decimal import Decimal
from datetime import date

from pydantic import ValidationError

from app.schemas import (
    FillScriptRequest,
    PrescriptionCreate,
    ManualPrescriptionCreate,
    JSONPrescriptionUpload,
    BillingCalculateRequest,
    PatientCreate,
    _validate_priority,
    _validate_positive_int,
)
from app.models import RxState, Priority
from app.utils import _int, _mask_patient_id, _parse_priority
from fastapi import HTTPException


# ===========================================================================
# _validate_priority (schema helper)
# ===========================================================================

class TestValidatePriority:
    def test_low_accepted(self):
        assert _validate_priority("low") == "low"

    def test_normal_accepted(self):
        assert _validate_priority("normal") == "normal"

    def test_high_accepted(self):
        assert _validate_priority("high") == "high"

    def test_stat_accepted(self):
        assert _validate_priority("stat") == "stat"

    def test_case_insensitive_upper(self):
        assert _validate_priority("LOW") == "low"

    def test_case_insensitive_mixed(self):
        assert _validate_priority("Normal") == "normal"

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError, match="priority must be one of"):
            _validate_priority("urgent")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError):
            _validate_priority("")

    def test_numeric_string_raises(self):
        with pytest.raises(ValueError):
            _validate_priority("1")


# ===========================================================================
# _validate_positive_int (schema helper)
# ===========================================================================

class TestValidatePositiveInt:
    def test_positive_value_passes(self):
        assert _validate_positive_int("quantity", 1) == 1
        assert _validate_positive_int("quantity", 100) == 100

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="must be greater than 0"):
            _validate_positive_int("quantity", 0)

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be greater than 0"):
            _validate_positive_int("quantity", -1)

    def test_large_value_passes(self):
        assert _validate_positive_int("quantity", 999_999) == 999_999


# ===========================================================================
# _parse_priority (main.py helper — raises HTTPException)
# ===========================================================================

class TestParsePriority:
    def test_low_returns_enum(self):
        assert _parse_priority("low") == Priority.low

    def test_normal_returns_enum(self):
        assert _parse_priority("normal") == Priority.normal

    def test_high_returns_enum(self):
        assert _parse_priority("high") == Priority.high

    def test_stat_returns_enum(self):
        assert _parse_priority("stat") == Priority.stat

    def test_invalid_raises_http_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_priority("emergency")
        assert exc_info.value.status_code == 400

    def test_empty_raises_http_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_priority("")
        assert exc_info.value.status_code == 400


# ===========================================================================
# _mask_patient_id helper
# ===========================================================================

class TestMaskPatientId:
    def test_returns_string(self):
        assert isinstance(_mask_patient_id(1), str)

    def test_length_is_12(self):
        assert len(_mask_patient_id(1)) == 12

    def test_same_id_same_token(self):
        assert _mask_patient_id(42) == _mask_patient_id(42)

    def test_different_ids_different_tokens(self):
        assert _mask_patient_id(1) != _mask_patient_id(2)

    def test_does_not_contain_patient_id(self):
        # The raw numeric ID must not appear literally in the output
        assert "99999" not in _mask_patient_id(99999)

    def test_hex_characters_only(self):
        token = _mask_patient_id(7)
        assert all(c in "0123456789abcdef" for c in token)


# ===========================================================================
# _int helper (safe SQLAlchemy Column coercion)
# ===========================================================================

class TestIntHelper:
    def test_int_value(self):
        assert _int(42) == 42

    def test_none_returns_zero(self):
        assert _int(None) == 0

    def test_float_coerces(self):
        assert _int(3.9) == 3

    def test_string_digit_coerces(self):
        assert _int("10") == 10

    def test_zero_returns_zero(self):
        assert _int(0) == 0


# ===========================================================================
# FillScriptRequest schema validation
# ===========================================================================

class TestFillScriptRequest:
    def _valid(self, **overrides):
        base = {"quantity": 30, "days_supply": 30, "priority": "normal"}
        base.update(overrides)
        return FillScriptRequest(**base)

    def test_valid_request_passes(self):
        req = self._valid()
        assert req.quantity == 30
        assert req.days_supply == 30
        assert req.priority == "normal"

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            self._valid(quantity=0)
        assert "quantity" in str(exc_info.value)

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(quantity=-5)

    def test_zero_days_supply_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(days_supply=0)

    def test_negative_days_supply_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(days_supply=-30)

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(priority="urgent")

    def test_priority_case_insensitive(self):
        req = self._valid(priority="HIGH")
        assert req.priority == "high"

    def test_scheduled_defaults_false(self):
        req = self._valid()
        assert req.scheduled is False

    def test_scheduled_true_accepted(self):
        req = self._valid(scheduled=True)
        assert req.scheduled is True

    def test_insurance_id_optional(self):
        req = self._valid(insurance_id=None)
        assert req.insurance_id is None

    def test_insurance_id_set(self):
        req = self._valid(insurance_id=7)
        assert req.insurance_id == 7

    def test_due_date_optional(self):
        req = self._valid(due_date=None)
        assert req.due_date is None

    def test_due_date_set(self):
        req = self._valid(due_date=date(2026, 6, 1))
        assert req.due_date == date(2026, 6, 1)

    def test_large_quantity_accepted_by_schema(self):
        # Schema allows it; business logic in the endpoint blocks overfill
        req = self._valid(quantity=999_999)
        assert req.quantity == 999_999


# ===========================================================================
# PrescriptionCreate schema validation
# ===========================================================================

class TestPrescriptionCreate:
    def _valid(self, **overrides):
        base = {
            "date": date.today(),
            "patient_id": 1,
            "drug_id": 1,
            "brand_required": 0,
            "directions": "Take 1 tablet daily",
            "refill_quantity": 30,
            "total_refills": 3,
            "npi": 1234567890,
        }
        base.update(overrides)
        return PrescriptionCreate(**base)

    def test_valid_request_passes(self):
        p = self._valid()
        assert p.refill_quantity == 30
        assert p.total_refills == 3

    def test_zero_refill_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(refill_quantity=0)

    def test_negative_refill_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(refill_quantity=-10)

    def test_zero_total_refills_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(total_refills=0)

    def test_negative_total_refills_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(total_refills=-1)


# ===========================================================================
# ManualPrescriptionCreate schema validation
# ===========================================================================

class TestManualPrescriptionCreate:
    def _valid(self, **overrides):
        base = {
            "patient_id": 1,
            "drug_id": 1,
            "prescriber_id": 1,
            "quantity": 30,
            "days_supply": 30,
            "total_refills": 3,
            "instructions": "Take daily",
            "priority": "normal",
            "initial_state": "QP",
        }
        base.update(overrides)
        return ManualPrescriptionCreate(**base)

    def test_valid_qp_state(self):
        assert self._valid(initial_state="QP").initial_state == "QP"

    def test_valid_hold_state(self):
        assert self._valid(initial_state="HOLD").initial_state == "HOLD"

    def test_valid_scheduled_state(self):
        assert self._valid(initial_state="SCHEDULED").initial_state == "SCHEDULED"

    def test_invalid_state_qt_rejected(self):
        # QT is NOT an allowed initial_state for manual entry
        with pytest.raises(ValidationError):
            self._valid(initial_state="QT")

    def test_invalid_state_sold_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(initial_state="SOLD")

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(quantity=0)

    def test_zero_days_supply_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(days_supply=0)

    def test_zero_total_refills_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(total_refills=0)

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(priority="rush")


# ===========================================================================
# JSONPrescriptionUpload schema validation
# ===========================================================================

class TestJSONPrescriptionUpload:
    def _valid(self, **overrides):
        base = {
            "date": date.today(),
            "patient": {"first_name": "Jane", "last_name": "Smith", "dob": "1990-03-22"},
            "prescriber": {"npi": 9876543210, "first_name": "Dr", "last_name": "House"},
            "drug": {"name": "Metformin", "manufacturer": "AstraZeneca"},
            "directions": "Take with meals",
            "refill_quantity": 30,
            "total_refills": 12,
        }
        base.update(overrides)
        return JSONPrescriptionUpload(**base)

    def test_valid_upload_passes(self):
        u = self._valid()
        assert u.refill_quantity == 30

    def test_zero_refill_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(refill_quantity=0)

    def test_invalid_priority_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(priority="critical")

    def test_default_priority_is_normal(self):
        assert self._valid().priority == "normal"

    def test_default_brand_required_is_false(self):
        assert self._valid().brand_required is False


# ===========================================================================
# BillingCalculateRequest schema validation
# ===========================================================================

class TestBillingCalculateRequest:
    def _valid(self, **overrides):
        base = {"drug_id": 1, "insurance_id": 1, "quantity": 30, "days_supply": 30}
        base.update(overrides)
        return BillingCalculateRequest(**base)

    def test_valid_request_passes(self):
        req = self._valid()
        assert req.quantity == 30

    def test_zero_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(quantity=0)

    def test_negative_quantity_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(quantity=-1)

    def test_zero_days_supply_rejected(self):
        with pytest.raises(ValidationError):
            self._valid(days_supply=0)


# ===========================================================================
# RxState enum sanity checks
# ===========================================================================

class TestRxStateEnum:
    def test_all_states_defined(self):
        expected = {"QT", "QV1", "QP", "QV2", "READY", "HOLD", "SCHEDULED", "REJECTED", "SOLD", "RTS"}
        actual = {s.value for s in RxState}
        assert expected == actual

    def test_from_string(self):
        assert RxState("QT") == RxState.QT
        assert RxState("SOLD") == RxState.SOLD

    def test_invalid_state_raises(self):
        with pytest.raises(ValueError):
            RxState("INVALID")


# ===========================================================================
# Priority enum sanity checks
# ===========================================================================

class TestPriorityEnum:
    def test_all_priorities_defined(self):
        expected = {"Low", "Normal", "High", "Stat"}
        actual = {p.value for p in Priority}
        assert expected == actual

    def test_priority_values(self):
        assert Priority.low.value == "Low"
        assert Priority.stat.value == "Stat"

    def test_priority_from_name(self):
        assert Priority["low"] == Priority.low
        assert Priority["stat"] == Priority.stat


# ===========================================================================
# PatientCreate schema
# ===========================================================================

class TestPatientCreate:
    def test_valid_patient(self):
        p = PatientCreate(
            first_name="Jane",
            last_name="Doe",
            dob=date(1990, 5, 20),
            address="456 Oak Ave",
        )
        assert p.first_name == "Jane"
        assert p.dob == date(1990, 5, 20)

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            PatientCreate(first_name="Jane", last_name="Doe", dob=date(1990, 1, 1))
        # address is required

    def test_invalid_dob_format_raises(self):
        with pytest.raises(ValidationError):
            PatientCreate(
                first_name="X",
                last_name="Y",
                dob="not-a-date",  # type: ignore
                address="z",
            )
