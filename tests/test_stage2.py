"""Stage 2 governance and PostgreSQL release drills."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from rankflow.api import create_app
from rankflow.demo_learning import collect, dataset, rehearse
from rankflow.epoch_registry import register_epoch
from rankflow.release_gate import POLICY, disposition, release
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
