"""Plugin provider interfaces and registry for the Pharmacy API.

This package decouples the core workflow from concrete drug-catalog and
insurance-adjudication implementations.  The application wires up concrete
providers at startup (see main.py); all business logic then calls the
abstract interfaces and never imports provider-specific modules directly.

Packages:
    base    — Abstract base classes and shared dataclasses
    registry — ProviderRegistry singleton + FastAPI Depends helpers
    local_drug_catalog   — Default: backed by the local Drug/Stock tables
    local_insurance      — Default: backed by the local Formulary tables
"""
