"""Abstract interfaces for pluggable drug-catalog and insurance providers.

The core application only depends on these classes.  Concrete
implementations live in separate modules (local_drug_catalog.py,
local_insurance.py, or any third-party package) and are registered at
startup via ProviderRegistry.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# ---------------------------------------------------------------------------
# Drug Catalog
# ---------------------------------------------------------------------------

@dataclass
class DrugSearchResult:
    ndc: str
    name: str
    form: str                          # "Tablet", "Capsule", "Liquid", etc.
    strength: str
    manufacturer: str
    unit_cost: Decimal
    in_stock: bool
    drug_id: Optional[int] = None      # local DB id, if applicable
    quantity_on_hand: Optional[int] = None


@dataclass
class DrugPricingResult:
    ndc: str
    unit_cost: Decimal
    awp: Optional[Decimal]             # Average Wholesale Price
    source: str                        # "local_db", "fdb", "surescripts", …


@dataclass
class InteractionWarning:
    severity: str                      # "major" | "moderate" | "minor"
    description: str
    ndcs_involved: list[str] = field(default_factory=list)


class DrugCatalogProvider(ABC):
    """Supply drug search, pricing, and availability to the core app.

    Implement this class and register an instance with ProviderRegistry to
    swap in a third-party data source (FDB, Surescripts, etc.) without
    touching any router code.
    """

    @abstractmethod
    async def search(self, query: str, limit: int = 20) -> list[DrugSearchResult]:
        """Full-text search by name, NDC, or generic equivalent."""
        ...

    @abstractmethod
    async def get_pricing(self, ndc: str) -> DrugPricingResult:
        """Return current pricing for a specific NDC."""
        ...

    @abstractmethod
    async def check_availability(self, ndc: str, quantity: int) -> bool:
        """True if the requested quantity can be dispensed right now."""
        ...

    @abstractmethod
    async def check_interactions(self, ndcs: list[str]) -> list[InteractionWarning]:
        """Return drug–drug interaction warnings for a set of NDCs.

        Return an empty list if interactions are not supported by this provider.
        """
        ...


# ---------------------------------------------------------------------------
# Insurance / Adjudication
# ---------------------------------------------------------------------------

@dataclass
class EligibilityResult:
    is_eligible: bool
    member_id: str
    group_id: str
    plan_name: str
    copay_amount: Optional[Decimal] = None
    deductible_remaining: Optional[Decimal] = None
    coverage_tier: Optional[int] = None        # 1=preferred generic … 4=specialty
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None


@dataclass
class ClaimSubmissionResult:
    approved: bool
    amount_due: Decimal                         # patient responsibility
    amount_paid: Decimal                        # amount paid by insurance
    claim_id: Optional[str] = None
    rejection_code: Optional[str] = None
    rejection_reason: Optional[str] = None
    requires_prior_auth: bool = False


class InsuranceAdjudicationGateway(ABC):
    """Verify coverage and adjudicate claims on behalf of the refill workflow.

    The advance_refill endpoint calls verify_eligibility before allowing a
    QV2→READY transition and submit_claim when recording billing details.
    The RTS workflow calls reverse_claim when a READY fill is returned.

    Implement and register a concrete class to connect to a real-time
    adjudication network (e.g. ClaimLogic, RelayHealth, Change Healthcare).
    """

    @abstractmethod
    async def verify_eligibility(
        self,
        member_id: str,
        group_id: str,
        bin_number: str,
        pcn: str,
        ndc: str,
        quantity: int,
        days_supply: int,
    ) -> EligibilityResult:
        """Real-time eligibility check (NCPDP D.0 equivalent)."""
        ...

    @abstractmethod
    async def submit_claim(
        self,
        member_id: str,
        group_id: str,
        bin_number: str,
        pcn: str,
        ndc: str,
        quantity: int,
        days_supply: int,
        prescriber_npi: str,
        unit_cost: Decimal,
    ) -> ClaimSubmissionResult:
        """Submit an adjudication claim and return patient responsibility."""
        ...

    @abstractmethod
    async def reverse_claim(self, claim_id: str) -> bool:
        """Reverse a previously adjudicated claim (used by RTS workflow)."""
        ...
