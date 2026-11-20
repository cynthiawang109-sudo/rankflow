"""Immutable traffic configuration snapshots and audited compare-and-swap."""
from dataclasses import asdict, dataclass
import hashlib
import hmac
from threading import Lock
from time import monotonic

from psycopg.types.json import Jsonb

from .generation import Generation, encoded

SCHEMA = """
CREATE TABLE IF NOT EXISTS traffic_configs (
    config_id TEXT PRIMARY KEY, payload JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS traffic_pointer (
    singleton BOOLEAN PRIMARY KEY CHECK (singleton),
    config_id TEXT NOT NULL REFERENCES traffic_configs(config_id), revision BIGINT NOT NULL
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

    def __post_init__(self):
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
        return "cfg-" + hashlib.sha256(encoded(asdict(self))).hexdigest()

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
    def __init__(self, store, generation_root, rescue, salts, poll_seconds=1):
        if rescue.canary_generation_id or rescue.shadow_generation_id:
            raise ValueError("Rescue configuration must be stable-only")
        self.store = store
        self.generation_root = generation_root
        self.salts = salts
        self.poll_seconds = poll_seconds
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
            except Exception:
                pin = self.rescue
            self.refresh_at = monotonic() + 3 * self.poll_seconds
            self.current = pin

    def publish(self, target, expected_revision, operation_id, actor, action="publish"):
        if action not in {"publish", "rollback", "kill"}:
            raise ValueError("Unknown traffic change")
        with self.lock, self.store.connect() as conn:
            pointer = conn.execute("""
                SELECT p.config_id, p.revision, c.payload FROM traffic_pointer p
                JOIN traffic_configs c USING (config_id) FOR UPDATE OF p
                """).fetchone()
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
            old = TrafficConfigSnapshot(**pointer["payload"])
            if action == "rollback":
                row = conn.execute("SELECT payload FROM traffic_configs WHERE config_id = %s",
                                   (target,)).fetchone()
                if row is None:
                    raise ValueError("Unknown rollback config ID")
                target = TrafficConfigSnapshot(**row["payload"])
                if target.canary_percent:
                    raise ValueError("Rollback target must be a stable configuration")
            elif action == "kill":
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
