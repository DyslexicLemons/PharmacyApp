"""ProviderRegistry — singleton DI container for pluggable providers.

Usage
-----
At application startup (main.py lifespan), register concrete implementations:

    from app.providers.registry import ProviderRegistry
    from app.providers.local_drug_catalog import LocalDrugCatalogProvider
    from app.providers.local_insurance import LocalInsuranceGateway

    ProviderRegistry.register_drug_catalog(LocalDrugCatalogProvider())
    ProviderRegistry.register_insurance_gateway(LocalInsuranceGateway())

In routers, inject via FastAPI Depends:

    from app.providers.registry import get_drug_catalog, get_insurance_gateway

    @router.get("/drugs/search")
    async def search_drugs(
        q: str,
        catalog: DrugCatalogProvider = Depends(get_drug_catalog),
    ):
        return await catalog.search(q)

Swapping providers requires only changes to main.py — no router code changes.
"""

from __future__ import annotations

import os
from typing import Optional

from .base import DrugCatalogProvider, InsuranceAdjudicationGateway


class ProviderRegistry:
    """Class-level registry; populated once at startup, read many times per request."""

    _drug_catalog: Optional[DrugCatalogProvider] = None
    _insurance_gateway: Optional[InsuranceAdjudicationGateway] = None

    # ------------------------------------------------------------------
    # Registration (called once at startup)
    # ------------------------------------------------------------------

    @classmethod
    def register_drug_catalog(cls, provider: DrugCatalogProvider) -> None:
        cls._drug_catalog = provider

    @classmethod
    def register_insurance_gateway(cls, gateway: InsuranceAdjudicationGateway) -> None:
        cls._insurance_gateway = gateway

    # ------------------------------------------------------------------
    # Retrieval (called per-request via Depends)
    # ------------------------------------------------------------------

    @classmethod
    def drug_catalog(cls) -> DrugCatalogProvider:
        if cls._drug_catalog is None:
            raise RuntimeError(
                "No DrugCatalogProvider registered. "
                "Call ProviderRegistry.register_drug_catalog() at startup."
            )
        return cls._drug_catalog

    @classmethod
    def insurance_gateway(cls) -> InsuranceAdjudicationGateway:
        if cls._insurance_gateway is None:
            raise RuntimeError(
                "No InsuranceAdjudicationGateway registered. "
                "Call ProviderRegistry.register_insurance_gateway() at startup."
            )
        return cls._insurance_gateway

    # ------------------------------------------------------------------
    # Introspection (useful for /health or admin endpoints)
    # ------------------------------------------------------------------

    @classmethod
    def status(cls) -> dict:
        return {
            "drug_catalog": type(cls._drug_catalog).__name__ if cls._drug_catalog else None,
            "insurance_gateway": type(cls._insurance_gateway).__name__ if cls._insurance_gateway else None,
        }


# ---------------------------------------------------------------------------
# FastAPI Depends helpers
# ---------------------------------------------------------------------------
# These are the only symbols routers should import — keeps them decoupled from
# the concrete provider classes.

def get_drug_catalog() -> DrugCatalogProvider:
    """FastAPI dependency: returns the active DrugCatalogProvider."""
    return ProviderRegistry.drug_catalog()


def get_insurance_gateway() -> InsuranceAdjudicationGateway:
    """FastAPI dependency: returns the active InsuranceAdjudicationGateway."""
    return ProviderRegistry.insurance_gateway()


# ---------------------------------------------------------------------------
# Provider selection from environment variable
# ---------------------------------------------------------------------------
# Set DRUG_CATALOG_PROVIDER=local (default) or a dotted import path to a
# custom class.  Same pattern for INSURANCE_GATEWAY_PROVIDER.
# This is used by the startup helper below; individual provider modules are
# responsible for their own env-based configuration.

PROVIDER_MAP = {
    "local": {
        "drug_catalog": "app.providers.local_drug_catalog.LocalDrugCatalogProvider",
        "insurance_gateway": "app.providers.local_insurance.LocalInsuranceGateway",
    }
}


def _import_class(dotted_path: str):
    """Import a class by its dotted module path, e.g. 'mypackage.module.MyClass'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def register_providers_from_env() -> None:
    """Register providers based on environment variables.

    DRUG_CATALOG_PROVIDER   — 'local' (default) or a dotted import path
    INSURANCE_GATEWAY_PROVIDER — 'local' (default) or a dotted import path

    Called from main.py lifespan so that provider selection requires only
    an env-var change and a container restart.
    """
    backend = os.environ.get("DRUG_CATALOG_PROVIDER", "local")
    ins_backend = os.environ.get("INSURANCE_GATEWAY_PROVIDER", "local")

    drug_path = PROVIDER_MAP.get("local", {})["drug_catalog"] if backend == "local" else backend
    ins_path = PROVIDER_MAP.get("local", {})["insurance_gateway"] if ins_backend == "local" else ins_backend

    DrugCatalogClass = _import_class(drug_path)
    InsuranceClass = _import_class(ins_path)

    ProviderRegistry.register_drug_catalog(DrugCatalogClass())
    ProviderRegistry.register_insurance_gateway(InsuranceClass())
