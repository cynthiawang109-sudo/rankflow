"""Signed drift measurements, alert hysteresis and Console visibility."""
import os
from unittest import TestCase, skipUnless

from fastapi.testclient import TestClient

from rankflow.api import create_app
from rankflow.drift import measure, monitor, reports
from rankflow.security import signature
from tests import test_stage2 as baseline


class DriftMeasurement(TestCase):
    def test_psi_and_sample_minimum(self):
        self.assertEqual(measure([1_000, 0], [1_000, 0], 0)["psi"], 0)
        self.assertGreater(measure([1_000, 0], [0, 1_000], 0)["psi"], 0.25)
        metrics = measure([1_000, 0], [750, 0], 250)
        self.assertIsNone(metrics["psi"])
        self.assertEqual(metrics["missing_rate"], 0.25)


@skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class DriftAudit(TestCase):
    setUp = baseline.PlatformTests.setUp

    def test_console_and_signed_alert_lifecycle(self):
        normal, shifted = [1_000, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 1_000]
        insufficient = [0, 0, 0, 0, 0, 10]
        windows = [("normal", normal, 0), ("shift", shifted, 0), ("shift", insufficient, 0),
                   ("shift", shifted, 0), ("shift", shifted, 0),
                   ("recovery", normal, 0), ("recovery", insufficient, 0),
                   ("recovery", normal, 0), ("recovery", normal, 0), ("normal", normal, 0)]
        key = baseline.SIGNING
        demo = monitor(self.store, key, baseline.STABLE.generation_id, normal, windows)
        records = reports(self.store, key, demo)
        subjects = [row["subject"] for row in records]
        self.assertEqual([row["status"] for row in subjects],
                         ["clear", "clear", "insufficient_data", "clear", "raised", "active",
                          "insufficient_data", "active", "recovered", "clear"])
        alert_id = subjects[4]["alert_id"]
        self.assertIsNotNone(alert_id)
        self.assertEqual({row["alert_id"] for row in subjects[4:9]}, {alert_id})
        self.assertIsNone(subjects[-1]["alert_id"])
        self.assertEqual(len({row["audit_id"] for row in records}), len(windows))
        self.assertTrue(all(row["recorded_at"] for row in records))
        self.assertEqual(reports(self.store, b"wrong signing key", demo), [])
        with self.store.connect() as conn:
            signatures = {row["audit_id"]: row["signature"]
                          for row in conn.execute("SELECT audit_id, signature FROM admin_audit_log")}
        for record in records:
            self.assertEqual(signatures[record["audit_id"]], signature(key, record))

        app = create_app(baseline.STABLE, self.store, viewer_bearer=baseline.SECRET, signing_key=key)
        with TestClient(app) as client:
            self.assertEqual(client.get("/operator/drift", params={"demo_id": demo}).status_code, 401)
            response = client.get("/operator/drift", params={"demo_id": demo},
                                  headers={"Authorization": "Bearer " + baseline.SECRET.decode()})
            self.assertEqual(response.status_code, 200)
            for text in (alert_id, records[4]["recorded_at"], records[8]["recorded_at"],
                         "raised", "recovered", "Investigate and block promotion", "observed_counts"):
                self.assertIn(text, response.text)
