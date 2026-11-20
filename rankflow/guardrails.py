"""Synthetic operational canary guardrails based on finalized telemetry windows."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import logging
from threading import Lock

import psycopg

from .operations import emit

LOG = logging.getLogger(__name__)
WINDOW = timedelta(minutes=1)
MINIMUM_REQUESTS = 20
FALLBACK_LIMIT = .05
SUSTAINED_WINDOWS = 2


class Guardrails:
    def __init__(self, store, traffic):
        self.store = store
        self.traffic = traffic
        self.lock = Lock()
        self.status = {"mode": "synthetic_operational", "state": "inactive"}
        self.last_sample = None

    def sample(self, pin, now=None):
        now = now or datetime.now(timezone.utc)
        end = now.replace(second=0, microsecond=0)
        with self.lock:
            if pin.degraded or not pin.config.canary_percent:
                self.status = {"mode": "synthetic_operational", "state": "inactive"}
                return self.status
            token = (pin.revision, end)
            if self.last_sample == token and self.status["state"] != "override":
                return self.status
            self.last_sample = token
            try:
                with self.traffic.store.connect() as conn:
                    override = conn.execute("SELECT expires_at FROM traffic_overrides WHERE revision = %s",
                                            (pin.revision,)).fetchone()
            except psycopg.Error:
                emit("guardrail_override_lookup_failed", logging.WARNING, revision=pin.revision)
                override = None
            if override:
                state = "override" if now < override["expires_at"] else "override_expired"
                windows = []
            else:
                state, windows, health = self.measure(pin, end)
            if override:
                health = "unknown"
            self.status = {"mode": "synthetic_operational", "config_id": pin.config.config_id,
                           "revision": pin.revision, "state": state, "health": health, "windows": windows}
            if state in {"auto_pause", "override_expired"}:
                target = replace(pin.config, state="killed", canary_generation_id=None, canary_percent=0,
                                 shadow_generation_id=None, shadow_mode=None)
                try:
                    self.traffic.publish(target, pin.revision, f"guardrail-{pin.revision}",
                                         "guardrail", state)
                    alert = "canary_fallback" if health == "degraded" else "canary_unknown"
                    if state == "auto_pause":
                        emit(alert, logging.WARNING, revision=pin.revision, config_id=pin.config.config_id,
                             action="pause")
                    LOG.warning("Synthetic operational canary paused at revision %s", pin.revision)
                except (ValueError, psycopg.Error):
                    emit("canary_pause_failed", logging.WARNING, revision=pin.revision)
                    LOG.warning("Canary pause will retry at revision %s", pin.revision)
                    self.last_sample = None
            return self.status

    def measure(self, pin, end):
        start = end - SUSTAINED_WINDOWS * WINDOW
        windows = [{"requests": 0, "fallbacks": 0} for _ in range(SUSTAINED_WINDOWS)]
        try:
            with self.traffic.store.connect() as conn:
                activated = conn.execute("SELECT recorded_at FROM traffic_audit WHERE revision = %s",
                                         (pin.revision,)).fetchone()["recorded_at"]
        except (TypeError, psycopg.Error):
            emit("guardrail_activation_unavailable", logging.WARNING, revision=pin.revision)
            return "unknown", windows, "unknown"
        try:
            with self.store.connect() as conn:
                rows = conn.execute("""
                    SELECT date_trunc('minute', i.created_at) AS bucket, count(*) AS requests,
                           count(*) FILTER (WHERE d.payload->>'fallback_used' = 'true') AS fallbacks
                    FROM impressions i JOIN decisions d ON d.impression_id = i.id
                    WHERE i.created_at >= %s AND i.created_at < %s
                      AND d.payload->>'config_revision' = %s
                      AND coalesce(d.payload->>'assigned_generation_id', d.payload->>'serving_generation') = %s
                      AND d.payload->>'assignment' = 'canary'
                      AND d.payload->>'source' = 'demo'
                    GROUP BY 1 ORDER BY 1
                    """, (start, end, str(pin.revision), pin.canary.generation_id)).fetchall()
            for row in rows:
                index = (row["bucket"] - start) // WINDOW
                windows[index] = {"requests": row["requests"], "fallbacks": row["fallbacks"]}
        except psycopg.Error:
            LOG.warning("Synthetic operational canary telemetry unavailable")
        states = []
        for index, bucket in enumerate(windows):
            requests = bucket["requests"]
            known = start + index * WINDOW >= activated and requests >= MINIMUM_REQUESTS
            if not known:
                states.append("unknown")
            elif bucket["fallbacks"] / requests > FALLBACK_LIMIT:
                states.append("breached")
            else:
                states.append("within_limit")
        health = {"breached": "degraded", "within_limit": "healthy", "unknown": "unknown"}[states[-1]]
        if activated <= start and all(state == states[-1] for state in states) and states[-1] != "within_limit":
            return "auto_pause", windows, health
        return states[-1], windows, health
