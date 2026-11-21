"""Stage 1 retrieval, ranking and public API gate evidence."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import uuid4
import unittest

from fastapi.testclient import TestClient

from rankflow.api import create_app, rank_request
from rankflow.features import FEATURE_NAMES, build_features
from rankflow.generation import Generation
from rankflow.retrieval import RetrievalConfig, Snapshot, retrieve
from rankflow.strategies import RULE, RankingStrategy
from rankflow.train import compare, training_groups


def event(aid, ts=20, kind="clicks"):
    return {"aid": aid, "ts": ts, "type": kind}


SNAPSHOT = Snapshot("fixture-snapshot", 10, {1: ((2, 5), (4, 2))}, (3, 1, 2, 4),
                    {3: 1, 1: 2, 2: 3, 4: 4})
CONFIG = RetrievalConfig(candidate_cap=4)
MODEL = RankingStrategy("lgbm-v1", "lightgbm", 1, "evaluated", "fixture-model",
                        lambda rows: list(range(len(rows))))
GENERATION = Generation("test-generation", SNAPSHOT, CONFIG, RULE, MODEL, {
    "W1": [], "W2-dev": [{"prefix_id": 0, "window": "W2-dev", "cutoff_ts": 20,
                         "events": [event(1)]}],
})


class RetrievalTests(unittest.TestCase):
    def test_sources_and_determinism(self):
        events = [event(1), event(2, 21)]
        configs = (
            (replace(CONFIG, covisitation=0, popularity=0), [2, 1]),
            (replace(CONFIG, recent=0, popularity=0), [2, 4]),
            (replace(CONFIG, recent=0, covisitation=0), [3, 1, 2, 4]),
        )
        for config, expected in configs:
            self.assertEqual([c.aid for c in retrieve(SNAPSHOT, events, config)], expected)
        tied = retrieve(SNAPSHOT, [event(2), event(1)], configs[0][0])
        self.assertEqual([candidate.aid for candidate in tied], [1, 2])
        actual = retrieve(SNAPSHOT, events, CONFIG)
        self.assertEqual(actual, retrieve(SNAPSHOT, events, CONFIG))
        self.assertEqual(actual[0].provenance()["covisitation"], {"present": True, "rank": 1})

    def test_cold_start(self):
        for events in ([], [event(999)], [event(999), event(998), event(999)]):
            result, decision = rank_request(GENERATION, events, 4, 20)
            self.assertEqual([item["aid"] for item in result["items"]], [3, 1, 2, 4])
            self.assertEqual(decision["unknown_aid_count"], len(events))
            self.assertEqual(decision["scoring_path"], "popularity")
        result, decision = rank_request(GENERATION, [event(4)], 4, 20)
        self.assertEqual(len(result["items"]), 4)
        self.assertEqual(decision["unknown_aid_count"], 0)
        self.assertTrue(result["items"][0]["sources"]["recent"]["present"])

    def test_train_serve_feature_parity_and_r6(self):
        events = [event(1, kind="carts")]
        fixture = [({"prefix_events": events, "positive_aid": aid}, []) for aid in (2, 999)]
        fitted = list(training_groups(fixture, SNAPSHOT, CONFIG))
        self.assertEqual(len(fitted), 1)
        rows, labels, counts = fitted[0]
        self.assertEqual(counts, {"queries": 2, "no_label": 0, "all_negative": 1, "eligible": 1})
        self.assertEqual(sum(labels), 1)
        self.assertEqual(len(rows), len(labels))
        repeated = list(training_groups(fixture + fixture[:1], SNAPSHOT, CONFIG))
        self.assertEqual([len(target) for _, target, _ in repeated], [4, 4])
        seen = []
        model = replace(MODEL, score=lambda matrix: seen.extend(matrix) or [0] * len(matrix))
        rank_request(replace(GENERATION, assigned=model), events, 4, 100)
        self.assertEqual(rows, seen)
        self.assertTrue(all(len(row) == len(FEATURE_NAMES) for row in rows))
        paired = compare(fixture, SNAPSHOT, CONFIG, MODEL)
        self.assertEqual(paired["retrieved"], 1)
        self.assertEqual(paired["labeled"], 2)
        self.assertEqual(paired["metrics"]["rule-v1"]["HitRate@20"], .5)

    def test_point_in_time_features(self):
        events = [event(1), event(1, 21, "orders")]
        before = build_features(SNAPSHOT, events[:1], retrieve(SNAPSHOT, events[:1], CONFIG))
        events[1] = event(3, 21, "carts")
        after = build_features(SNAPSHOT, events[:1], retrieve(SNAPSHOT, events[:1], CONFIG))
        self.assertEqual(before, after)
        with self.assertRaisesRegex(ValueError, "strictly precede"):
            build_features(SNAPSHOT, [event(1, 10)], [])

    def test_request_scoped_fallback(self):
        def fail(_):
            raise RuntimeError("injected model failure")
        generation = replace(GENERATION, assigned=replace(MODEL, score=fail))
        for current, budget, reason in (
            (generation, 20, "ml_scoring_error"),
            (replace(generation, assigned=MODEL), 0, "logical_deadline"),
        ):
            result, decision = rank_request(current, [event(1)], 4, budget)
            self.assertEqual(result["assigned_strategy"], "lgbm-v1")
            self.assertEqual(result["served_strategy"], "rule-v1")
            self.assertTrue(result["fallback_used"])
            self.assertEqual(decision["fallback_reason"], reason)


def payload(events=None):
    return {"request_id": str(uuid4()), "session_id": "demo", "events": events or [], "top_k": 2}


class ApiTests(unittest.TestCase):
    def test_contract_replay_and_public_boundary_t13(self):
        with TestClient(create_app(GENERATION)) as client:
            public = client.get("/v1/playground/prefixes?window=W2-dev").json()
            self.assertEqual(public[0]["events"], [event(1)])
            self.assertNotIn("positive_aid", str(public))
            for window in ("W2-gate", "W3"):
                response = client.get("/v1/playground/prefixes", params={"window": window})
                self.assertEqual(response.status_code, 404)
                response = client.post("/v1/playground/rank", json={**payload(), "window": window})
                self.assertEqual(response.status_code, 422)
            request = payload([event(1)])
            replay = client.post("/v1/recommend", json=request).json()
            playground = client.post("/v1/playground/rank", json=request).json()
            for key in ("items", "serving_generation", "retrieval_snapshot_id", "feature_version"):
                self.assertEqual(replay[key], playground[key])
            self.assertEqual(playground["comparison"]["mode"], "ranker-only")
            self.assertEqual(replay["logging_status"], "degraded")
            self.assertIsNone(replay["impression_id"])
            self.assertEqual(client.post("/v1/recommend", json=payload([event(1, 22), event(1, 21)])).status_code, 422)
            self.assertEqual(client.post("/v1/recommend", content=b"x" * 65537).status_code, 413)
            self.assertEqual(client.get("/playground").status_code, 200)
            self.assertEqual(client.post("/v1/recommend", json=request).status_code, 403)


@unittest.skipUnless(os.environ.get("RANKFLOW_TEST_DATABASE_URL"), "Requires PostgreSQL test DSN")
class PostgresGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from psycopg import sql

        from rankflow.store import PostgresStore

        cls.admin = PostgresStore(os.environ["RANKFLOW_TEST_DATABASE_URL"])
        cls.schema = sql.Identifier("stage1_" + uuid4().hex)
        with cls.admin.connect() as conn:
            conn.execute(sql.SQL("CREATE SCHEMA {}").format(cls.schema))

        class TestStore(PostgresStore):
            def connect(self):
                conn = super().connect()
                conn.execute(sql.SQL("SET search_path TO {}").format(cls.schema))
                conn.commit()
                return conn

        cls.store = TestStore(cls.admin.dsn)
        cls.store.initialize()

    @classmethod
    def tearDownClass(cls):
        from psycopg import sql

        with cls.admin.connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(cls.schema))

    def pooled_store(self):
        from psycopg.conninfo import make_conninfo
        from psycopg_pool import ConnectionPool

        from rankflow.store import PostgresStore

        schema = self.schema.as_string()
        store = PostgresStore(make_conninfo(self.admin.dsn, options=f"-c search_path={schema}"),
                              pool_decisions=True)
        store.decision_pool = ConnectionPool(
            store.dsn, kwargs=store.decision_pool.kwargs,
            min_size=1, max_size=1, timeout=0.25, open=False,
        )
        return store

    def test_exhausted_decision_pool_degrades_then_recovers(self):
        store = self.pooled_store()
        with TestClient(create_app(GENERATION, store)) as client:
            with store.decision_pool.connection(timeout=5):
                result = client.post("/v1/recommend", json=payload([event(1)])).json()
                self.assertEqual(result["logging_status"], "degraded")
                self.assertIsNone(result["impression_id"])
            recovered = client.post("/v1/recommend", json=payload([event(1)])).json()
            self.assertEqual(recovered["logging_status"], "persisted")
            self.assertIsNotNone(recovered["impression_id"])

    def test_dead_decision_connection_rolls_back_and_is_replaced(self):
        from unittest.mock import patch

        store = self.pooled_store()
        pool = store.decision_pool
        original_connection = pool.connection

        from contextlib import contextmanager

        @contextmanager
        def disconnect_before_commit():
            with original_connection(timeout=5) as conn:
                yield conn
                with self.store.connect() as other:
                    other.execute("SELECT pg_terminate_backend(%s, 5000)", (conn.info.backend_pid,))

        def counts():
            with self.store.connect() as conn:
                return conn.execute("""
                    SELECT (SELECT count(*) FROM impressions) AS impressions,
                           (SELECT count(*) FROM decisions) AS decisions,
                           (SELECT count(*) FROM outbox) AS outbox
                    """).fetchone()

        with TestClient(create_app(GENERATION, store)) as client:
            before = counts()
            with patch.object(pool, "connection", disconnect_before_commit):
                result = client.post("/v1/recommend", json=payload([event(1)])).json()
            self.assertEqual(result["logging_status"], "degraded")
            self.assertIsNone(result["impression_id"])
            self.assertEqual(counts(), before)
            pool.wait(timeout=5)
            recovered = client.post("/v1/recommend", json=payload([event(1)])).json()
            self.assertEqual(recovered["logging_status"], "persisted")
            self.assertEqual(counts(), {table: count + 1 for table, count in before.items()})

    def test_disconnect_after_commit_t05(self):
        app = create_app(GENERATION, self.store)
        body = json.dumps(payload([event(1)])).encode()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            if message["type"] == "http.response.body":
                raise OSError("simulated disconnect")

        scope = {"type": "http", "method": "POST", "path": "/v1/recommend", "root_path": "",
                 "query_string": b"", "headers": [(b"content-type", b"application/json")],
                 "scheme": "http", "server": ("local", 80), "http_version": "1.1", "state": {}}
        with self.assertRaises(OSError):
            asyncio.run(app(scope, receive, send))
        with self.store.connect() as conn:
            impression_id = scope["state"]["persisted_impression"]
            decision = self.store._decision(conn, impression_id)
            self.assertIsNotNone(decision)
            self.assertEqual(decision["send_state"], "send_failed")
            self.assertIsNone(decision["kind"])
            self.assertIsNotNone(conn.execute("SELECT event_id FROM outbox WHERE impression_id = %s",
                                             (impression_id,)).fetchone())

    def test_feedback_top_k_t06_and_review_loop(self):
        with TestClient(create_app(GENERATION, self.store)) as client:
            result = client.post("/v1/playground/rank", json=payload([event(1)])).json()
            self.assertEqual(result["logging_status"], "persisted")
            impression = result["impression_id"]
            ack = client.post(f"/v1/impressions/{impression}/ack").json()
            self.assertEqual(ack["client_confirmation_state"], "confirmed")
            self.assertEqual(ack["send_state"], "send_completed")
            self.assertIn(4, [candidate.aid for candidate in retrieve(SNAPSHOT, [event(1)], CONFIG)])
            event_data = {"event_id": str(uuid4()), "impression_id": impression, "aid": 4,
                          "action": "click", "source": "demo",
                          "occurred_at": datetime.now(timezone.utc).isoformat()}
            rejected = client.post("/v1/feedback", json=event_data)
            self.assertEqual(rejected.json()["detail"], "not_in_returned_top_k")
            event_data["aid"] = result["items"][0]["aid"]
            saved = client.post("/v1/feedback", json=event_data).json()
            self.assertEqual(saved["source"], "demo")
            self.assertTrue(saved["attributed"])
            self.assertEqual(saved, client.post("/v1/feedback", json=event_data).json())

    def test_atomic_degraded_response_and_persisted_fallback(self):
        def fail(_):
            raise RuntimeError("injected model failure")

        generation = replace(GENERATION, assigned=replace(MODEL, score=fail))
        with TestClient(create_app(generation, self.store)) as client:
            result = client.post("/v1/recommend", json=payload([event(1)])).json()
            with self.store.connect() as conn:
                decision = conn.execute("SELECT payload FROM decisions WHERE impression_id = %s",
                                        (result["impression_id"],)).fetchone()["payload"]
                self.assertEqual(decision["fallback_reason"], "ml_scoring_error")
                self.assertEqual(decision["assigned_strategy"], "lgbm-v1")
                self.assertEqual(decision["served_strategy"], "rule-v1")
                count = conn.execute("SELECT count(*) AS n FROM impressions").fetchone()["n"]
                conn.execute("ALTER TABLE outbox ADD CONSTRAINT injected_failure CHECK (false) NOT VALID")
            try:
                degraded = client.post("/v1/recommend", json=payload([event(1)])).json()
                self.assertEqual(degraded["logging_status"], "degraded")
                self.assertIsNone(degraded["impression_id"])
                self.assertEqual(degraded["items"], result["items"])
                with self.store.connect() as conn:
                    self.assertEqual(conn.execute("SELECT count(*) AS n FROM impressions").fetchone()["n"], count)
            finally:
                with self.store.connect() as conn:
                    conn.execute("ALTER TABLE outbox DROP CONSTRAINT injected_failure")

    def test_delayed_and_duplicate_ack_t15_and_outbox(self):
        identifier = self.store.persist({"serving_generation": "test", "items": []})
        with self.store.connect() as conn:
            conn.execute("UPDATE impressions SET created_at = created_at - %s WHERE id = %s",
                         (timedelta(minutes=6), identifier))
        first = self.store.ack(identifier)
        self.assertEqual(first["client_confirmation_state"], "expired_unconfirmed")
        self.assertEqual(first["acknowledgement_kind"], "late_confirmation")
        self.assertEqual(first["send_state"], "send_unknown")
        self.assertEqual(first, self.store.ack(identifier))
        current = self.store.persist({"serving_generation": "test", "items": []})
        confirmed = self.store.ack(current)
        self.assertEqual(confirmed["client_confirmation_state"], "confirmed")
        self.assertEqual(confirmed["send_state"], "send_unknown")
        self.assertEqual(confirmed, self.store.ack(current))
        self.store.drain()
        with self.store.connect() as conn:
            event_id = conn.execute("SELECT event_id FROM outbox WHERE impression_id = %s",
                                    (identifier,)).fetchone()["event_id"]
            conn.execute("UPDATE outbox SET delivered_at = NULL WHERE event_id = %s", (event_id,))
        self.store.drain()
        with self.store.connect() as conn:
            self.assertEqual(conn.execute("SELECT count(*) AS n FROM delivered_events WHERE event_id = %s",
                                          (event_id,)).fetchone()["n"], 1)


if __name__ == "__main__":
    unittest.main()
