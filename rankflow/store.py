"""Transactional decision capture and idempotent demo attribution."""
from datetime import datetime, timedelta, timezone
import logging
from uuid import uuid4

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .operations import emit
from .security import AUDIT_SCHEMA
from .epoch_registry import SCHEMA as EPOCH_SCHEMA

LOGGER = logging.getLogger(__name__)
ACK_WINDOW = timedelta(minutes=5)
ATTRIBUTION_WINDOW = timedelta(hours=24)

SCHEMA = """
CREATE TABLE IF NOT EXISTS impressions (
    id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    generation TEXT NOT NULL, items JSONB NOT NULL,
    send_state TEXT NOT NULL DEFAULT 'send_unknown'
);
CREATE TABLE IF NOT EXISTS decisions (
    impression_id TEXT PRIMARY KEY REFERENCES impressions(id), payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    event_id TEXT PRIMARY KEY, impression_id TEXT NOT NULL REFERENCES impressions(id),
    payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    delivered_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS delivered_events (
    event_id TEXT PRIMARY KEY, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS shadow_observations (
    impression_id TEXT PRIMARY KEY REFERENCES impressions(id),
    payload JSONB NOT NULL, observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS acknowledgements (
    impression_id TEXT NOT NULL REFERENCES impressions(id),
    kind TEXT NOT NULL, acknowledged_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (impression_id, kind)
);
CREATE UNIQUE INDEX IF NOT EXISTS acknowledgements_kind_key
    ON acknowledgements (impression_id, kind);
CREATE TABLE IF NOT EXISTS feedback_events (
    event_id TEXT PRIMARY KEY, impression_id TEXT NOT NULL REFERENCES impressions(id),
    occurred_at TIMESTAMPTZ NOT NULL, ingested_at TIMESTAMPTZ NOT NULL, payload JSONB NOT NULL
);
"""


class PostgresStore:
    def __init__(self, dsn, ack_window=ACK_WINDOW, attribution_window=ATTRIBUTION_WINDOW,
                 *, pool_decisions=False):
        self.dsn = dsn
        options = conninfo_to_dict(dsn).get("options", "")
        self.options = f"{options} -c statement_timeout=2000 -c lock_timeout=1500"
        self.ack_window = ack_window
        self.attribution_window = attribution_window
        self.decision_pool = ConnectionPool(
            self.dsn, kwargs={"connect_timeout": 2, "row_factory": dict_row, "options": self.options},
            min_size=4, max_size=12, timeout=2, max_waiting=40, open=False,
        ) if pool_decisions else None

    def connect(self):
        return psycopg.connect(self.dsn, connect_timeout=2, row_factory=dict_row,
                               options=self.options)

    def initialize(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(621024)")
            conn.execute(SCHEMA)
            conn.execute(EPOCH_SCHEMA)
            conn.execute(AUDIT_SCHEMA)
            conn.execute("""
                DO $$ BEGIN
                    IF EXISTS (SELECT 1 FROM pg_constraint
                               WHERE conrelid = 'acknowledgements'::regclass
                               AND contype = 'p' AND cardinality(conkey) = 1) THEN
                        ALTER TABLE acknowledgements DROP CONSTRAINT acknowledgements_pkey;
                    END IF;
                END $$;
                """)

    def ready(self):
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1 FROM impressions LIMIT 1")
        except psycopg.Error:
            return False
        return True

    def persist(self, decision):
        impression_id = str(uuid4())
        event_id = str(uuid4())
        payload = dict(decision, impression_id=impression_id, logging_status="persisted")
        event = {"event_id": event_id, "type": "recommendation_generated", **payload}
        transaction = self.decision_pool.connection() if self.decision_pool else self.connect()
        with transaction as conn:
            conn.execute("""
                WITH impression AS (
                    INSERT INTO impressions(id, generation, items) VALUES (%s, %s, %s)
                    RETURNING id
                ), saved_decision AS (
                    INSERT INTO decisions(impression_id, payload)
                    SELECT id, %s FROM impression
                    RETURNING impression_id
                )
                INSERT INTO outbox(event_id, impression_id, payload)
                SELECT %s, impression_id, %s FROM saved_decision
                """, (impression_id, decision["serving_generation"], Jsonb(decision["items"]),
                      Jsonb(payload), event_id, Jsonb(event)))
        emit("decision_committed", request_id=decision.get("request_id"), impression_id=impression_id,
             event_id=event_id)
        return impression_id

    def record_shadow(self, impression_id, observation):
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO shadow_observations(impression_id, payload) VALUES (%s, %s) "
                "ON CONFLICT DO NOTHING", (impression_id, Jsonb(observation)))

    def record_send(self, impression_id, state):
        with self.connect() as conn:
            conn.execute("UPDATE impressions SET send_state = %s WHERE id = %s AND send_state = 'send_unknown'",
                         (state, impression_id))

    def _decision(self, conn, impression_id):
        return conn.execute(
            """SELECT i.*, a.kind, a.acknowledged_at FROM impressions i
               JOIN decisions d ON d.impression_id = i.id
               LEFT JOIN LATERAL (
                   SELECT kind, acknowledged_at FROM acknowledgements
                   WHERE impression_id = i.id ORDER BY acknowledged_at, kind LIMIT 1
               ) a ON true
               WHERE i.id = %s""", (impression_id,)
        ).fetchone()

    def _confirmation(self, decision, now):
        if decision["kind"] == "confirmed":
            return "confirmed"
        return "expired_unconfirmed" if now >= decision["created_at"] + self.ack_window else "pending"

    def ack(self, impression_id):
        with self.connect() as conn:
            decision = self._decision(conn, impression_id)
            if decision is None:
                return None
            now = datetime.now(timezone.utc)
            kind = "late_confirmation" if now >= decision["created_at"] + self.ack_window else "confirmed"
            conn.execute("""INSERT INTO acknowledgements VALUES (%s, %s, %s)
                            ON CONFLICT (impression_id, kind) DO NOTHING""", (impression_id, kind, now))
            decision = self._decision(conn, impression_id)
            return {"impression_id": impression_id, "send_state": decision["send_state"],
                    "client_confirmation_state": self._confirmation(decision, now),
                    "acknowledgement_kind": decision["kind"], "acknowledged_at": decision["acknowledged_at"]}

    def feedback(self, event):
        with self.connect() as conn:
            existing = conn.execute("SELECT payload FROM feedback_events WHERE event_id = %s",
                                    (event["event_id"],)).fetchone()
            if existing:
                return self._replay_feedback(existing["payload"], event)
            decision = self._decision(conn, event["impression_id"])
            if decision is None:
                return {"attributed": False, "reason": "logging_degraded_no_decision"}
            item = next((item for item in decision["items"] if item["aid"] == event["aid"]), None)
            if item is None:
                return {"attributed": False, "reason": "not_in_returned_top_k"}
            now = datetime.now(timezone.utc)
            occurred = datetime.fromisoformat(event["occurred_at"])
            if (occurred < decision["created_at"] or occurred > now + timedelta(minutes=1)
                    or now > decision["created_at"] + self.attribution_window):
                return {"attributed": False, "reason": "outside_attribution_window"}
            result = {**event, "source": "demo", "attributed": True, "reason": "attributed",
                      "rank": item["rank"], "serving_generation": decision["generation"],
                      "confirmation_state": self._confirmation(decision, now), "ingested_at": now.isoformat()}
            inserted = conn.execute(
                """INSERT INTO feedback_events VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (event_id) DO NOTHING RETURNING event_id""",
                (event["event_id"], event["impression_id"], occurred, now, Jsonb(result)),
            ).fetchone()
            if not inserted:
                existing = conn.execute("SELECT payload FROM feedback_events WHERE event_id = %s",
                                        (event["event_id"],)).fetchone()
                return self._replay_feedback(existing["payload"], event)
            return result

    @staticmethod
    def _replay_feedback(saved, event):
        if any(saved[key] != value for key, value in event.items()):
            return {"attributed": False, "reason": "event_id_conflict"}
        return saved

    def drain(self, limit=100):
        """Deliver to the local event sink in the same transaction as marking delivery."""
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT event_id, payload FROM outbox WHERE delivered_at IS NULL
                   ORDER BY created_at, event_id LIMIT %s FOR UPDATE SKIP LOCKED""", (limit,)
            ).fetchall()
            for row in rows:
                conn.execute("INSERT INTO delivered_events VALUES (%s, %s) ON CONFLICT DO NOTHING",
                             (row["event_id"], Jsonb(row["payload"])))
                conn.execute("UPDATE outbox SET delivered_at = clock_timestamp() WHERE event_id = %s",
                             (row["event_id"],))
        for row in rows:
            emit("outbox_delivered", request_id=row["payload"].get("request_id"), event_id=row["event_id"])
        return len(rows)
