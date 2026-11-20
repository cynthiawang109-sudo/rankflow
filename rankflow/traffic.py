"""Immutable traffic configuration snapshots and audited compare-and-swap."""
from dataclasses import asdict, dataclass
import hashlib
import hmac
from threading import Lock
from time import monotonic
from uuid import uuid4
import logging

from psycopg.types.json import Jsonb

from .generation import Generation, encoded

LOGGER = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_configs (
    config_id TEXT PRIMARY KEY, payload JSONB NOT NULL
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
                 promotion_allowed=None):
        if rescue.canary_generation_id or rescue.shadow_generation_id:
            raise ValueError("Rescue configuration must be stable-only")
        self.store = store
        self.generation_root = generation_root
        self.salts = salts
        self.poll_seconds = poll_seconds
        self.promotion_allowed = promotion_allowed
        self.instance_id = uuid4().hex
        self.lock = Lock()
        self.generations = {}
        self.rescue = self.load(rescue, -1, degraded=True)
        self.current = self.rescue
        self.refresh_at = 0

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
            conn.execute(SCHEMA)
            rescue = self.rescue.config
            conn.execute("INSERT INTO traffic_configs VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (rescue.config_id, Jsonb(asdict(rescue))))
            conn.execute("INSERT INTO traffic_pointer VALUES (true, %s, 0) ON CONFLICT DO NOTHING",
                         (rescue.config_id,))

    def pin(self):
        pin = self.current
        return pin if monotonic() < self.refresh_at else self.rescue

    def refresh(self):
        with self.lock:
            try:
                with self.store.connect() as conn:
                    row = conn.execute("""
                        SELECT p.config_id, p.revision, c.payload FROM traffic_pointer p
                        JOIN traffic_configs c USING (config_id)
                        """).fetchone()
                    config = TrafficConfigSnapshot(**row["payload"])
                    if row["config_id"] != config.config_id:
                        raise ValueError("Traffic configuration checksum mismatch")
                    pin = self.load(config, row["revision"])
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
            except Exception:
                LOGGER.exception("Traffic control refresh failed")
                pin = self.rescue
            self.refresh_at = monotonic() + 3 * self.poll_seconds
            self.current = pin

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

    def publish(self, target, expected_revision, operation_id, actor, action="publish"):
        if action not in {"publish", "rollback", "kill", "auto_pause"}:
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
                return prior["revision"]
            if pointer["revision"] != expected_revision:
                raise ValueError("Traffic revision conflict")
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
            elif action in {"kill", "auto_pause"}:
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
            if target.canary_percent:
                ready = conn.execute("""
                    SELECT prepared FROM traffic_instances
                    WHERE last_seen > clock_timestamp() - %s * interval '1 second'
                    """, (3 * self.poll_seconds,)).fetchall()
                if not ready or any(target.config_id not in row["prepared"] for row in ready):
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
        return revision
