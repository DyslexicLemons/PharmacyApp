"""
test_providers.py — Unit tests for LocalDrugCatalogProvider and LocalInsuranceGateway.

These tests exercise the provider classes directly (not via HTTP) using a real
PostgreSQL test session, consistent with the project's no-mock-DB policy.
"""
import asyncio
import pytest
from decimal import Decimal

from app.providers.local_drug_catalog import LocalDrugCatalogProvider
from app.providers.local_insurance import LocalInsuranceGateway
from app.providers.registry import ProviderRegistry
from tests.conftest import (
    make_drug, make_patient, make_insurance,
    make_formulary, make_patient_insurance,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run an async provider method synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# LocalDrugCatalogProvider
# ===========================================================================

class TestLocalDrugCatalogProviderSearch:
    def test_search_returns_matching_drug(self, db_session):
        drug = make_drug(db_session, name="Metformin", ndc="00093-1048-01")
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("Metformin"))

        assert len(results) == 1
        assert results[0].name == "Metformin"
        assert results[0].drug_id == drug.id

    def test_search_case_insensitive(self, db_session):
        make_drug(db_session, name="Lisinopril")
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("lisinopril"))

        assert len(results) == 1
        assert results[0].name == "Lisinopril"

    def test_search_partial_name_match(self, db_session):
        make_drug(db_session, name="Atorvastatin Calcium")
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("Atorva"))

        assert len(results) == 1

    def test_search_no_match_returns_empty(self, db_session):
        make_drug(db_session, name="Lisinopril")
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("XYZ_NO_MATCH_99999"))

        assert results == []

    def test_search_respects_limit(self, db_session):
        for i in range(5):
            make_drug(db_session, name=f"Drug{i}", ndc=f"11111-{i:04d}-00")
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("Drug", limit=3))

        assert len(results) <= 3

    def test_search_result_includes_stock_info(self, db_session):
        make_drug(db_session, name="Amlodipine")  # make_drug always creates stock (qty=5000)
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("Amlodipine"))

        assert len(results) == 1
        assert results[0].in_stock is True
        assert results[0].quantity_on_hand == 5000

    def test_search_unit_cost_populated(self, db_session):
        make_drug(db_session, name="Warfarin", cost=Decimal("2.50"))
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        results = run(provider.search("Warfarin"))

        assert results[0].unit_cost == Decimal("2.50")


class TestLocalDrugCatalogProviderPricing:
    def test_get_pricing_returns_cost_for_known_ndc(self, db_session):
        make_drug(db_session, ndc="12345-678-90", cost=Decimal("3.75"))
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        result = run(provider.get_pricing("12345-678-90"))

        assert result.ndc == "12345-678-90"
        assert result.unit_cost == Decimal("3.75")
        assert result.source == "local_db"
        assert result.awp is None  # local DB carries no AWP

    def test_get_pricing_unknown_ndc_returns_zero_cost(self, db_session):
        provider = LocalDrugCatalogProvider(db=db_session)
        result = run(provider.get_pricing("00000-000-00"))

        assert result.unit_cost == Decimal("0")


class TestLocalDrugCatalogProviderAvailability:
    def test_check_availability_true_when_stock_sufficient(self, db_session):
        drug = make_drug(db_session, ndc="12345-678-90")  # stock qty=5000
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        available = run(provider.check_availability("12345-678-90", 30))

        assert available is True

    def test_check_availability_false_when_stock_insufficient(self, db_session):
        from app.models import Stock
        drug = make_drug(db_session, ndc="12345-678-90")
        stock = db_session.query(Stock).filter(Stock.drug_id == drug.id).first()
        stock.quantity = 5  # less than requested quantity
        db_session.commit()

        provider = LocalDrugCatalogProvider(db=db_session)
        available = run(provider.check_availability("12345-678-90", 30))

        assert available is False

    def test_check_availability_false_for_unknown_ndc(self, db_session):
        provider = LocalDrugCatalogProvider(db=db_session)
        available = run(provider.check_availability("00000-000-00", 1))

        assert available is False


class TestLocalDrugCatalogProviderInteractions:
    def test_check_interactions_returns_empty_list(self, db_session):
        """LocalDrugCatalogProvider does not support interactions — always empty."""
        provider = LocalDrugCatalogProvider(db=db_session)
        warnings = run(provider.check_interactions(["12345-678-90", "99999-000-01"]))

        assert warnings == []


# ===========================================================================
# LocalInsuranceGateway
# ===========================================================================

class TestLocalInsuranceGatewayEligibility:
    def test_eligible_when_covered_in_formulary(self, db_session):
        drug = make_drug(db_session, ndc="12345-678-90", cost=Decimal("1.00"))
        patient = make_patient(db_session)
        insurance = make_insurance(db_session)  # bin_number="610493", pcn="ADV"
        make_formulary(db_session, insurance, drug, tier=1, copay_per_30=Decimal("10.00"))
        make_patient_insurance(db_session, patient, insurance)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.verify_eligibility(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
        ))

        assert result.is_eligible is True
        assert result.plan_name == "Blue Shield"
        assert result.coverage_tier == 1
        assert result.copay_amount is not None

    def test_not_eligible_when_drug_not_covered(self, db_session):
        drug = make_drug(db_session, ndc="12345-678-90")
        patient = make_patient(db_session)
        insurance = make_insurance(db_session)
        make_formulary(db_session, insurance, drug, not_covered=True)
        make_patient_insurance(db_session, patient, insurance)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.verify_eligibility(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
        ))

        assert result.is_eligible is False
        assert result.rejection_code == "NOT_COVERED"

    def test_not_eligible_when_plan_not_found(self, db_session):
        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.verify_eligibility(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="000000",  # unknown BIN
            pcn="UNKNOWN",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
        ))

        assert result.is_eligible is False
        assert result.rejection_code == "PLAN_NOT_FOUND"

    def test_not_eligible_when_drug_not_in_catalog(self, db_session):
        insurance = make_insurance(db_session)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.verify_eligibility(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="00000-000-00",  # NDC not in catalog
            quantity=30,
            days_supply=30,
        ))

        assert result.is_eligible is False
        assert result.rejection_code == "DRUG_NOT_FOUND"


class TestLocalInsuranceGatewaySubmitClaim:
    def test_submit_claim_approved_returns_correct_amounts(self, db_session):
        """
        drug.cost=$1.00, qty=30 → cash_price=$30.00
        copay_per_30=$10.00, days_supply=30 → copay=$10.00
        insurance_paid = $30.00 - $10.00 = $20.00
        """
        drug = make_drug(db_session, ndc="12345-678-90", cost=Decimal("1.00"))
        patient = make_patient(db_session)
        insurance = make_insurance(db_session)
        make_formulary(db_session, insurance, drug, copay_per_30=Decimal("10.00"))
        make_patient_insurance(db_session, patient, insurance)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.submit_claim(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
            prescriber_npi="1234567890",
            unit_cost=Decimal("1.00"),
        ))

        assert result.approved is True
        assert result.amount_due == Decimal("10.00")
        assert result.amount_paid == Decimal("20.00")
        assert result.claim_id is not None

    def test_submit_claim_rejected_when_not_covered(self, db_session):
        drug = make_drug(db_session, ndc="12345-678-90", cost=Decimal("1.00"))
        patient = make_patient(db_session)
        insurance = make_insurance(db_session)
        make_formulary(db_session, insurance, drug, not_covered=True)
        make_patient_insurance(db_session, patient, insurance)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.submit_claim(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
            prescriber_npi="1234567890",
            unit_cost=Decimal("1.00"),
        ))

        assert result.approved is False
        assert result.rejection_code == "NOT_COVERED"

    def test_submit_claim_copay_capped_at_cash_price(self, db_session):
        """
        drug.cost=$0.10, qty=30 → cash_price=$3.00
        copay_per_30=$50.00 → raw_copay=$50.00 → capped at $3.00
        """
        drug = make_drug(db_session, ndc="12345-678-90", cost=Decimal("0.10"))
        patient = make_patient(db_session)
        insurance = make_insurance(db_session)
        make_formulary(db_session, insurance, drug, copay_per_30=Decimal("50.00"))
        make_patient_insurance(db_session, patient, insurance)
        db_session.commit()

        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.submit_claim(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="610493",
            pcn="ADV",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
            prescriber_npi="1234567890",
            unit_cost=Decimal("0.10"),
        ))

        assert result.approved is True
        assert result.amount_due <= Decimal("3.00"), "Copay must not exceed cash price"
        assert result.amount_paid >= Decimal("0"), "Insurance paid must be non-negative"

    def test_submit_claim_plan_not_found(self, db_session):
        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.submit_claim(
            member_id="MBR123",
            group_id="GRP001",
            bin_number="000000",
            pcn="UNKNOWN",
            ndc="12345-678-90",
            quantity=30,
            days_supply=30,
            prescriber_npi="1234567890",
            unit_cost=Decimal("1.00"),
        ))

        assert result.approved is False
        assert result.rejection_code == "PLAN_NOT_FOUND"


class TestLocalInsuranceGatewayReverse:
    def test_reverse_claim_always_succeeds(self, db_session):
        """Local gateway has no external network to reverse — always returns True."""
        gateway = LocalInsuranceGateway(db=db_session)
        result = run(gateway.reverse_claim("local-MBR123-12345-678-90-30"))
        assert result is True


# ===========================================================================
# ProviderRegistry
# ===========================================================================

class TestProviderRegistry:
    def test_status_returns_provider_names(self):
        status = ProviderRegistry.status()
        # After startup registration these should be set (via register_providers_from_env in lifespan)
        assert "drug_catalog" in status
        assert "insurance_gateway" in status

    def test_registry_raises_if_not_registered(self):
        """Save and restore so we don't permanently break other tests."""
        original_drug = ProviderRegistry._drug_catalog
        ProviderRegistry._drug_catalog = None
        try:
            with pytest.raises(RuntimeError, match="No DrugCatalogProvider"):
                ProviderRegistry.drug_catalog()
        finally:
            ProviderRegistry._drug_catalog = original_drug
