"""
Tests for the Return-to-Stock (RTS) feature.

Covers:
- GET /rts/lookup/{refill_id}: preview info for a READY refill
- GET /rts/lookup/rx/{prescription_id}: lookup by Rx (prescription) number
- POST /rts: process the return, stock update, prescription quantity restore
- GET /rts: history list
- Edge cases: wrong state, double-RTS
"""

import pytest
from datetime import date
from decimal import Decimal

from app.models import RxState, Stock
from tests.conftest import make_drug, make_patient, make_prescriber, make_prescription, make_refill


# ---------------------------------------------------------------------------
# Helper: advance refill to READY state
# ---------------------------------------------------------------------------

def _advance_to_ready(client, refill_id: int) -> None:
    """Walk a refill from QT through to READY via the advance endpoint."""
    for _ in range(4):
        r = client.post(f"/refills/{refill_id}/advance", json={})
        assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# GET /rts/lookup/{refill_id}
# ---------------------------------------------------------------------------

class TestRTSLookup:
    def test_lookup_ready_refill_returns_details(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session, first="Jane", last="Smith")
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)

        resp = client.get(f"/rts/lookup/{refill.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["refill_id"] == refill.id
        assert data["drug_name"] == drug.drug_name
        assert data["quantity"] == 30
        assert "Smith" in data["patient_name"]

    def test_lookup_nonexistent_refill_returns_404(self, client, db_session):
        resp = client.get("/rts/lookup/999999")
        assert resp.status_code == 404

    def test_lookup_non_ready_refill_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QT)
        db_session.commit()

        # Still in QT — not READY
        resp = client.get(f"/rts/lookup/{refill.id}")
        assert resp.status_code == 400
        assert "READY" in resp.json()["detail"]

    def test_lookup_hold_refill_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.HOLD)
        db_session.commit()

        resp = client.get(f"/rts/lookup/{refill.id}")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /rts/lookup/rx/{prescription_id}
# ---------------------------------------------------------------------------

class TestRTSLookupByRx:
    def test_lookup_by_rx_returns_ready_refill(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session, first="Jane", last="Smith")
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)

        resp = client.get(f"/rts/lookup/rx/{prescription.id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["refill_id"] == refill.id
        assert data["drug_name"] == drug.drug_name
        assert data["quantity"] == 30
        assert "Smith" in data["patient_name"]

    def test_lookup_by_rx_nonexistent_prescription_returns_404(self, client, db_session):
        resp = client.get("/rts/lookup/rx/999999")
        assert resp.status_code == 404

    def test_lookup_by_rx_no_ready_refill_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber)
        make_refill(db_session, prescription, drug, patient, state=RxState.QT)
        db_session.commit()

        resp = client.get(f"/rts/lookup/rx/{prescription.id}")
        assert resp.status_code == 400
        assert "READY" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# POST /rts
# ---------------------------------------------------------------------------

class TestProcessRTS:
    def test_rts_transitions_refill_to_rts_state(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)

        resp = client.post("/rts", json={"refill_id": refill.id})
        assert resp.status_code == 201, resp.text

        db_session.expire_all()
        from app.models import Refill as RefillModel
        updated = db_session.get(RefillModel, refill.id)
        assert updated.state == RxState.RTS

    def test_rts_increases_stock_quantity(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)  # starts with 5000 units stock
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        stock_before = db_session.query(Stock).filter(Stock.drug_id == drug.id).first()
        qty_before = stock_before.quantity

        _advance_to_ready(client, refill.id)

        resp = client.post("/rts", json={"refill_id": refill.id})
        assert resp.status_code == 201

        db_session.expire_all()
        stock_after = db_session.query(Stock).filter(Stock.drug_id == drug.id).first()
        assert stock_after.quantity == qty_before + 30

    def test_rts_restores_prescription_remaining_quantity(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        # Before advancing: remaining_qty should be 90 - 30 = 60 (reserved when fill entered active chain)
        _advance_to_ready(client, refill.id)

        db_session.expire_all()
        from app.models import Prescription as PrescriptionModel
        rx_mid = db_session.get(PrescriptionModel, prescription.id)
        qty_mid = rx_mid.remaining_quantity  # should be 60 (30 reserved)

        resp = client.post("/rts", json={"refill_id": refill.id})
        assert resp.status_code == 201

        db_session.expire_all()
        rx_after = db_session.get(PrescriptionModel, prescription.id)
        # Quantity restored — should be qty_mid + 30 = 90
        assert rx_after.remaining_quantity == qty_mid + 30

    def test_rts_creates_return_to_stock_record(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)

        resp = client.post("/rts", json={"refill_id": refill.id})
        assert resp.status_code == 201

        data = resp.json()
        assert data["refill_id"] == refill.id
        assert data["drug_id"] == drug.id
        assert data["quantity"] == 30
        assert data["returned_by"] == "test_user"
        assert "returned_at" in data

    def test_rts_non_ready_refill_returns_400(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber)
        refill = make_refill(db_session, prescription, drug, patient, state=RxState.QT)
        db_session.commit()

        # Still QT
        resp = client.post("/rts", json={"refill_id": refill.id})
        assert resp.status_code == 400
        assert "READY" in resp.json()["detail"]

    def test_rts_nonexistent_refill_returns_404(self, client, db_session):
        resp = client.post("/rts", json={"refill_id": 999999})
        assert resp.status_code == 404

    def test_rts_already_rts_refill_returns_400(self, client, db_session):
        """Double-RTS: second attempt fails because state is already RTS."""
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)

        r1 = client.post("/rts", json={"refill_id": refill.id})
        assert r1.status_code == 201

        r2 = client.post("/rts", json={"refill_id": refill.id})
        assert r2.status_code == 400


# ---------------------------------------------------------------------------
# GET /rts (history)
# ---------------------------------------------------------------------------

class TestRTSHistory:
    def test_empty_history_returns_empty_list(self, client, db_session):
        resp = client.get("/rts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_history_shows_processed_rts_records(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)
        client.post("/rts", json={"refill_id": refill.id})

        resp = client.get("/rts")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["refill_id"] == refill.id
        assert data["items"][0]["quantity"] == 30

    def test_history_includes_drug_details(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session, name="Metoprolol")
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=60, state=RxState.QT)
        db_session.commit()

        _advance_to_ready(client, refill.id)
        client.post("/rts", json={"refill_id": refill.id})

        resp = client.get("/rts")
        item = resp.json()["items"][0]
        assert item["drug"]["drug_name"] == "Metoprolol"
        assert item["quantity"] == 60


# ---------------------------------------------------------------------------
# Stock view RTS aggregates
# ---------------------------------------------------------------------------

class TestStockRTSAggregates:
    def test_stock_rts_count_and_quantity_appear_in_stock_view(self, client, db_session):
        prescriber = make_prescriber(db_session)
        drug = make_drug(db_session)
        patient = make_patient(db_session)
        prescription = make_prescription(db_session, patient, drug, prescriber, original_qty=90, remaining_qty=90)
        refill = make_refill(db_session, prescription, drug, patient, quantity=30, state=RxState.QT)
        db_session.commit()

        # Before any RTS: counts should be 0
        resp = client.get("/stock")
        assert resp.status_code == 200
        stock_item = next(s for s in resp.json()["items"] if s["drug_id"] == drug.id)
        assert stock_item["rts_count"] == 0
        assert stock_item["rts_quantity"] == 0

        _advance_to_ready(client, refill.id)
        client.post("/rts", json={"refill_id": refill.id})

        # After RTS: counts should reflect the one event
        resp = client.get("/stock")
        stock_item = next(s for s in resp.json()["items"] if s["drug_id"] == drug.id)
        assert stock_item["rts_count"] == 1
        assert stock_item["rts_quantity"] == 30
