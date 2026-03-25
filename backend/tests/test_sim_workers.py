"""Tests for sim worker CRUD endpoints.

Regression coverage for the ResponseValidationError that occurred when
bench/activate returned a raw ORM object instead of SimWorkerOut.
"""
import pytest
from tests.conftest import make_drug, make_patient, make_prescriber, make_refill, make_prescription
from app.models import SimWorker, SimWorkerRole, StationName, RxState


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
