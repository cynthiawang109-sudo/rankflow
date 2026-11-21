"""Local W2-dev feature-drift demonstration using the signed operator audit."""
import argparse
from bisect import bisect_right
import hmac
import json
import math
import os
from pathlib import Path
from uuid import uuid4

from .features import FEATURE_NAMES, FEATURE_VERSION, build_features
from .generation import Generation
from .retrieval import retrieve
from .security import append_audit, signature
from .store import PostgresStore
from .training_pipeline import pinned_inputs, queries


ACTION = "feature_drift_demo"
FEATURE = "session_length"
EDGES = (2, 5, 10, 20, 50)
MINIMUM = 1_000
THRESHOLD = 0.25
CONSECUTIVE = 2
SHIFT = 100
PHASES = ("normal", "shift", "shift", "recovery", "recovery")


def measure(reference, observed, missing):
    """Use fixed bins and a half-count pseudocount for PSI."""
    total = sum(observed)
    psi = None
    if min(sum(reference), total) >= MINIMUM:
        expected_total = sum(reference) + len(reference) / 2
        actual_total = total + len(observed) / 2
        psi = 0.0
        for expected, actual in zip(reference, observed, strict=True):
            p = (expected + .5) / expected_total
            q = (actual + .5) / actual_total
            psi += (q - p) * math.log(q / p)
    return {"reference_counts": reference, "observed_counts": observed, "observed_count": total,
            "missing_count": missing, "missing_rate": missing / (total + missing) if total + missing else None,
            "psi": psi}


def monitor(store, key, generation, reference, windows):
    demo_id = uuid4().hex
    alert_id = None
    streak = 0
    with store.connect() as connection:
        for index, (phase, observed, missing) in enumerate(windows, 1):
            metrics = measure(reference, observed, missing)
            psi = metrics["psi"]
            breached = psi is not None and psi >= THRESHOLD
            streak = streak + 1 if psi is not None and breached == (alert_id is None) else 0
            status = "insufficient_data" if psi is None else "active" if alert_id else "clear"
            if streak == CONSECUTIVE:
                streak = 0
                if alert_id is None:
                    alert_id = uuid4().hex
                    status = "raised"
                else:
                    status = "recovered"
            subject = {
                **metrics, "demo_id": demo_id, "window": index, "phase": phase, "source": "demo",
                "population": "W2-dev", "generation": generation, "strategy": "rule-v1",
                "feature_schema": FEATURE_VERSION, "feature": FEATURE, "bin_edges": EDGES,
                "threshold": THRESHOLD, "minimum_count": MINIMUM, "consecutive_windows": CONSECUTIVE,
                "alert_id": alert_id, "status": status, "breached": breached,
                "action": "Investigate and block promotion of new generations until reviewed.",
            }
            append_audit(connection, key, "local-drift-monitor", ACTION, subject)
            if status == "recovered":
                alert_id = None
    return demo_id


def reports(store, key, demo_id):
    with store.connect() as connection:
        rows = connection.execute("""
            SELECT record, signature FROM admin_audit_log
            WHERE record->>'action' = %s AND record->'subject'->>'demo_id' = %s
            ORDER BY (record->'subject'->>'window')::int
            """, (ACTION, demo_id)).fetchall()
    return [row["record"] for row in rows
            if hmac.compare_digest(row["signature"], signature(key, row["record"]))]


def histograms(directory, snapshot, config):
    """Split covered labeled queries by session, matching W2-dev's scored population."""
    counts = [[0] * (len(EDGES) + 1) for _ in range(len(PHASES) + 1)]
    index = FEATURE_NAMES.index(FEATURE)
    for query, _ in queries(directory, snapshot):
        target = query["positive_aid"]
        if target is None:
            continue
        events = query["prefix_events"]
        candidates = retrieve(snapshot, events, config)
        if not any(candidate.aid == target for candidate in candidates):
            continue
        group = int(query["session_id_hash"], 16) % len(counts)
        shift = SHIFT if group and PHASES[group - 1] == "shift" else 0
        for row in build_features(snapshot, events, candidates):
            counts[group][bisect_right(EDGES, row[index] + shift)] += 1
    return counts[0], [(phase, counts[index], 0) for index, phase in enumerate(PHASES, 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("stable", type=Path)
    args = parser.parse_args()
    store = PostgresStore(os.environ["RANKFLOW_TEST_DATABASE_URL"])
    key = os.environ["RANKFLOW_AUDIT_KEY"].encode()
    stable = Generation.load(args.stable, isolated=True)
    _, _, _, snapshot, config = pinned_inputs(args.directory)
    if (stable.assigned.strategy_id != "rule-v1" or stable.snapshot.snapshot_id != snapshot.snapshot_id
            or stable.config != config):
        parser.error("Stable bundle must match the frozen rule-v1 development inputs")
    reference, windows = histograms(args.directory, snapshot, config)
    store.initialize()
    demo_id = monitor(store, key, stable.generation_id, reference, windows)
    print(json.dumps(reports(store, key, demo_id), indent=2))


if __name__ == "__main__":
    main()
