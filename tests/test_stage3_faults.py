"""Repeatable Stage 3 fault drills with PostgreSQL-backed assertions."""
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
from unittest import TestCase, skipUnless
from unittest.mock import patch

from fastapi.testclient import TestClient
from psycopg import OperationalError
from psycopg.conninfo import make_conninfo

from rankflow.api import create_app, rank_request
from rankflow.data.epoch import generate_queries
from rankflow.data.pipeline import FIXTURE, build_run, read_config
from rankflow.generation import build, cached_generation, encoded, identity
from rankflow.retrieval import RetrievalConfig
from rankflow.scorer import Scorer
from rankflow.store import PostgresStore
from rankflow.train import run as train
from tests import test_stage2 as baseline
from tests.test_stage1 import event, payload


class ArtifactAndScorerDrills(TestCase):
    def test_partial_and_corrupt_artifact_never_activate(self):
        with TemporaryDirectory() as workspace:
            root = Path(workspace)
            dataset, training = root / "data", root / "training"
            build_run(FIXTURE, dataset, read_config(Path("configs/stage0.yaml")))
            train(dataset, training, RetrievalConfig(recent=10, covisitation=100, popularity=20),
                  "Stage 3 synthetic artifact integrity fixture")
            good = build(dataset, training, root / "registry")
            source = root / good.name
            cache = root / "cache"
            shutil.copytree(good, source)
            model = source / "lgbm-v1.txt"
            model.unlink()
            with self.assertRaises(FileNotFoundError):
                cached_generation(source, cache)
            self.assertFalse((cache / good.name).exists())
            model.write_bytes(b"damaged")
            with self.assertRaisesRegex(ValueError, "checksum"):
                cached_generation(source, cache)
            self.assertFalse((cache / good.name).exists())
            shutil.copyfile(good / model.name, model)
            self.assertEqual(cached_generation(source, cache).generation_id, good.name)
            for field, value in (("feature_schema", "incompatible-schema"), ("feature_code_sha256", "0" * 64)):
                with self.subTest(incompatible=field):
                    manifest = json.loads((good / "manifest.json").read_bytes())
                    manifest["compatibility"][field] = value
                    incompatible_id = identity(manifest)
                    incompatible = root / incompatible_id
                    shutil.copytree(good, incompatible)
                    (incompatible / "manifest.json").write_bytes(encoded(manifest))
                    with self.assertRaisesRegex(ValueError, "Serving feature compatibility mismatch"):
                        cached_generation(incompatible, cache)
                    self.assertFalse((cache / incompatible_id).exists())

    def test_scorer_hang_and_crash_fall_back(self):
        for mode, reason in (("hang", "logical_deadline"), ("crash", "ml_scoring_error")):
            with self.subTest(mode=mode):
                scorer = Scorer("tests.stage3_fault_worker")
                self.addCleanup(scorer.close)
                path = Path(mode)
                generation = replace(baseline.CANDIDATE, model_path=path)
                with self.assertRaises(TimeoutError):
                    scorer.score(path, generation.assigned.artifact_hash, [[0]], 20)
                deadline = monotonic() + 10
                while scorer.warmed is None and monotonic() < deadline:
                    sleep(.02)
                self.assertIsNotNone(scorer.warmed)
                started = monotonic()
                result, decision = rank_request(generation, [event(1)], 3, 200, scorer=scorer,
                                               request_id=f"fault-{mode}")
                self.assertLess(monotonic() - started, 1)
                self.assertEqual(decision["fallback_reason"], reason)
                self.assertEqual(result["served_strategy"], "rule-v1")
                self.assertNotEqual(result["served_strategy"], result["assigned_strategy"])


@skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class DatabaseFaultDrills(TestCase):
    setUp = baseline.PlatformTests.setUp
    registry = baseline.PlatformTests.registry

    def test_event_store_outage_and_recovery(self):
        with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET)) as client:
            with patch.object(self.store, "connect", side_effect=OperationalError("injected database outage")):
                response = client.post("/v1/recommend", json=payload([event(1)])).json()
            self.assertEqual(response["logging_status"], "degraded")
            self.assertIsNone(response["impression_id"])
            with self.store.connect() as connection:
                self.assertEqual(connection.execute("SELECT count(*) AS n FROM decisions").fetchone()["n"], 0)
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1)])).json()["logging_status"],
                             "persisted")

    def test_control_plane_outage_at_startup(self):
        control = PostgresStore(self.store.dsn)
        traffic = baseline.FixtureRegistry(control, Path("."), self.rescue, {"v1": baseline.SECRET})
        with patch.object(control, "connect", side_effect=OperationalError("injected startup outage")):
            with self.assertLogs("rankflow.api", "ERROR"):
                with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET, traffic=traffic)) as client:
                    result = client.post("/v1/recommend", json=payload([event(1)])).json()
                    readiness = client.get("/health/ready").json()
        self.assertEqual(result["config_id"], self.rescue.config_id)
        self.assertEqual(result["assignment"], "stable")
        self.assertTrue(readiness["serving_ready"])
        self.assertFalse(readiness["release_ready"])

    def test_inference_hang_during_shadow_saturation(self):
        traffic = self.registry()
        shadow = replace(self.rescue, state="shadowing", shadow_generation_id="stable", shadow_mode="live")
        traffic.publish(shadow, 0, "saturated-shadow", "test")
        candidate = replace(baseline.CANDIDATE, model_path=Path("hang"))
        canary = replace(shadow, state="canary", canary_generation_id="candidate", canary_percent=100)
        shadow_entered, release_shadow = Event(), Event()
        foreground = Scorer("tests.stage3_fault_worker")
        background, comparison = Scorer(), Scorer()

        def rank(*args, **kwargs):
            if kwargs.get("scorer") is background:
                shadow_entered.set()
                if not release_shadow.wait(15):
                    raise RuntimeError("Shadow fixture did not release")
            return rank_request(*args, **kwargs)

        def recommend(client):
            response = client.post("/v1/recommend", json=payload([event(1)]))
            response.raise_for_status()
            return response.json()

        with patch.object(traffic, "generation", side_effect={"stable": baseline.STABLE,
                                                              "candidate": candidate}.__getitem__):
            traffic.prepare(canary)
            traffic.refresh()
            traffic.publish(canary, 1, "hanging-canary", "test")
            traffic.refresh()
            with patch("rankflow.api.Scorer", side_effect=(foreground, background, comparison)):
                app = create_app(baseline.STABLE, self.store, baseline.SECRET, traffic=traffic, deadline_ms=100)
            with TestClient(app) as client, patch("rankflow.api.rank_request", side_effect=rank):
                foreground.prepare(candidate.model_path, candidate.assigned.artifact_hash)
                hanging_worker = foreground.process
                with ThreadPoolExecutor(4) as workers:
                    first = workers.submit(recommend, client)
                    try:
                        self.assertTrue(shadow_entered.wait(5))
                        others = [workers.submit(recommend, client) for _ in range(3)]
                        completed, _ = wait(others, timeout=5, return_when=FIRST_COMPLETED)
                        self.assertTrue(completed)
                        self.assertGreater(app.state.counters["synthetic_shadow_shed"], 0)
                        self.assertIsNotNone(hanging_worker.wait(timeout=2))
                    finally:
                        release_shadow.set()
                    for future in [first, *others]:
                        result = future.result(timeout=10)
                        self.assertTrue(result["fallback_used"])
                        self.assertEqual(result["served_strategy"], "rule-v1")
                        self.assertEqual(result["logging_status"], "persisted")
                healthy_path = Path("recovered")
                foreground.prepare(healthy_path, candidate.assigned.artifact_hash)
                self.assertEqual(foreground.score(healthy_path, candidate.assigned.artifact_hash, [[0]], 500), [0])
                traffic.publish(self.rescue.config_id, 2, "stable-after-overload", "test", "rollback")
                traffic.refresh()
                self.assertFalse(recommend(client)["fallback_used"])

    def test_same_millisecond_query_identity_survives_delivery(self):
        events = [dict(event(aid), event_index=index) for index, aid in enumerate((1, 2, 3))]
        configuration = {"queries": {"min_prefix_length": 1, "max_cutoffs_per_session": 3},
                         "sampler": {"seed": 3}, "label_policy_version": "fixture"}
        queries = list(generate_queries(15, events, "W1", "fixture", "fixture-snapshot",
                                        "otto_offline", configuration))
        impression_ids = []
        with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET)) as client:
            for query in queries:
                session, index = query["query_id"]
                prefix = [{key: item[key] for key in ("aid", "ts", "type")} for item in query["prefix_events"]]
                recommendation = dict(payload(prefix), request_id=f"fixture:{session}:{index}")
                response = client.post("/v1/recommend", json=recommendation).raise_for_status().json()
                impression_ids.append(response["impression_id"])
        self.assertEqual(len(set(impression_ids)), 3)
        self.store.drain()
        with self.store.connect() as connection:
            rows = connection.execute("SELECT payload FROM delivered_events ORDER BY payload->>'request_id'").fetchall()
        self.assertEqual([row["payload"]["request_id"] for row in rows],
                         ["fixture:15:0", "fixture:15:1", "fixture:15:2"])
        self.assertEqual([row["payload"]["cutoff_ts"] for row in rows], [20, 20, 20])
        self.assertEqual([len(row["payload"]["prefix_events"]) for row in rows], [1, 2, 3])

    def test_concurrent_publish_loser_retries_at_winning_revision(self):
        first, second = self.registry(), self.registry()
        target = replace(self.rescue, state="shadowing")

        def attempt(pair):
            index, instance = pair
            try:
                return index, instance.publish(target, 0, f"publish-{index}", "fault-drill")
            except ValueError as error:
                self.assertIn("revision conflict", str(error))
                return index, None

        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(attempt, enumerate((first, second))))
        self.assertCountEqual([revision for _, revision in results], [1, None])
        loser = next(index for index, revision in results if revision is None)
        instance = (first, second)[loser]
        instance.refresh()
        self.assertEqual(instance.pin().revision, 1)
        self.assertEqual(instance.publish(target, 1, f"publish-{loser}", "fault-drill"), 2)

    def interrupt(self, operation):
        with self.store.connect() as connection:
            schema = connection.execute("SELECT current_schema() AS name").fetchone()["name"]
        env = dict(os.environ, RANKFLOW_FAULT_DATABASE_URL=make_conninfo(
            self.store.dsn, options=f"-c search_path={schema}"))
        with subprocess.Popen([sys.executable, "-m", "tests.stage3_fault_worker", operation],
                              env=env, stdout=subprocess.PIPE) as child:
            with ThreadPoolExecutor(1) as reading:
                output = reading.submit(child.stdout.readline)
                try:
                    return output.result(timeout=90).strip()
                finally:
                    child.kill()
                    child.wait(timeout=10)

    def test_kill_mid_write_then_outbox_crash_and_redelivery(self):
        self.assertEqual(self.interrupt("persist"), b"transaction_open")
        with self.store.connect() as conn:
            for table in ("impressions", "decisions", "outbox"):
                self.assertEqual(conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"], 0)
        self.store.persist({"request_id": "restarted", "items": [], "serving_generation": "stable"})
        self.assertEqual(self.interrupt("drain"), b"transaction_open")
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM delivered_events").fetchone()["n"], 0)
            self.assertIsNone(conn.execute("SELECT delivered_at FROM outbox").fetchone()["delivered_at"])
        self.assertEqual(self.store.drain(), 1)
        with self.store.connect() as conn:
            conn.execute("UPDATE outbox SET delivered_at = NULL")
        self.assertEqual(self.store.drain(), 1)
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM delivered_events").fetchone()["n"], 1)

    def test_render_then_crash_preserves_unknown_send_and_confirmation(self):
        rendered = json.loads(self.interrupt("send"))
        self.assertEqual(rendered["logging_status"], "persisted")
        impression = rendered["impression_id"]
        acknowledgement = f"/v1/impressions/{impression}/ack"
        headers = {"Authorization": "Bearer " + baseline.SECRET.decode()}
        with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET,
                                   admin_bearer=baseline.SECRET)) as client:
            first = client.post(acknowledgement).raise_for_status().json()
            self.assertEqual(first["client_confirmation_state"], "confirmed")
            self.assertEqual(first["send_state"], "send_unknown")
            with self.store.connect() as conn:
                conn.execute("UPDATE impressions SET created_at=created_at - interval '10 minutes' WHERE id=%s",
                             (impression,))
            before = client.get("/operator/metrics", headers=headers).raise_for_status().json()["durable"][0]
            for _ in range(2):
                late = client.post(acknowledgement).raise_for_status().json()
                self.assertEqual(late["client_confirmation_state"], "confirmed")
                self.assertEqual(late["send_state"], "send_unknown")
            after = client.get("/operator/metrics", headers=headers).raise_for_status().json()["durable"][0]
        for row in (before, after):
            self.assertEqual((row["confirmed"], row["closed_impressions"]), (1, 1))
            self.assertEqual((row["send_completed"], row["send_failed"], row["send_unknown"]), (0, 0, 1))
        with self.store.connect() as conn:
            rows = conn.execute("SELECT kind FROM acknowledgements WHERE impression_id=%s", (impression,)).fetchall()
        self.assertCountEqual([row["kind"] for row in rows], ["confirmed", "late_confirmation"])

    def test_http_request_keeps_pin_during_publish(self):
        traffic, publisher = self.registry(), self.registry()
        entered, release = Event(), Event()
        real_rank = rank_request

        def blocked(*args, **kwargs):
            if not entered.is_set():
                entered.set()
                if not release.wait(10):
                    raise RuntimeError("Publish did not finish")
            return real_rank(*args, **kwargs)

        with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET, traffic=traffic)) as client:
            with patch("rankflow.api.rank_request", side_effect=blocked), ThreadPoolExecutor(1) as pool:
                future = pool.submit(client.post, "/v1/recommend", json=payload([event(1)]))
                try:
                    self.assertTrue(entered.wait(5))
                    next_config = replace(self.rescue, state="shadowing")
                    publisher.publish(next_config, 0, "concurrent-publish", "fault-drill")
                    traffic.refresh()
                finally:
                    release.set()
                old = future.result(timeout=10).json()
            new = client.post("/v1/recommend", json=payload([event(1)])).json()
        self.assertEqual((old["config_revision"], old["config_id"]), (0, self.rescue.config_id))
        self.assertEqual((new["config_revision"], new["config_id"]), (1, next_config.config_id))

    def test_clock_skew_and_late_ack_leave_closed_metrics_unchanged(self):
        with TestClient(create_app(baseline.STABLE, self.store, baseline.SECRET,
                                   admin_bearer=baseline.SECRET)) as client:
            rec = client.post("/v1/recommend", json=payload([event(1)])).json()
            impression = rec["impression_id"]
            headers = {"Authorization": "Bearer " + baseline.SECRET.decode()}
            feedback = {"event_id": "skewed", "impression_id": impression, "aid": rec["items"][0]["aid"],
                        "action": "click", "source": "demo",
                        "occurred_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()}
            self.assertEqual(client.post("/v1/feedback", json=feedback).json()["detail"],
                             "outside_attribution_window")
            with self.store.connect() as connection:
                connection.execute("UPDATE impressions SET created_at=created_at - interval '10 minutes'")
            before = client.get("/operator/metrics", headers=headers).json()["durable"]
            self.assertEqual((before[0]["confirmed"], before[0]["closed_impressions"]), (0, 1))
            for _ in range(2):
                reply = client.post(f"/v1/impressions/{impression}/ack").json()
                self.assertEqual(reply["acknowledgement_kind"], "late_confirmation")
            after = client.get("/operator/metrics", headers=headers).json()["durable"]
        self.assertEqual([(r["confirmed"], r["closed_impressions"]) for r in before],
                         [(r["confirmed"], r["closed_impressions"]) for r in after])
        with self.store.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) AS n FROM acknowledgements").fetchone()["n"], 1)
