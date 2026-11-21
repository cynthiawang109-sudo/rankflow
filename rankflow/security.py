"""Local access controls and integrity records for privileged mutations."""
import hashlib
import hmac
import json
from threading import Lock
from time import monotonic
from uuid import uuid4

from fastapi import HTTPException
from psycopg.types.json import Jsonb


AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS admin_audit_log (
    audit_id TEXT PRIMARY KEY, record JSONB NOT NULL, signature TEXT NOT NULL
);
"""
LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def append_audit(connection, key, actor, action, subject):
    record = {"audit_id": uuid4().hex, "actor": actor, "action": action, "subject": subject,
              "recorded_at": connection.execute("SELECT clock_timestamp() AS now").fetchone()["now"].isoformat()}
    connection.execute("INSERT INTO admin_audit_log VALUES (%s, %s, %s)",
                       (record["audit_id"], Jsonb(record), signature(key, record)))


def signature(key, record):
    return hmac.new(key, json.dumps(record, sort_keys=True, separators=(",", ":")).encode(),
                    hashlib.sha256).hexdigest()


def csrf(request):
    token = request.cookies.get("rankflow_csrf")
    supplied = request.headers.get("x-csrf-token", "")
    if (token or request.headers.get("origin")) and (not token or not hmac.compare_digest(
            token.encode(), supplied.encode())):
        raise HTTPException(403, "csrf_token_required")


class RateLimit:
    """One token bucket per public route family per instance, without client identifiers."""
    def __init__(self, per_second, burst):
        if per_second <= 0 or burst <= 0:
            raise ValueError("Public rate limits must be positive")
        self.per_second, self.burst = per_second, burst
        self.lock = Lock()
        self.buckets = {}

    def allow(self, family):
        now = monotonic()
        with self.lock:
            remaining, last = self.buckets.get(family, (self.burst, now))
            remaining = min(self.burst, remaining + max(0, now - last) * self.per_second)
            allowed = remaining >= 1
            self.buckets[family] = remaining - int(allowed), max(now, last)
            return allowed
