"""Bounded-dimension operational telemetry without request payloads."""
from collections import Counter, defaultdict
import json
import logging
from threading import Lock

LOG = logging.getLogger("rankflow.operations")


def emit(event, level=logging.INFO, **fields):
    LOG.log(level, json.dumps({"event": event, **fields}, sort_keys=True))


class RequestMetrics:
    def __init__(self):
        self.lock = Lock()
        self.totals = defaultdict(Counter)

    def record(self, generation, cohort, source, fallback, degraded):
        with self.lock:
            counts = self.totals[generation, cohort, source]
            counts["ranked_requests"] += 1
            counts["fallbacks"] += int(fallback)
            counts["degraded_logging"] += int(degraded)

    def snapshot(self):
        with self.lock:
            return [dict(generation=generation, cohort=cohort, source=source, **counts)
                    for (generation, cohort, source), counts in sorted(self.totals.items())]


ALERTS = {
    "canary_unknown": ("pause", "canary-health"),
    "canary_fallback": ("pause", "canary-health"),
    "canary_pause_failed": ("page", "canary-health"),
    "logging_degraded": ("page", "database-and-outbox"),
    "outbox_retry": ("page", "database-and-outbox"),
    "fleet_stale": ("rollback", "fleet-convergence"),
}
ALERT_CATALOGUE = {name: {"action": action, "runbook": f"/operator/runbook#{entry}"}
                   for name, (action, entry) in ALERTS.items()}
