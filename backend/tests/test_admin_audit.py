"""
test_admin_audit.py — verifies the admin data-generation/clear commands write
an AuditLog row, per CLAUDE.md's audit-logging convention for significant
write actions.
"""
from app.models import AuditLog
from tests.conftest import make_prescriber, make_drug, make_patient, make_prescription


class TestClearPrescriptionsAudit:
    def test_clear_prescriptions_writes_audit_log(self, client, base_data):
        resp = client.post("/commands/clear_prescriptions")
        assert resp.status_code == 200

        db = base_data["db"]
        log = db.query(AuditLog).filter(AuditLog.action == "PRESCRIPTIONS_CLEARED").first()
        assert log is not None
        assert "prescriptions_deleted=1" in log.details


class TestGeneratePrescriptionsCommandAudit:
    def test_generate_prescriptions_writes_audit_log(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        resp = client.post(
            "/commands/generate_prescriptions",
            json={"count": 3, "state": "QT"},
        )
        assert resp.status_code == 200

        log = db.query(AuditLog).filter(AuditLog.action == "PRESCRIPTIONS_GENERATED").first()
        assert log is not None
        assert "count=3" in log.details
        assert "state=QT" in log.details


class TestGenerateTestPrescriptionsAudit:
    def test_generate_test_prescriptions_writes_audit_log(self, client, db_session):
        db = db_session
        prescriber = make_prescriber(db)
        drug = make_drug(db)
        patient = make_patient(db)
        db.commit()

        resp = client.post("/commands/generate_test_prescriptions")
        assert resp.status_code == 200

        log = db.query(AuditLog).filter(AuditLog.action == "TEST_PRESCRIPTIONS_GENERATED").first()
        assert log is not None
        assert "prescriptions_created=50" in log.details
