"""Operator-only W2-gate evaluation and signed release records."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path

from .data.epoch import generate_queries
from .data.ingestion import file_hash
from .strategies import RULE, load_model
from .training_pipeline import METRICS, SAMPLING, canonical, paired_evaluation, pinned_inputs, read_json

POLICY = Path(__file__).resolve().parents[1] / "configs/stage2_gate.json"


def gate_queries(directory, manifest, epoch, snapshot):
    window = "W2-gate"
    members = set(manifest["memberships"][window])
    config = manifest["configuration"]
    suffix = b'"window":"W2-gate"}'
    with (directory / "sessions.jsonl").open("rb") as stream:
        for line in stream:
            if not line.rstrip().endswith(suffix):
                continue
            row = json.loads(line)
            if row["source"] != "otto_offline" or row["events"][0]["ts"] <= snapshot.watermark:
                raise ValueError("Gate row violates provenance or snapshot watermark")
            members.remove(row["session"])
            for query in generate_queries(row["session"], row["events"], window, epoch["epoch_id"],
                                          snapshot.snapshot_id, row["source"], config):
                yield query, row["events"]
    if members:
        raise ValueError("Gate population differs from manifest membership")


def intervals(sessions, policy):
    import numpy as np

    values = np.asarray(list(sessions.values()))
    counts = values[:, 0]
    delta = values[:, 5:7] - values[:, 2:4]
    rng = np.random.default_rng(policy["bootstrap_seed"])
    sample = np.empty((policy["bootstrap_replicates"], 2))
    for index in range(len(sample)):
        selected = rng.integers(len(values), size=len(values))
        sample[index] = delta[selected].sum(axis=0) / counts[selected].sum()
    tail = (1 - policy["confidence_level"]) / 2
    bounds = np.quantile(sample, [tail, 1 - tail], axis=0).T
    return {name: [float(lower), float(upper)] for name, (lower, upper) in zip(METRICS, bounds)}


def disposition(evaluation, candidate, policy):
    overall = evaluation["slices"]["overall"]["metrics"]
    primary = policy["primary_metrics"]
    tolerance = policy["absolute_non_regression_tolerance"]
    deltas = {name: overall[candidate][name] - overall[RULE.strategy_id][name] for name in primary}
    slice_regressions = {
        name: regressions for name, segment in evaluation["slices"].items() if name != "overall"
        if (regressions := [metric for metric in primary
                            if segment["metrics"][candidate][metric] - segment["metrics"][RULE.strategy_id][metric]
                            < -tolerance])
    }
    if any(delta < -tolerance for delta in deltas.values()):
        return "rejected", "Primary regression exceeds the configured tolerance", deltas, slice_regressions
    if not any(delta > tolerance for delta in deltas.values()):
        return "rejected", "No primary improvement exceeds the configured tolerance", deltas, slice_regressions
    if slice_regressions:
        return "rejected", "Registered slice regression exceeds the configured tolerance", deltas, slice_regressions
    return "approved", "Primary improvement and slice guardrails satisfied", deltas, slice_regressions


def append_signed(path, data, signing_key):
    signature = hmac.new(signing_key, canonical(data), hashlib.sha256).hexdigest()
    envelope = {"record": data, "signature": signature, "algorithm": "HMAC-SHA256"}
    with path.open("xb") as output:
        output.write(canonical(envelope) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    return envelope


def release(directory, candidate, registry, operator, signing_key):
    policy = read_json(POLICY)
    registry.mkdir(parents=True, exist_ok=True)
    lineage = read_json(candidate / "run.json")["lineage"]
    identity = hashlib.sha256(canonical([policy["epoch_id"], lineage["artifact_sha256"]])).hexdigest()
    record = {"decision_id": identity, "operator": operator, "policy": policy,
              "lineage": lineage, "sampling_limitation": SAMPLING,
              "recorded_at": datetime.now(timezone.utc).isoformat()}
    if lineage["source"] != "otto_offline":
        record.update(decision="rejected", reason="Candidate provenance is ineligible for the OTTO gate")
        return append_signed(registry / f"{identity}-provenance.json", record, signing_key)
    baseline, manifest, epoch, snapshot, config = pinned_inputs(directory)
    model_path = candidate / "lgbm-v1.txt"
    if (lineage["artifact_sha256"] != baseline["strategies"]["lgbm-v1"]["artifact_sha256"]
            or file_hash(model_path) != lineage["artifact_sha256"]
            or lineage["retrieval_snapshot_id"] != snapshot.snapshot_id
            or lineage["candidate_configuration"] != baseline["retrieval"]
            or lineage["data_manifest_sha256"] != epoch["dataset_manifest_hash"]
            or lineage["epoch_id"] != epoch["epoch_id"]
            or epoch["epoch_id"] != policy["epoch_id"]
            or manifest["configuration"]["validation_split"]["gate_percent"] != policy["gate_percent"]):
        raise ValueError("Candidate or epoch does not match the registered promotion comparison")
    model = load_model(model_path)
    append_signed(registry / f"{identity}.claim", record, signing_key)
    evaluation, clusters = paired_evaluation(gate_queries(directory, manifest, epoch, snapshot),
                                              snapshot, config, model)
    for name, sessions in clusters.items():
        evaluation["slices"][name]["delta_confidence_intervals"] = intervals(sessions, policy)
    decision, reason, deltas, regressions = disposition(evaluation, model.strategy_id, policy)
    record.update(decision=decision, reason=reason, primary_deltas=deltas,
                  slice_regressions=regressions, evaluation=evaluation)
    record["completed_at"] = datetime.now(timezone.utc).isoformat()
    return append_signed(registry / f"{identity}.json", record, signing_key)


def decision_summary(envelope):
    record = envelope["record"]
    outcome = record["decision"]
    stable = "rule-v1 remains stable." if outcome == "rejected" else "Any traffic change requires a separate release operation."
    return "\n".join([
        "# Stage 2 release decision", "",
        f"**{outcome}** ? lgbm-v1 against rule-v1 on the pinned W2-gate population.", "",
        record["reason"] + ". " + stable, "",
        f"- Decision ID `{record['decision_id']}`",
        f"- Registered training run `{record['lineage']['run_id']}`",
        f"- Protocol `{record['policy']['evaluation_protocol_version']}`",
        f"- Completed `{record['completed_at']}`",
        f"- Operator `{record['operator']}`",
        f"- Registry record signature `{envelope['signature']}` (HMAC-SHA256)", "",
        "The signed registry entry and underlying aggregates are available in the authenticated Operator Console.", "",
        SAMPLING, "",
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--bearer-stdin", action="store_true")
    args = parser.parse_args()
    expected = os.environ["RANKFLOW_ADMIN_BEARER"]
    if args.bearer_stdin:
        import sys
        presented = sys.stdin.readline().rstrip("\r\n")
    else:
        presented = getpass.getpass("Operator bearer: ")
    if not expected or not hmac.compare_digest(presented.encode(), expected.encode()):
        parser.error("Operator authentication failed")
    key = os.environ["RANKFLOW_RELEASE_SIGNING_KEY"].encode()
    if len(key) < 32:
        parser.error("Release signing key must contain at least 32 bytes")
    envelope = release(args.directory, args.candidate, args.registry, args.operator, key)
    record = envelope["record"]
    if args.summary:
        with args.summary.open("x", encoding="utf-8") as summary:
            summary.write(decision_summary(envelope))
    print(record["decision_id"], record["decision"])


if __name__ == "__main__":
    main()
