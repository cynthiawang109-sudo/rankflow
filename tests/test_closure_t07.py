"""Incompatible offline replay must leave the active stable release alone."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import patch

from fastapi.testclient import TestClient

from rankflow.api import create_app
from rankflow.data.ingestion import file_hash
from rankflow.features import FEATURE_NAMES
from rankflow.generation import FILES, Generation, encoded, identity
from rankflow.shadow_replay import replay_bundles
from tests import test_stage2 as baseline
from tests.test_stage1 import event, payload


@skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class ReplayIsolation(TestCase):
    setUp = baseline.PlatformTests.setUp

    def test_incompatible_replay_preserves_stable_serving_and_results(self):
        archive = os.environ.get("RANKFLOW_T07_STABLE")
        with TemporaryDirectory() as directory:
            root = Path(directory)
            results = root / "results"
            results.mkdir()
            other = results / "other-generation.json"
            other.write_bytes(b'{"evaluated":true}')
            if archive:
                stable_path = Path(archive).resolve()
                stable = Generation.load(stable_path)
                manifest = json.loads((stable_path / "manifest.json").read_bytes())
                dataset = Path("artifacts/stage0-otto")
                events = stable.examples["W2-dev"][0]["events"]
                other_artifacts = [path for peer in stable_path.parent.glob("gen-*")
                                   if peer != stable_path for path in peer.iterdir() if path.is_file()]
                other_artifacts.extend(stable_path.parents[1].glob("training/*-verified/run.json"))
            else:
                stable = baseline.STABLE
                stable_path = root / stable.generation_id
                stable_path.mkdir()
                dataset = root
                other_artifacts = []
                events = [event(1)]
                for filename in FILES:
                    (stable_path / filename).write_bytes(b"synthetic artifact")
                manifest = {"version": "serving-generation-v1",
                            "checksums": {name: file_hash(stable_path / name) for name in FILES}}
            manifest["compatibility"] = {
                "feature_schema": "session-features-incompatible-t07-v1",
                "feature_names": [*FEATURE_NAMES, "t07_extra_column"],
                "feature_code_sha256": "0" * 64,
                "mode": "ranker-only",
            }
            rejected_id = identity(manifest)
            candidate = root / rejected_id
            shutil.copytree(stable_path, candidate)
            (candidate / "manifest.json").write_bytes(encoded(manifest))
            output = results / f"{rejected_id}.json"

            def hashes():
                return {path: file_hash(path) for path in (*stable_path.iterdir(), *candidate.iterdir(),
                                                          other, *other_artifacts)
                        if path.is_file()}

            def stored_results():
                with self.store.connect() as conn:
                    return {table: conn.execute(f"SELECT * FROM {table}").fetchall()
                            for table in ("impressions", "decisions", "outbox", "shadow_observations")}

            before_hashes = hashes()
            entered, continue_attempt = Event(), Event()
            load = Generation.load

            def block_candidate(path):
                if path == stable_path:
                    return stable
                entered.set()
                if not continue_attempt.wait(20):
                    raise RuntimeError("Replay test did not release the blocked loader")
                return load(path)

            with TestClient(create_app(stable, self.store, baseline.SECRET, deadline_ms=2000)) as client:
                def recommend():
                    response = client.post("/v1/recommend", json=payload(events))
                    response.raise_for_status()
                    return response.json()

                before = recommend()
                saved = stored_results()
                with ThreadPoolExecutor(max_workers=1) as worker:
                    with (patch("rankflow.shadow_replay.Generation.load", side_effect=block_candidate),
                          patch("rankflow.shadow_replay.replay") as evaluate):
                        attempt = worker.submit(replay_bundles, dataset, stable_path, candidate, output, 1)
                        try:
                            self.assertTrue(entered.wait(20))
                            during = recommend()
                        finally:
                            continue_attempt.set()
                        with self.assertRaisesRegex(ValueError, "Serving feature compatibility mismatch"):
                            attempt.result(timeout=90)
                        evaluate.assert_not_called()
                after = recommend()
                current = stored_results()

            for response in (before, during, after):
                self.assertEqual(response["serving_generation"], stable.generation_id)
                self.assertEqual(response["served_strategy"], "rule-v1")
                self.assertEqual(response["logging_status"], "persisted")
                self.assertEqual(response["items"], before["items"])
                self.assertFalse(response["fallback_used"])
            self.assertEqual(len({row["impression_id"] for row in (before, during, after)}), 3)
            self.assertCountEqual([row["generation"] for row in current["impressions"]],
                                  [stable.generation_id] * 3)
            for table in ("decisions", "outbox"):
                self.assertEqual(len(current[table]), 3)
                self.assertEqual({row["impression_id"] for row in current[table]},
                                 {row["impression_id"] for row in (before, during, after)})
                self.assertEqual({row["payload"]["serving_generation"] for row in current[table]},
                                 {stable.generation_id})
                for field in ("assigned_strategy", "served_strategy"):
                    self.assertEqual({row["payload"][field] for row in current[table]}, {"rule-v1"})
            self.assertEqual(current["shadow_observations"], [])
            for table in ("impressions", "decisions"):
                self.assertTrue(all(row in current[table] for row in saved[table]))
            self.assertEqual(hashes(), before_hashes)
            audit_path = output.with_name(output.name + ".rejected.json")
            self.assertCountEqual(results.iterdir(), [other, audit_path])
            audit = json.loads(audit_path.read_bytes())
            self.assertEqual(audit["reason"], "Serving feature compatibility mismatch")
            self.assertEqual(audit["status"], "rejected")
            self.assertEqual(audit["challenger_generation"], rejected_id)
            self.assertEqual(audit["stable_generation"], stable.generation_id)
            if archive:
                print(json.dumps({"audit": audit, "impressions": [
                    response["impression_id"] for response in (before, during, after)
                ], "items": before["items"]}, sort_keys=True))
