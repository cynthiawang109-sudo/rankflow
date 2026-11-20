"""Stage 2 governance and PostgreSQL release drills."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from rankflow.api import create_app
from rankflow.demo_learning import collect, dataset, rehearse
from rankflow.epoch_registry import register_epoch
from rankflow.guardrails import Guardrails
from rankflow.release_gate import POLICY, append_signed, disposition, release
from rankflow.store import PostgresStore
from rankflow.traffic import TrafficConfigSnapshot, TrafficRegistry
from rankflow.training_pipeline import read_json
from tests.test_stage1 import GENERATION, MODEL, RULE, event, payload

STABLE = replace(GENERATION, generation_id="stable")
CANDIDATE = replace(GENERATION, generation_id="candidate", assigned=MODEL, challenger=RULE)
SECRET = b"stage2-test-key"
SIGNING = b"stage2-test-release-signing-key-32"


class FixtureRegistry(TrafficRegistry):
    def generation(self, identifier):
        return {"stable": STABLE, "candidate": CANDIDATE}[identifier]


class GateTests(unittest.TestCase):
    def test_weakened_candidate_is_rejected(self):
        from rankflow.training_pipeline import paired_evaluation

        weak = replace(MODEL, score=lambda rows: [-score for score in RULE.score(rows)])
        queries = [({"prefix_events": [event(1)], "session_id_hash": "s", "positive_aid": 1}, [event(1)])]
        evaluation, _ = paired_evaluation(queries, STABLE.snapshot, STABLE.config, weak)
        decision, _, _, _ = disposition(evaluation, weak.strategy_id, read_json(POLICY))
        self.assertEqual(decision, "rejected")

    def test_gate_record_requires_operator_bearer(self):
        with TemporaryDirectory() as workspace:
            registry = Path(workspace)
            record = {"window": "W2-gate", "decision": "rejected", "evaluation": {"private": True}}
            append_signed(registry / "gate.json", record, SIGNING)
            (registry / "forged.json").write_text(
                '{"record":{"window":"W2-gate","evaluation":{"forged":true}},"signature":"invalid"}')
            with TestClient(create_app(STABLE, admin_bearer=SECRET, release_registry=registry,
                                       signing_key=SIGNING)) as client:
                self.assertEqual(client.get("/operator/releases").status_code, 401)
                self.assertEqual(client.get("/v1/playground/prefixes?window=W2-gate").status_code, 404)
                headers = {"Authorization": "Bearer stage2-test-key"}
                response = client.get("/operator/releases", headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["record"] for row in response.json()], [record])

    def test_demo_provenance_rejected_before_gate_open(self):
        with TemporaryDirectory() as workspace:
            root = Path(workspace)
            (root / "run.json").write_text('{"lineage":{"artifact_sha256":"demo","source":"demo"}}')
            record = release(root / "sealed", root, root / "decisions", "test", SIGNING)["record"]
            self.assertEqual(record["decision"], "rejected")
            self.assertNotIn("evaluation", record)
            self.assertEqual(len(list((root / "decisions").glob("*.json"))), 1)


@unittest.skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class PlatformTests(unittest.TestCase):
    def setUp(self):
        from psycopg import sql

        admin = PostgresStore(os.environ["RANKFLOW_TEST_DATABASE_URL"])
        schema = sql.Identifier("stage2_" + uuid4().hex)

        def clean():
            with admin.connect() as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(schema))

        with admin.connect() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
        self.addCleanup(clean)

        class TestStore(PostgresStore):
            def connect(self):
                conn = super().connect()
                conn.execute(sql.SQL("SET search_path TO {}").format(schema))
                conn.commit()
                return conn

        self.store = TestStore(admin.dsn)
        self.store.initialize()
        self.rescue = TrafficConfigSnapshot("stable")

    def registry(self):
        registry = FixtureRegistry(self.store, Path("."), self.rescue, {"v1": SECRET})
        registry.initialize()
        registry.refresh()
        return registry

    def test_two_instances_sticky_canary_cas_and_kill(self):
        first, second = self.registry(), self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        first.publish(shadow, 0, "shadow", "test")
        first.refresh()
        second.refresh()
        old = second.pin()
        canary = replace(shadow, state="canary", canary_generation_id="candidate", canary_percent=50)
        first.prepare(canary)
        first.refresh()
        with self.assertRaisesRegex(ValueError, "every leased instance"):
            first.publish(canary, 1, "early", "test")
        second.refresh()

        def attempt(registry, operation):
            try:
                return registry.publish(canary, 1, operation, "test")
            except ValueError:
                return None

        with ThreadPoolExecutor(2) as executor:
            calls = [executor.submit(attempt, first, "one"), executor.submit(attempt, second, "two")]
            self.assertCountEqual([call.result() for call in calls], [2, None])
        first.refresh()
        second.refresh()
        self.assertEqual({row["revision"] for row in first.fleet()}, {2})
        self.assertEqual(old.select("session")[1], "stable")
        self.assertEqual(old.config.config_id, shadow.config_id)
        self.assertEqual(old.select("session")[0].generation_id, STABLE.generation_id)
        assignment = [first.pin().select(str(i))[1] for i in range(100)]
        self.assertEqual(set(assignment), {"stable", "canary"})
        self.assertEqual(assignment, [second.pin().select(str(i))[1] for i in range(100)])
        changed = replace(canary, shadow_mode=None, shadow_generation_id=None)
        first.prepare(changed)
        first.refresh()
        second.refresh()
        first.publish(changed, 2, "config-update", "test")
        first.refresh()
        self.assertEqual(assignment, [first.pin().select(str(i))[1] for i in range(100)])
        killed = replace(self.rescue, state="killed")
        self.assertEqual(first.publish(killed, 3, "kill", "test", "kill"), 4)
        self.assertEqual(first.publish(killed, 3, "kill", "test", "kill"), 4)
        first.refresh()
        self.assertEqual({first.pin().select(str(i))[1] for i in range(100)}, {"stable"})
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT action FROM traffic_audit WHERE revision=4").fetchone()["action"],
                             "kill")

    def test_live_shadow_feedback_and_outbox_replay(self):
        traffic = self.registry()
        headers = {"Authorization": "Bearer stage2-test-key"}
        app = create_app(STABLE, self.store, SECRET, traffic=traffic, admin_bearer=SECRET)
        with TemporaryDirectory() as temporary, TestClient(app) as client:
            self.assertEqual(client.get("/operator/events").status_code, 401)
            self.assertEqual(client.get("/operator/events", headers=headers).status_code, 200)
            shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
            traffic.publish(shadow, 0, "shadow", "test")
            traffic.refresh()
            for i in range(2):
                request = dict(payload([event(1)]), session_id=f"demo-{i}", top_k=4)
                decision = client.post("/v1/recommend", json=request).json()
                self.assertEqual(decision["assignment"], "stable")
                self.assertEqual(decision["assigned_strategy"], RULE.strategy_id)
                self.assertEqual(decision["config_id"], shadow.config_id)
                click = {"event_id": f"click-{i}", "impression_id": decision["impression_id"],
                         "action": "click", "source": "demo", "aid": decision["items"][i]["aid"],
                         "occurred_at": datetime.now(timezone.utc).isoformat()}
                self.assertEqual(client.post("/v1/feedback", json=click).json()["source"], "demo")
                self.assertEqual(client.post("/v1/feedback", json=dict(click, aid=99, event_id="outside")).status_code, 422)
            self.assertEqual(app.state.counters["synthetic_shadow_completed"], 2)
            self.assertEqual(len(dataset(collect(self.store, STABLE), STABLE)["examples"]), 2)
            run = rehearse(self.store, STABLE, Path(temporary), SIGNING)
            self.assertEqual(read_json(run / "decision.json")["record"]["decision"], "rejected")
            self.store.drain()
            with self.store.connect() as conn:
                conn.execute("UPDATE outbox SET delivered_at=NULL")
            self.store.drain()
            with self.store.connect() as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM delivered_events").fetchone()["count"], 2)

    def test_control_outage_uses_designated_rescue(self):
        first, second = self.registry(), self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        first.publish(shadow, 0, "shadow-before-outage", "test")
        first.refresh()
        second.refresh()
        pinned = first.pin()
        with patch.object(self.store, "connect", side_effect=OSError("test outage")):
            with self.assertLogs("rankflow.traffic", "ERROR"):
                first.refresh()
                second.refresh()
        self.assertEqual(pinned.config.config_id, shadow.config_id)
        for instance in (first, second):
            pin = instance.pin()
            self.assertTrue(pin.degraded)
            self.assertEqual(pin.config.config_id, self.rescue.config_id)
            self.assertEqual(pin.select("existing-session")[1], "stable")
            instance.refresh()
            self.assertFalse(instance.pin().degraded)

    def test_rollback_targets_named_config(self):
        registry = self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        registry.publish(shadow, 0, "shadow", "test")
        self.assertEqual(registry.publish(self.rescue.config_id, 1, "rollback", "test", "rollback"), 2)
        self.assertEqual(registry.publish(self.rescue.config_id, 1, "rollback", "test", "rollback"), 2)
        registry.refresh()
        self.assertEqual(registry.pin().config.config_id, self.rescue.config_id)
        self.assertEqual(registry.pin().revision, 2)

    def test_late_ack_preserves_confirmed_state_and_deduplicates(self):
        with TestClient(create_app(STABLE, self.store, SECRET)) as client:
            impression = client.post("/v1/recommend", json=payload([event(1)])).json()["impression_id"]
            route = f"/v1/impressions/{impression}/ack"
            self.assertEqual(client.post(route).json()["client_confirmation_state"], "confirmed")
            with self.store.connect() as conn:
                conn.execute("UPDATE impressions SET created_at = created_at - interval '1 hour' WHERE id = %s",
                             (impression,))
            for _ in range(2):
                self.assertEqual(client.post(route).json()["client_confirmation_state"], "confirmed")
            with self.store.connect() as conn:
                rows = conn.execute("SELECT kind FROM acknowledgements WHERE impression_id = %s",
                                    (impression,)).fetchall()
        self.assertCountEqual([row["kind"] for row in rows], ["confirmed", "late_confirmation"])

    def test_failed_rollback_convergence_activates_rescue_and_freezes_release(self):
        first, second = self.registry(), self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        first.publish(shadow, 0, "shadow", "test")
        first.publish(self.rescue.config_id, 1, "rollback", "test", "rollback")
        first.refresh()
        with self.store.connect() as conn:
            conn.execute("UPDATE traffic_audit SET recorded_at = recorded_at - interval '1 minute' WHERE revision=2")
        first.observe_convergence()
        first.refresh()
        second.refresh()
        self.assertTrue(first.pin().degraded)
        self.assertTrue(second.pin().degraded)
        self.assertEqual(first.pin().config.config_id, second.pin().config.config_id)
        with self.assertRaisesRegex(ValueError, "frozen"):
            first.publish(shadow, 3, "blocked", "test")
        first.publish(self.rescue, 3, "resolve", "test", "resolve")
        first.refresh()
        self.assertFalse(first.pin().degraded)

    def test_unknown_canary_telemetry_auto_pauses(self):
        traffic = self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        traffic.publish(shadow, 0, "shadow", "test")
        canary = replace(shadow, state="canary", canary_generation_id="candidate", canary_percent=50)
        traffic.prepare(canary)
        traffic.refresh()
        traffic.publish(canary, 1, "canary", "test")
        traffic.refresh()
        guardrails = Guardrails(self.store, traffic)
        now = datetime.now(timezone.utc)
        self.assertEqual(guardrails.sample(traffic.pin(), now)["state"], "unknown")
        with self.assertLogs("rankflow.guardrails", "WARNING"):
            self.assertEqual(guardrails.sample(traffic.pin(), now + timedelta(minutes=3))["state"], "auto_pause")
        traffic.refresh()
        self.assertEqual(traffic.pin().config.state, "killed")
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT action FROM traffic_audit WHERE revision=3").fetchone()["action"],
                             "auto_pause")

        traffic.publish(canary, 3, "override", "operator", "override", reason="Synthetic validation",
                        override_seconds=30)
        traffic.refresh()
        with self.store.connect() as conn:
            expiry = conn.execute("SELECT * FROM traffic_overrides WHERE revision = 4").fetchone()
        self.assertEqual(expiry["reason"], "Synthetic validation")
        self.assertEqual(guardrails.sample(traffic.pin(), expiry["expires_at"] - timedelta(seconds=1))["state"],
                         "override")
        with self.assertLogs("rankflow.guardrails", "WARNING"):
            self.assertEqual(guardrails.sample(traffic.pin(), expiry["expires_at"])["state"], "override_expired")
        traffic.refresh()
        self.assertEqual(traffic.pin().config.state, "killed")

    def test_sustained_canary_fallback_pauses(self):
        traffic = self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="candidate", shadow_mode="live")
        traffic.publish(shadow, 0, "shadow", "test")
        canary = replace(shadow, state="canary", canary_generation_id="candidate", canary_percent=50)
        traffic.prepare(canary)
        traffic.refresh()
        traffic.publish(canary, 1, "canary", "test")
        traffic.refresh()
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=3)
        with self.store.connect() as conn:
            conn.execute("UPDATE traffic_audit SET recorded_at=%s WHERE revision=2",
                         (end - timedelta(minutes=3),))
            for offset, failed in ((3, False), (2, True), (1, True)):
                for index in range(20):
                    impression = str(uuid4())
                    conn.execute("INSERT INTO impressions (id, generation, items, created_at) "
                                 "VALUES (%s, 'stable', '[]', %s)",
                                 (impression, end - timedelta(minutes=offset)))
                    conn.execute("INSERT INTO decisions VALUES (%s, "
                                 "jsonb_build_object('config_revision', 2, 'source', 'demo', "
                                 "'assignment', 'canary', 'assigned_generation_id', 'candidate', "
                                 "'fallback_used', %s::boolean))", (impression, failed and index < 2))
        guardrails = Guardrails(self.store, traffic)
        sample = guardrails.sample(traffic.pin(), end - timedelta(minutes=1))
        self.assertEqual(sample["health"], "degraded")
        self.assertNotEqual(sample["state"], "auto_pause")
        with self.assertLogs("rankflow.operations", "WARNING") as alerts:
            sample = guardrails.sample(traffic.pin(), end)
        self.assertEqual((sample["health"], sample["state"]), ("degraded", "auto_pause"))
        self.assertIn("canary_fallback", alerts.output[0])
        traffic.refresh()
        self.assertEqual(traffic.pin().config.state, "killed")
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT action FROM traffic_audit WHERE revision=3").fetchone()["action"],
                             "auto_pause")

    def test_epoch_overlap_and_preserved_replay(self):
        epoch = {"epoch_id": "one", "source": "otto_offline", "history_statistics_watermark": 10,
                 "training_data_watermark": 19, "validation_window": [20, 30], "final_test_window": [30, 40],
                 "retrieval_snapshot_id": "fixture-snapshot", "dataset_manifest_hash": "fixture",
                 "query_manifest_hash": "fixture", "candidate_family": ["LightGBM-LambdaRank", 1, "nextclick-v1"]}
        self.assertTrue(register_epoch(self.store, epoch))
        with self.assertRaisesRegex(ValueError, "overlap"):
            register_epoch(self.store, dict(epoch, epoch_id="overlap"))
        with TestClient(create_app(STABLE)) as client:
            before = client.post("/v1/recommend", json=payload([event(1)])).json()["items"]
            self.assertTrue(register_epoch(self.store, dict(epoch, epoch_id="two", training_data_watermark=49,
                                                           validation_window=[50, 60], final_test_window=[60, 70])))
            after = client.post("/v1/recommend", json=payload([event(1)])).json()["items"]
        self.assertEqual(before, after)
