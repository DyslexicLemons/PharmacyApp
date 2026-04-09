"""
test_drug_search.py — Integration tests for the provider-backed drug endpoints.

  GET /drugs/search?q=
  GET /drugs/interactions?ndcs=

These endpoints delegate to the active DrugCatalogProvider injected via
dependency override in conftest.  All tests run against a real PostgreSQL
test DB — no mocks.
"""
import pytest
from decimal import Decimal

from tests.conftest import make_drug


# ===========================================================================
# GET /drugs/search
# ===========================================================================

class TestDrugSearch:
    def test_search_returns_matching_drug(self, client, db_session):
        drug = make_drug(db_session, name="Metformin HCl", ndc="00093-1048-01",
                         cost=Decimal("0.75"))
        db_session.commit()

        resp = client.get("/drugs/search?q=Metformin")

        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["name"] == "Metformin HCl"
        assert results[0]["drug_id"] == drug.id
        assert results[0]["ndc"] == "00093-1048-01"

    def test_search_returns_in_stock_true_when_stock_exists(self, client, db_session):
        make_drug(db_session, name="Amlodipine")  # make_drug always seeds stock qty=5000
        db_session.commit()

        resp = client.get("/drugs/search?q=Amlodipine")

        assert resp.status_code == 200
        assert resp.json()[0]["in_stock"] is True
        assert resp.json()[0]["quantity_on_hand"] == 5000

    def test_search_returns_unit_cost_as_string(self, client, db_session):
        make_drug(db_session, name="Warfarin", cost=Decimal("2.50"))
        db_session.commit()

        resp = client.get("/drugs/search?q=Warfarin")

        assert resp.status_code == 200
        assert resp.json()[0]["unit_cost"] == "2.50"

    def test_search_empty_results_for_unknown_drug(self, client, db_session):
        make_drug(db_session, name="Lisinopril")
        db_session.commit()

        resp = client.get("/drugs/search?q=XYZ_DOES_NOT_EXIST_99999")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_is_case_insensitive(self, client, db_session):
        make_drug(db_session, name="Atorvastatin")
        db_session.commit()

        resp = client.get("/drugs/search?q=atorvastatin")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_search_partial_match(self, client, db_session):
        make_drug(db_session, name="Hydrochlorothiazide")
        db_session.commit()

        resp = client.get("/drugs/search?q=Hydrochlo")

        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_search_limit_respected(self, client, db_session):
        for i in range(6):
            make_drug(db_session, name=f"TestDrug{i:03d}", ndc=f"22222-{i:04d}-00")
        db_session.commit()

        resp = client.get("/drugs/search?q=TestDrug&limit=4")

        assert resp.status_code == 200
        assert len(resp.json()) <= 4

    def test_search_missing_q_returns_422(self, client):
        resp = client.get("/drugs/search")
        assert resp.status_code == 422

    def test_search_empty_q_returns_422(self, client):
        resp = client.get("/drugs/search?q=")
        assert resp.status_code == 422

    def test_search_multiple_results(self, client, db_session):
        make_drug(db_session, name="Lisinopril 5mg",  ndc="00093-1001-01")
        make_drug(db_session, name="Lisinopril 10mg", ndc="00093-1002-01")
        make_drug(db_session, name="Lisinopril 20mg", ndc="00093-1003-01")
        db_session.commit()

        resp = client.get("/drugs/search?q=Lisinopril")

        assert resp.status_code == 200
        assert len(resp.json()) == 3


# ===========================================================================
# GET /drugs/interactions
# ===========================================================================

class TestDrugInteractions:
    def test_interactions_returns_empty_list_for_local_provider(self, client, db_session):
        """LocalDrugCatalogProvider does not support interaction data — always []."""
        make_drug(db_session, ndc="12345-678-90")
        make_drug(db_session, ndc="99999-000-01", name="OtherDrug")
        db_session.commit()

        resp = client.get("/drugs/interactions?ndcs=12345-678-90,99999-000-01")

        assert resp.status_code == 200
        assert resp.json() == []

    def test_interactions_missing_ndcs_returns_422(self, client):
        resp = client.get("/drugs/interactions")
        assert resp.status_code == 422

    def test_interactions_single_ndc_returns_empty(self, client):
        resp = client.get("/drugs/interactions?ndcs=12345-678-90")
        assert resp.status_code == 200
        assert resp.json() == []
