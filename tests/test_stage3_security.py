"""Stage 3 role enforcement and pseudonymous lifecycle drills."""
from datetime import timedelta
from dataclasses import replace
import hmac
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from fastapi.testclient import TestClient

from rankflow.api import create_app, from_environment
from rankflow.retention import expire
from rankflow.security import signature
from tests import test_stage2 as fixture
from tests.test_stage1 import event, payload


def authorization(role):
    return {"Authorization": f"Bearer fixture-{role}"}


class SecurityDrills(TestCase):
    def app(self, store=None, traffic=None, **kwargs):
        return create_app(fixture.STABLE, store, traffic=traffic, admin_bearer=b"fixture-admin",
                          operator_bearer=b"fixture-operator", viewer_bearer=b"fixture-viewer",
                          signing_key=fixture.SIGNING, **kwargs)

    def test_role_matrix_and_sealed_boundaries(self):
        generation = replace(fixture.STABLE, examples={**fixture.STABLE.examples, "W2-gate": [], "W3": []})
        with patch.object(fixture, "STABLE", generation):
            app = self.app()
        with TestClient(app) as client:
            calls = [
                ("GET", "/operator", [401, 200, 200, 200]),
                ("GET", "/operator/status", [401, 200, 200, 200]),
                ("GET", "/operator/metrics", [401, 200, 200, 200]),
                ("GET", "/operator/runbook", [401, 200, 200, 200]),
                ("GET", "/operator/events", [401, 503, 503, 503]),
                ("GET", "/operator/epochs", [401, 503, 503, 503]),
                ("GET", "/operator/releases", [401, 403, 200, 200]),
                ("POST", "/operator/epochs", [401, 403, 403, 503]),
                ("POST", "/operator/prepare", [401, 403, 503, 503]),
                ("POST", "/operator/traffic/kill", [401, 403, 503, 503]),
            ]
            for method, route, codes in calls:
                for role, code in zip(("public", "viewer", "operator", "admin"), codes):
                    with self.subTest(route=route, method=method, role=role):
                        response = client.request(method, route, headers=authorization(role) if role != "public" else {},
                                                  json={"expected_revision": 0, "operation_id": "fixture"})
                        self.assertEqual(response.status_code, code)
            for role in ("public", "viewer", "operator", "admin"):
                headers = authorization(role) if role != "public" else {}
                for route in ("/health/live", "/health/ready", "/health/routable", "/openapi.json", "/docs",
                              "/docs/oauth2-redirect", "/redoc"):
                    self.assertEqual(client.get(route, headers=headers).status_code, 200)
                for route in ("/v1/recommend", "/v1/playground/rank"):
                    self.assertEqual(client.post(route, headers=headers, json=payload([event(1)])).status_code, 200)
                self.assertEqual(client.post("/v1/impressions/fixture/ack", headers=headers).status_code, 404)
                feedback = {"event_id": "fixture", "impression_id": "fixture", "aid": 1,
                            "action": "click", "occurred_at": "2026-01-01T00:00:00Z", "source": "demo"}
                self.assertEqual(client.post("/v1/feedback", headers=headers, json=feedback).status_code, 404)
                self.assertEqual(client.get("/playground", headers=headers).status_code, 200)
                client.cookies.clear()
                for window in ("W2-gate", "W3"):
                    self.assertEqual(
                        client.get(f"/v1/playground/prefixes?window={window}", headers=authorization(role)).status_code,
                        404)
            self.assertEqual(client.get("/v1/playground/prefixes?window=W2-dev").status_code, 200)
            self.assertEqual(client.get("/operator/releases?token=fixture-admin").status_code, 401)
            self.assertEqual(client.get("/operator/status", headers={"Authorization": "Basic fixture-admin"}).status_code, 401)
        self.assertEqual(app.state.counters["public_window_denied"], 8)
        self.assertEqual(app.state.counters["protected_release_read_denied"], 3)

    def test_csrf_on_cookie_mutations_and_size_and_rate_limits(self):
        with TestClient(self.app()) as client:
            client.get("/playground")
            token = client.cookies["rankflow_csrf"]
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1)])).status_code, 403)
            self.assertEqual(client.post("/v1/playground/rank", json=payload([event(1)])).status_code, 403)
            self.assertEqual(client.post("/v1/impressions/fixture/ack").status_code, 403)
            self.assertEqual(client.post("/v1/feedback", json={
                "event_id": "fixture", "impression_id": "fixture", "aid": 1, "action": "click",
                "occurred_at": "2026-01-01T00:00:00Z", "source": "demo",
            }).status_code, 403)
            self.assertEqual(client.post("/operator/epochs", json={}, headers=authorization("admin")).status_code, 403)
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1)]),
                                         headers={"x-csrf-token": token}).status_code, 200)
            self.assertEqual(client.post("/v1/recommend", content=b"x" * 65537).status_code, 413)
        with TestClient(self.app(public_rate=.01, public_burst=1)) as client:
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1)])).status_code, 200)
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1)])).status_code, 429)

    def test_environment_rejects_reused_session_hmac_key(self):
        with TemporaryDirectory() as directory:
            rescue, salts = Path(directory) / "rescue.json", Path(directory) / "salts.json"
            rescue.write_text('{"stable_generation_id":"stable"}')
            salts.write_text('{"v1":"fixture-session-key"}')
            settings = {"RANKFLOW_GENERATION": "stable", "RANKFLOW_DATABASE_URL": "postgresql:///fixture",
                        "RANKFLOW_SESSION_KEY": "fixture-session-key", "RANKFLOW_RESCUE_CONFIG": str(rescue),
                        "RANKFLOW_ROUTING_SALTS": str(salts)}
            with patch.dict(os.environ, settings), self.assertRaisesRegex(ValueError, "configured separately"):
                from_environment()


@skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class PrivacyDrills(TestCase):
    setUp = fixture.PlatformTests.setUp
    registry = fixture.PlatformTests.registry

    def test_signed_operator_audit_and_retention_deletion(self):
        traffic = self.registry()
        app = SecurityDrills().app(self.store, traffic)
        with TestClient(app) as client:
            next_config = {"stable_generation_id": "stable", "state": "shadowing"}
            for action in ("resolve", "publish"):
                configuration = next_config if action == "resolve" else dict(next_config, state="promoted")
                self.assertEqual(client.post(f"/operator/traffic/{action}", headers=authorization("operator"),
                                             json={"expected_revision": 0, "operation_id": "denied",
                                                   "configuration": configuration}).status_code, 403)
            result = client.post("/operator/traffic/publish", headers=authorization("operator"),
                                 json={"expected_revision": 0, "operation_id": "signed-fixture",
                                       "configuration": next_config})
            self.assertEqual(result.status_code, 200)
            older = client.post("/v1/recommend", json=payload([event(1)])).json()["impression_id"]
            recent = client.post("/v1/recommend", json=payload([event(1)])).json()["impression_id"]
            client.post(f"/v1/impressions/{older}/ack").raise_for_status()
        with self.store.connect() as conn:
            signed = conn.execute("SELECT * FROM admin_audit_log").fetchone()
            self.assertTrue(hmac.compare_digest(signed["signature"], signature(fixture.SIGNING, signed["record"])))
            self.assertEqual(signed["record"]["actor"], "operator")
            conn.execute("UPDATE impressions SET created_at=created_at - interval '31 days' WHERE id=%s", (older,))
        self.store.drain()
        self.assertEqual(expire(self.store, timedelta(days=30)),
                         {"impressions_deleted": 1, "delivery_payloads_deleted": 1})
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT id FROM impressions").fetchall(), [{"id": recent}])
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM acknowledgements").fetchone()["n"], 0)
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM delivered_events").fetchone()["n"], 1)
