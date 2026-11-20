"""Immutable traffic configuration snapshots and audited compare-and-swap."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from threading import Lock
from time import monotonic
from uuid import uuid4
import logging

from .operations import emit

import psycopg
from psycopg.types.json import Jsonb

from .generation import Generation, encoded

LOGGER = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_configs (
    config_id TEXT PRIMARY KEY, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS traffic_rescue (
    singleton BOOLEAN PRIMARY KEY CHECK (singleton),
    config_id TEXT NOT NULL REFERENCES traffic_configs(config_id)
);
CREATE TABLE IF NOT EXISTS traffic_pointer (
    singleton BOOLEAN PRIMARY KEY CHECK (singleton),
    config_id TEXT NOT NULL REFERENCES traffic_configs(config_id), revision BIGINT NOT NULL
);
CREATE TABLE IF NOT EXISTS traffic_instances (
    instance_id TEXT PRIMARY KEY, revision BIGINT NOT NULL, config_id TEXT NOT NULL,
    prepared JSONB NOT NULL, last_seen TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS traffic_preloads (
    config_id TEXT PRIMARY KEY REFERENCES traffic_configs(config_id)
);
CREATE TABLE IF NOT EXISTS traffic_audit (
    operation_id TEXT PRIMARY KEY, action TEXT NOT NULL, config_id TEXT NOT NULL,
    revision BIGINT NOT NULL, actor TEXT NOT NULL, recorded_at TIMESTAMPTZ DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS traffic_tracking (
    revision BIGINT PRIMARY KEY, expected_instances JSONB NOT NULL, recovery_config_id TEXT,
    state TEXT NOT NULL DEFAULT 'pointer_committed'
);
CREATE TABLE IF NOT EXISTS traffic_overrides (
    revision BIGINT PRIMARY KEY, reason TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL, duration_seconds INTEGER
);
ALTER TABLE traffic_overrides ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;
CREATE TABLE IF NOT EXISTS traffic_incident (
    singleton BOOLEAN PRIMARY KEY CHECK (singleton),
    reason TEXT NOT NULL, opened_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
"""

TRANSITIONS = {
    "draft": {"shadowing", "killed"},
    "shadowing": {"canary", "killed"},
    "canary": {"promoted", "rolled_back", "killed"},
    "promoted": {"rolled_back", "killed"},
    "rolled_back": set(),
    "killed": set(),
}


@dataclass(frozen=True)
class TrafficConfigSnapshot:
    stable_generation_id: str
    experiment_id: str = "alpha"
    canary_generation_id: str | None = None
    canary_percent: int = 0
    shadow_generation_id: str | None = None
    shadow_mode: str | None = None
    routing_salt_id: str = "v1"
    guardrail_policy_version: str = "stage2-v1"
    state: str = "draft"
    guardrail_mode: str = "synthetic_operational"

    def __post_init__(self):
        if self.guardrail_mode != "synthetic_operational":
            raise ValueError("Only synthetic operational guardrails are available")
        if not 0 <= self.canary_percent <= 100 or self.state not in TRANSITIONS:
            raise ValueError("Invalid experiment state or canary percentage")
        if self.canary_percent and (self.state != "canary" or not self.canary_generation_id):
            raise ValueError("Canary traffic requires a canary generation and state")
        if self.state == "canary" and not self.canary_percent:
            raise ValueError("Canary state requires a positive percentage")
        if bool(self.shadow_generation_id) != (self.shadow_mode == "live"):
            raise ValueError("Live shadow requires a shadow generation")
        if self.state in {"killed", "rolled_back"} and (self.canary_generation_id or self.shadow_generation_id):
            raise ValueError("Terminal safety configurations must be stable-only")

    @property
    def config_id(self):
        payload = asdict(self)
        del payload["guardrail_mode"]
        return "cfg-" + hashlib.sha256(encoded(payload)).hexdigest()

    def cohort(self, session_hash, salt):
        digest = hmac.digest(salt, encoded([self.experiment_id, self.routing_salt_id, session_hash]), "sha256")
        threshold = (1 << 64) * self.canary_percent // 100
        return "canary" if int.from_bytes(digest[:8], "big") < threshold else "stable"


@dataclass(frozen=True)
class TrafficPin:
    config: TrafficConfigSnapshot
    revision: int
    stable: Generation
    canary: Generation | None
    shadow: Generation | None
    salt: bytes
    degraded: bool = False

    def select(self, session_hash):
        cohort = self.config.cohort(session_hash, self.salt)
        return (self.canary if cohort == "canary" else self.stable), cohort


class TrafficRegistry:
    def __init__(self, store, generation_root, rescue, salts, poll_seconds=1,
                 promotion_allowed=None, convergence_seconds=10, minimum_capacity=1):
        if rescue.canary_generation_id or rescue.shadow_generation_id:
            raise ValueError("Rescue configuration must be stable-only")
        self.store = store
        self.generation_root = generation_root
        self.salts = salts
        self.poll_seconds = poll_seconds
        self.promotion_allowed = promotion_allowed
        self.convergence_seconds = convergence_seconds
        self.minimum_capacity = minimum_capacity
        self.instance_id = uuid4().hex
        self.lock = Lock()
        self.generations = {}
        self.rescue = self.load(rescue, -1, degraded=True)
        self.active = (self.rescue, 0.0, True)

    def generation(self, identifier):
        if len(identifier) != 68 or not identifier.startswith("gen-") or any(
            character not in "0123456789abcdef" for character in identifier[4:]
        ):
            raise ValueError("Invalid generation ID")
        if identifier not in self.generations:
            self.generations[identifier] = Generation.load(self.generation_root / identifier)
        return self.generations[identifier]

    def load(self, config, revision, degraded=False):
        return TrafficPin(config, revision, self.generation(config.stable_generation_id),
                          self.generation(config.canary_generation_id) if config.canary_generation_id else None,
                          self.generation(config.shadow_generation_id) if config.shadow_generation_id else None,
                          self.salts[config.routing_salt_id], degraded)

    def initialize(self):
        with self.store.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(621025)")
            conn.execute(SCHEMA)
            rescue = self.rescue.config
            conn.execute("INSERT INTO traffic_configs VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (rescue.config_id, Jsonb(asdict(rescue))))
            conn.execute("INSERT INTO traffic_rescue VALUES (true, %s) ON CONFLICT DO NOTHING",
                         (rescue.config_id,))
            designated = conn.execute("SELECT config_id FROM traffic_rescue").fetchone()
            if designated["config_id"] != rescue.config_id:
                raise ValueError("Configured rescue differs from the globally provisioned config")
            conn.execute("INSERT INTO traffic_pointer VALUES (true, %s, 0) ON CONFLICT DO NOTHING",
                         (rescue.config_id,))

    def pin(self):
        pin, expires_at, _ = self.active
        return pin if monotonic() < expires_at else self.rescue

    def serving_pin(self):
        pin, expires_at, compatible = self.active
        if not compatible:
            return None
        return pin if monotonic() < expires_at else self.rescue

    def readiness(self):
        pin = self.serving_pin()
        try:
            with self.store.connect() as conn:
                target = conn.execute("SELECT config_id, revision FROM traffic_pointer").fetchone()
        except psycopg.Error:
            target = None
        current = bool(pin and target and pin.revision == target["revision"]
                       and pin.config.config_id == target["config_id"])
        return {"instance_id": self.instance_id,
                "serving_ready": bool(pin and (current or target is None)),
                "release_ready": bool(current and not pin.degraded),
                "config_id": pin.config.config_id if pin else None,
                "config_revision": pin.revision if pin else None,
                "target_config_id": target["config_id"] if target else None,
                "target_revision": target["revision"] if target else None}

    def refresh(self):
        with self.lock:
            compatible = True
            try:
                with self.store.connect() as conn:
                    row = conn.execute("""
                        SELECT p.config_id, p.revision, c.payload FROM traffic_pointer p
                        JOIN traffic_configs c USING (config_id)
                        """).fetchone()
                    config = TrafficConfigSnapshot(**row["payload"])
                    if row["config_id"] != config.config_id:
                        raise ValueError("Traffic configuration checksum mismatch")
                    frozen = conn.execute("SELECT 1 FROM traffic_incident").fetchone()
                    pin = self.load(config, row["revision"], degraded=bool(frozen))
                    prepared = []
                    for item in conn.execute("""
                        SELECT config_id, payload FROM traffic_preloads JOIN traffic_configs USING (config_id)
                        """).fetchall():
                        try:
                            target = TrafficConfigSnapshot(**item["payload"])
                            if target.config_id != item["config_id"]:
                                raise ValueError("Preload identity mismatch")
                            self.load(target, -1)
                            prepared.append(target.config_id)
                        except (OSError, ValueError, KeyError):
                            LOGGER.warning("Traffic preload failed for %s", item["config_id"])
                    conn.execute("""
                        INSERT INTO traffic_instances(instance_id, revision, config_id, prepared)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT(instance_id) DO UPDATE SET revision = excluded.revision,
                            config_id = excluded.config_id, prepared = excluded.prepared,
                            last_seen = clock_timestamp()
                        """, (self.instance_id, pin.revision, config.config_id, Jsonb(prepared)))
            except psycopg.Error:
                LOGGER.exception("Traffic control refresh failed, using designated rescue")
                pin = self.rescue
            except Exception:
                LOGGER.exception("Active traffic configuration unavailable")
                pin, compatible = self.rescue, False
            self.active = (pin, monotonic() + 3 * self.poll_seconds, compatible)

    def observe_convergence(self):
        with self.store.connect() as conn:
            active = conn.execute("""
                SELECT p.revision, p.config_id, a.action, a.recorded_at, t.expected_instances,
                       t.recovery_config_id, t.state, clock_timestamp() AS now
                FROM traffic_pointer p JOIN traffic_tracking t USING (revision)
                JOIN traffic_audit a USING (revision)
                """).fetchone()
            if active is None or active["state"] == "converged":
                return
            revision = active["revision"]
            eligible = conn.execute("""
                SELECT instance_id, revision
                FROM traffic_instances
                WHERE last_seen > clock_timestamp() - %s * interval '1 second'
                """, (3 * self.poll_seconds,)).fetchall()
            acknowledged = {row["instance_id"] for row in eligible if row["revision"] == revision}
            required = set(active["expected_instances"]) | {row["instance_id"] for row in eligible}
            if required and required <= acknowledged:
                conn.execute("UPDATE traffic_tracking SET state='converged' WHERE revision=%s", (revision,))
                return
            if active["now"] < active["recorded_at"] + timedelta(seconds=self.convergence_seconds):
                return
            result = conn.execute("""
                UPDATE traffic_tracking SET state='partially_converged'
                WHERE revision=%s AND state<>'partially_converged'
                """, (revision,))
            if result.rowcount:
                emit("fleet_stale", logging.WARNING, revision=revision,
                     missing_instances=sorted(required - acknowledged),
                     rollback_config_id=active["recovery_config_id"])
        action = active["action"]
        try:
            if action == "rollback":
                self.publish(self.rescue.config, revision, f"rescue-{revision}", "convergence", "rescue")
            elif action == "publish" and len(acknowledged) < self.minimum_capacity and active["recovery_config_id"]:
                self.publish(active["recovery_config_id"], revision, f"capacity-{revision}", "convergence", "rollback")
        except ValueError:
            LOGGER.info("Traffic recovery operation lost its expected revision")

    def prepare(self, target):
        with self.lock, self.store.connect() as conn:
            self.load(target, -1)
            conn.execute("INSERT INTO traffic_configs VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (target.config_id, Jsonb(asdict(target))))
            conn.execute("INSERT INTO traffic_preloads VALUES (%s) ON CONFLICT DO NOTHING",
                         (target.config_id,))
        return target.config_id

    def fleet(self):
        with self.store.connect() as conn:
            return conn.execute("""
                SELECT *, last_seen > clock_timestamp() - %s * interval '1 second' AS leased
                FROM traffic_instances ORDER BY instance_id
                """, (3 * self.poll_seconds,)).fetchall()

    def publish(self, target, expected_revision, operation_id, actor, action="publish", *,
                reason=None, override_seconds=None):
        if action not in {"publish", "rollback", "kill", "auto_pause", "rescue", "resolve", "override", "override_expired"}:
            raise ValueError("Unknown traffic change")
        with self.lock, self.store.connect() as conn:
            pointer = conn.execute("SELECT config_id, revision FROM traffic_pointer FOR UPDATE").fetchone()
            if pointer is None:
                raise ValueError("Traffic pointer is uninitialized")
            prior = conn.execute("SELECT * FROM traffic_audit WHERE operation_id = %s",
                                 (operation_id,)).fetchone()
            if prior:
                target_id = target if isinstance(target, str) else target.config_id
                if (prior["action"], prior["actor"], prior["config_id"], prior["revision"]) != (
                        action, actor, target_id, expected_revision + 1):
                    raise ValueError("Operation ID was used for a different mutation")
                if action == "override":
                    previous = conn.execute("SELECT reason, duration_seconds FROM traffic_overrides WHERE revision=%s",
                                            (prior["revision"],)).fetchone()
                    if (previous["reason"], previous["duration_seconds"]) != (reason, override_seconds):
                        raise ValueError("Operation ID was used for a different override")
                return prior["revision"]
            if pointer["revision"] != expected_revision:
                raise ValueError("Traffic revision conflict")
            frozen = conn.execute("SELECT 1 FROM traffic_incident").fetchone()
            if frozen and action not in {"kill", "rescue", "resolve"}:
                raise ValueError("Traffic releases are frozen during the rescue incident")
            current = conn.execute("SELECT payload FROM traffic_configs WHERE config_id = %s",
                                   (pointer["config_id"],)).fetchone()
            old = TrafficConfigSnapshot(**current["payload"])
            if action == "rollback":
                row = conn.execute("SELECT payload FROM traffic_configs WHERE config_id = %s",
                                   (target,)).fetchone()
                if row is None:
                    raise ValueError("Unknown rollback config ID")
                target = TrafficConfigSnapshot(**row["payload"])
                if target.canary_percent:
                    raise ValueError("Rollback target must be a stable configuration")
            elif action == "rescue":
                if target.config_id != self.rescue.config.config_id:
                    raise ValueError("Emergency rescue must use the provisioned config")
                conn.execute("INSERT INTO traffic_incident VALUES (true, %s) ON CONFLICT DO NOTHING",
                             ("Rollback convergence failed",))
            elif action == "resolve":
                if not frozen or target.config_id != self.rescue.config.config_id:
                    raise ValueError("Resolve a rescue incident from the designated config")
                conn.execute("DELETE FROM traffic_incident")
            elif action == "override":
                paused = conn.execute("SELECT action FROM traffic_audit WHERE revision = %s",
                                      (expected_revision,)).fetchone()
                former = conn.execute("SELECT config_id FROM traffic_audit WHERE revision = %s",
                                      (expected_revision - 1,)).fetchone()
                if (not paused or paused["action"] != "auto_pause" or not former
                        or former["config_id"] != target.config_id or not reason or reason.isspace()
                        or not isinstance(override_seconds, int) or not 1 <= override_seconds <= 600):
                    raise ValueError("Override requires the auto-paused configuration, reason and bounded duration")
            elif action in {"kill", "auto_pause", "override_expired"}:
                if target.state != "killed" or target.stable_generation_id != old.stable_generation_id:
                    raise ValueError("Kill requires the current stable generation")
            elif target.experiment_id == old.experiment_id:
                if target.routing_salt_id != old.routing_salt_id:
                    raise ValueError("Version the experiment before rotating its routing salt")
                if target.state != old.state and target.state not in TRANSITIONS[old.state]:
                    raise ValueError("Invalid experiment transition")
                if target.state not in {"promoted"} and target.stable_generation_id != old.stable_generation_id:
                    raise ValueError("Stable generation can change only during promotion")
            elif target.state != "draft" or target.stable_generation_id != old.stable_generation_id:
                raise ValueError("A new experiment must start with the current stable generation")
            if action == "publish" and target.state == "promoted":
                if (not self.promotion_allowed or old.canary_generation_id != target.stable_generation_id
                        or not self.promotion_allowed(self.generation(target.stable_generation_id))):
                    raise ValueError("Promotion requires a signed approval for the current canary")
            ready = conn.execute("""
                    SELECT instance_id, prepared FROM traffic_instances
                    WHERE last_seen > clock_timestamp() - %s * interval '1 second'
                    """, (3 * self.poll_seconds,)).fetchall()
            if target.canary_percent and (not ready or any(target.config_id not in row["prepared"] for row in ready)):
                raise ValueError("Both generations must be preloaded by every leased instance")
            revision = expected_revision + 1
            self.load(target, revision)
            conn.execute("INSERT INTO traffic_configs VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (target.config_id, Jsonb(asdict(target))))
            result = conn.execute("UPDATE traffic_pointer SET config_id=%s, revision=%s WHERE revision=%s",
                                  (target.config_id, revision, expected_revision))
            if result.rowcount != 1:
                raise ValueError("Traffic revision conflict")
            conn.execute("INSERT INTO traffic_audit(operation_id, action, config_id, revision, actor) "
                         "VALUES (%s, %s, %s, %s, %s)",
                         (operation_id, action, target.config_id, revision, actor))
            if action == "override":
                expires = datetime.now(timezone.utc) + timedelta(seconds=override_seconds)
                conn.execute("INSERT INTO traffic_overrides VALUES (%s, %s, %s, %s)",
                             (revision, reason, expires, override_seconds))
            recovery = old.config_id if not old.canary_percent else self.rescue.config.config_id
            conn.execute("INSERT INTO traffic_tracking(revision, expected_instances, recovery_config_id) "
                         "VALUES (%s, %s, %s)",
                         (revision, Jsonb([row["instance_id"] for row in ready]), recovery))
        return revision
