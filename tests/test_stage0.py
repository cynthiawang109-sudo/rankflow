import copy
from dataclasses import replace
import gzip
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from rankflow.data.epoch import EvaluationEpoch, validate_epoch
from rankflow.data.fetch import ARCHIVE, DATASET, fetch
from rankflow.data.ingestion import file_hash, load_sessions, read_rows, sample_ids, write_row
from rankflow.data.pipeline import (
    FIXTURE, build_run, read_config, read_json, replay_queries, session_events,
)
from rankflow.data.retrieval import DiskBudgetExceeded, candidate_inputs


class Stage0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.config = read_config(Path("configs/stage0.yaml"))
        cls.run_path = cls.root / "baseline"
        cls.manifest, cls.retrieval, _ = build_run(FIXTURE, cls.run_path, cls.config)
        cls.sessions = list(session_events(cls.run_path / "sessions.jsonl"))
        cls.queries = list(read_rows(cls.run_path / "queries.jsonl"))
        record = read_json(cls.run_path / "evaluation_epoch.json")
        del record["source"]
        cls.epoch = EvaluationEpoch(**record)

    def test_t09_tied_cutoffs_and_order(self):
        queries = [query for query in self.queries if query["query_id"][0] == 5]
        tied = queries[:3]
        self.assertEqual([query["cutoff_ts"] for query in tied], [210, 210, 210])
        self.assertEqual([query["query_id"] for query in tied], [[5, 0], [5, 1], [5, 2]])
        self.assertEqual([event["aid"] for event in tied[-1]["prefix_events"]], [1, 2, 3])
        self.assertEqual((tied[0]["positive_aid"], tied[0]["label_event_index"],
                          tied[0]["label_event_ts"]), (3, 2, 210))
        self.assertIsNone(queries[-1]["positive_aid"])

    def test_t17_rejects_invalid_registration(self):
        windows = self.manifest["windows"]
        members = self.manifest["memberships"]

        def validate(epoch=self.epoch, ranges=windows, membership=members, queries=self.queries):
            validate_epoch(epoch, ranges, membership, iter(self.sessions), iter(queries))

        validate()
        for label_ts in (windows["W2"][0], windows["W3"][0]):
            with self.subTest(label_ts=label_ts):
                bad_queries = copy.deepcopy(self.queries)
                bad_queries[0]["label_event_ts"] = label_ts
                with self.assertRaisesRegex(ValueError, "W1 label event time"):
                    validate(queries=bad_queries)
        for watermark in (210, 310, 311):
            with self.subTest(watermark=watermark):
                with self.assertRaisesRegex(ValueError, "snapshot watermark must be strictly before"):
                    validate(epoch=replace(self.epoch, history_statistics_watermark=watermark))
        with self.assertRaisesRegex(ValueError, "disjoint, ordered"):
            validate(ranges={**windows, "W3": [399, 500]})
        with self.assertRaisesRegex(ValueError, "pairwise disjoint"):
            validate(membership={**members, "W2-gate": members["W2-dev"]})
        with self.assertRaisesRegex(ValueError, "window-crossing session"):
            validate(membership={**members, "W0": [*members["W0"], 6]})
        bad_queries = copy.deepcopy(self.queries)
        bad_queries[0].update(positive_aid=999, label_event_index=3, label_event_ts=211)
        with self.assertRaisesRegex(ValueError, "first click strictly after"):
            validate(queries=bad_queries)

    def test_t18_exact_pairs(self):
        # Session 1 contributes (1,2), (1,3), (2,3) once each despite
        # repeats and reverse order. Session 4 adds one more (1,2).
        # Session 2 has 4..6 exactly 20 positions apart and 4..7 at 21.
        # The only distinct item in session 3 is beyond the cap.
        expected = {(1, 2): 2, (1, 3): 1, (2, 3): 1, (4, 5): 1,
                    (4, 6): 1, (5, 6): 1, (5, 7): 1, (6, 7): 1}
        directed = {**expected, **{(b, a): count for (a, b), count in expected.items()}}
        rows = list(read_rows(self.run_path / "covisitation.jsonl"))
        self.assertEqual(len(rows), len(directed))
        self.assertEqual({(row["aid"], row["neighbour_aid"]): row["count"] for row in rows}, directed)

    def test_future_mutation(self):
        original = self.queries[0]
        self.assertEqual(original["query_id"], [5, 0])
        source = self.root / "mutated.jsonl"
        with source.open("w", encoding="utf-8") as stream:
            for row in read_rows(FIXTURE):
                if row["session"] == 5:
                    # Modify a future event with a timestamp tied with the cutoff.
                    row["events"][2]["aid"] = 888
                    row["events"].append({"aid": 777, "ts": 212, "type": "clicks"})
                if row["session"] == 8:
                    row["events"][0]["aid"] = 444
                write_row(stream, row)
        mutated_path = self.root / "mutated"
        build_run(source, mutated_path, self.config)
        mutated = next(read_rows(mutated_path / "queries.jsonl"))

        def inputs(query, directory):
            table = list(read_rows(directory / "covisitation.jsonl"))
            return candidate_inputs(query, lambda aid: (
                row["neighbour_aid"] for row in table if row["aid"] == aid
            ), self.config["retrieval"]["candidate_cap"])

        self.assertNotEqual(original["positive_aid"], mutated["positive_aid"])
        for field in ("query_id", "cutoff_ts", "prefix_events", "retrieval_snapshot_id"):
            self.assertEqual(original[field], mutated[field])
        self.assertEqual(inputs(original, self.run_path), inputs(mutated, mutated_path))

    def test_leakage_and_crossing_accounting(self):
        history = list(session_events(self.run_path / "history.jsonl"))
        watermark = max(event["ts"] for _, events in history for event in events)
        self.assertEqual(watermark, self.epoch.history_statistics_watermark)
        for query in self.queries:
            self.assertLess(watermark, query["cutoff_ts"])
            self.assertEqual(query["retrieval_snapshot_id"], self.epoch.retrieval_snapshot_id)
        self.assertEqual(self.manifest["crossing_exclusions_by_length"], {
            "short": {"events": 5, "sessions": 2}, "long": {"events": 22, "sessions": 1},
        })
        self.assertTrue({6, 7, 9}.isdisjoint(
            session for group in self.manifest["memberships"].values() for session in group
        ))

    def test_determinism_and_replay(self):
        second = self.root / "second"
        manifest, _, _ = build_run(FIXTURE, second, self.config)
        for name in ("queries.jsonl", "covisitation.jsonl"):
            self.assertEqual(manifest["artifacts"][name], self.manifest["artifacts"][name])
        for name, digest in self.manifest["artifacts"].items():
            self.assertEqual(file_hash(self.run_path / name), digest)
        replay = self.root / "replayed.jsonl"
        replay_queries(self.run_path, replay, self.config)
        self.assertEqual(replay.read_bytes(), (self.run_path / "queries.jsonl").read_bytes())
        self.assertEqual(self.epoch.dataset_manifest_hash,
                         file_hash(self.run_path / "data_manifest.json"))
        self.assertEqual(self.epoch.query_manifest_hash, file_hash(replay))

    def test_sampler_and_ingestion_order(self):
        rows = list(read_rows(FIXTURE))
        reversed_path = self.root / "reversed.jsonl"
        with reversed_path.open("w", encoding="utf-8") as stream:
            for row in reversed(rows):
                if row["session"] == 5:
                    row["events"].insert(0, row["events"].pop())
                write_row(stream, row)
        settings = {"seed": self.config["sampler"]["seed"], "cap": 8}
        ids = sample_ids(FIXTURE, **settings)
        self.assertEqual(len(ids), 8)
        self.assertEqual(ids, sample_ids(reversed_path, **settings))
        events = dict(load_sessions(reversed_path))[5]
        self.assertEqual([event["aid"] for event in events], [1, 2, 3, 999])
        self.assertEqual([event["event_index"] for event in events], [0, 1, 2, 3])

    def test_top_n_and_minimum_count(self):
        config = copy.deepcopy(self.config)
        config["retrieval"].update(top_n_per_item=1)
        pruned = self.root / "pruned"
        _, snapshot, _ = build_run(FIXTURE, pruned, config)
        table = {row["aid"]: row["neighbour_aid"] for row in read_rows(pruned / "covisitation.jsonl")}
        self.assertEqual(table, {1: 2, 2: 1, 3: 1, 4: 5, 5: 4, 6: 4, 7: 5})
        self.assertLessEqual(snapshot["row_count"], snapshot["distinct_items"])
        config["retrieval"]["min_count"] = 2
        filtered = self.root / "filtered"
        build_run(FIXTURE, filtered, config)
        self.assertEqual([(row["aid"], row["neighbour_aid"], row["count"])
                          for row in read_rows(filtered / "covisitation.jsonl")],
                         [(1, 2, 2), (2, 1, 2)])

    def test_disk_budget_aborts_without_partial_table(self):
        for budget in (1, 4096, self.retrieval["staging_disk_bytes"]):
            with self.subTest(budget=budget):
                output = self.root / f"budget-{budget}"
                config = copy.deepcopy(self.config)
                config["retrieval"]["disk_budget_bytes"] = budget
                with self.assertRaisesRegex(DiskBudgetExceeded, "disk budget"):
                    build_run(FIXTURE, output, config)
                self.assertEqual([path.name for path in output.iterdir()], ["disk_budget_abort.json"])
                self.assertEqual(read_json(output / "disk_budget_abort.json")["status"], "aborted")

    def test_fixture_cannot_be_used_as_otto(self):
        with self.assertRaisesRegex(ValueError, "verified train.jsonl"):
            build_run(FIXTURE, self.root / "otto", self.config, "otto")


class FetchTests(unittest.TestCase):
    def test_fetch_command_and_hashes(self):
        fixture = FIXTURE.read_bytes()

        def fake_download(command, *, check):
            self.assertTrue(check)
            self.assertEqual(command[:-1], ["kaggle", "datasets", "download", "-d", DATASET, "-p"])
            with ZipFile(Path(command[-1]) / ARCHIVE, "w") as archive:
                archive.writestr("nested/train.jsonl.gz", gzip.compress(fixture))
                archive.writestr("test.jsonl", fixture)

        with TemporaryDirectory() as temp:
            output = Path(temp) / "mock-download"
            with patch("rankflow.data.fetch.subprocess.run", side_effect=fake_download):
                fetch(output)
            manifest = read_json(output / "download_manifest.json")
            self.assertEqual(manifest["archive_sha256"], file_hash(output / ARCHIVE))
            for name in ("train.jsonl", "test.jsonl"):
                self.assertEqual((output / name).read_bytes(), fixture)
                self.assertEqual(manifest["files"][name], file_hash(output / name))
            with self.assertRaises(FileExistsError):
                fetch(output)

    def test_failed_download_does_not_publish(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "failed"
            with patch("rankflow.data.fetch.subprocess.run",
                       side_effect=subprocess.CalledProcessError(1, "kaggle")):
                with self.assertRaises(subprocess.CalledProcessError):
                    fetch(output)
            self.assertFalse(output.exists())
