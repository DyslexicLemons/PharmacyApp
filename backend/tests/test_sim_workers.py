"""Tests for sim worker CRUD endpoints.

Regression coverage for the ResponseValidationError that occurred when
bench/activate returned a raw ORM object instead of SimWorkerOut.
"""
from unittest.mock import patch

import pytest
from tests.conftest import make_drug, make_patient, make_prescriber, make_refill, make_prescription
from app.models import SimWorker, SimWorkerRole, StationName, RxState, Stock, SystemConfig, Refill


def make_worker(db, name="Bot Alpha", role=SimWorkerRole.technician, is_active=True):
    w = SimWorker(name=name, role=role, is_active=is_active, speed=5,
                  current_station=StationName.triage)
    db.add(w)
    db.flush()
    return w


class TestSimWorkerCRUD:
    def test_list_workers_empty(self, client):
        resp = client.get("/sim-workers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_worker(self, client):
        resp = client.post("/sim-workers", json={
            "name": "Bot Alpha", "role": "technician", "speed": 5, "is_active": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Bot Alpha"
        assert data["role"] == "technician"
        assert data["is_active"] is True
        assert data["current_refill"] is None

    def test_activate_deactivate_no_refill(self, client, db_session):
        """Toggle is_active on a worker with no current_refill — must not raise ResponseValidationError."""
        worker = make_worker(db_session)
        db_session.commit()

        resp = client.put(f"/sim-workers/{worker.id}", json={"is_active": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        assert data["current_refill"] is None

        resp = client.put(f"/sim-workers/{worker.id}", json={"is_active": True})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    def test_activate_deactivate_with_active_refill(self, client, db_session):
        """Toggle is_active when worker has current_refill — response must include drug_name and patient_name."""
        drug = make_drug(db_session, name="Metformin", ndc="99999-001-01")
        patient = make_patient(db_session, first="Jane", last="Smith")
        prescriber = make_prescriber(db_session)
        rx = make_prescription(db_session, patient=patient, drug=drug, prescriber=prescriber)
        refill = make_refill(db_session, prescription=rx, drug=drug, patient=patient,
                             state=RxState.QP)
        db_session.commit()

        worker = make_worker(db_session, name="Bot Beta")
        worker.current_refill_id = refill.id
        db_session.commit()

        resp = client.put(f"/sim-workers/{worker.id}", json={"is_active": False})
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is False
        ctx = data["current_refill"]
        assert ctx is not None
        assert ctx["drug_name"] == "Metformin"
        assert ctx["patient_name"] == "Jane Smith"
        assert ctx["prescription_id"] == rx.id

    def test_update_worker_not_found(self, client):
        resp = client.put("/sim-workers/99999", json={"is_active": False})
        assert resp.status_code == 404


class TestSimStockAdjustment:
    """simulate_technician/simulate_pharmacist must call the same _adjust_stock
    used by the /advance router endpoint, so simulated fills deplete real Stock
    the same way real fills do — see app/workflow.py.
    """

    def test_simulate_technician_qp_to_qv2_decrements_stock(self, db_session):
        from app.tasks import simulate_technician

        db = db_session
        db.add(SystemConfig(id=1, simulation_enabled=True))
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QP)
        worker = make_worker(db, name="Bot Fill", role=SimWorkerRole.technician)
        worker.current_station = StationName.fill
        db.commit()

        stock_before = db.query(Stock).filter(Stock.drug_id == drug.id).first().quantity

        with patch("app.tasks._acquire_lock", return_value=True):
            result = simulate_technician()

        assert result["qp_to_qv2"] == 1
        db.expire_all()
        assert db.query(Stock).filter(Stock.drug_id == drug.id).first().quantity == stock_before - 30
        refreshed = db.query(Refill).filter(Refill.id == refill.id).first()
        assert refreshed.state == RxState.QV2

    def test_simulate_pharmacist_qv2_return_to_qp_restores_stock(self, db_session):
        from app.tasks import simulate_pharmacist

        db = db_session
        db.add(SystemConfig(id=1, simulation_enabled=True))
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        prescription = make_prescription(db, patient, drug, prescriber, 90, 90)
        refill = make_refill(db, prescription, drug, patient, quantity=30, state=RxState.QV2)
        worker = make_worker(db, name="Doc Verify2", role=SimWorkerRole.pharmacist)
        worker.current_station = StationName.verify_2
        db.commit()

        stock_before = db.query(Stock).filter(Stock.drug_id == drug.id).first().quantity

        # Force the ~10% "sent back for re-check" branch instead of approval to READY.
        with patch("app.tasks._acquire_lock", return_value=True), \
             patch("app.tasks.random.random", return_value=0.01):
            result = simulate_pharmacist()

        assert result["qv2_returned"] == 1
        db.expire_all()
        assert db.query(Stock).filter(Stock.drug_id == drug.id).first().quantity == stock_before + 30
        refreshed = db.query(Refill).filter(Refill.id == refill.id).first()
        assert refreshed.state == RxState.QP
