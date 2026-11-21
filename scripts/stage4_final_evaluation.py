"""Open the registered W3 population once and write its report-only comparison."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from rankflow.data.epoch import generate_queries
from rankflow.data.ingestion import file_hash
from rankflow.strategies import load_model
from rankflow.training_pipeline import paired_evaluation, pinned_inputs


DECISION = "466d0bb2fb3075a22266ed42a0fb9bff4887a411130621db9c7d35d503a9d684"
AUDIT = Path("docs/stage4_holdout_access.json")


def w3(directory, manifest, epoch, snapshot):
    members = set(manifest["memberships"]["W3"])
    with (directory / "sessions.jsonl").open("rb") as stream:
        for line in stream:
            if not line.rstrip().endswith(b'"window":"W3"}'):
                continue
            row = json.loads(line)
            if row["source"] != "otto_offline" or row["events"][0]["ts"] <= snapshot.watermark:
                raise ValueError("Holdout input violates provenance or snapshot watermark")
            members.remove(row["session"])
            for query in generate_queries(row["session"], row["events"], "W3", epoch["epoch_id"],
                                          snapshot.snapshot_id, row["source"], manifest["configuration"]):
                yield query, row["events"]
    if members:
        raise ValueError("Holdout membership mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--confirm-final-report", action="store_true", required=True)
    args = parser.parse_args()
    dataset = Path("artifacts/stage0-otto")
    evidence = json.loads(Path("docs/stage2_training_evidence.json").read_bytes())
    gate = json.loads((Path("artifacts/stage2/releases") / f"{DECISION}.json").read_bytes())["record"]
    if gate["decision_id"] != DECISION or gate["decision"] != "rejected" or gate["lineage"] != evidence["lineage"]:
        raise ValueError("Recorded W2-gate decision or lineage mismatch")
    lineage = evidence["lineage"]
    registry = Path("artifacts/stage1/generations")
    stable = (registry / "alpha.txt").read_text().strip()
    bundle = registry / stable
    generation = json.loads((bundle / "manifest.json").read_bytes())
    model_path = bundle / "lgbm-v1.txt"
    if generation["assigned_strategy"] != "rule-v1" or file_hash(model_path) != lineage["artifact_sha256"]:
        raise ValueError("Final strategy or archived comparison artifact mismatch")
    _, manifest, epoch, snapshot, config = pinned_inputs(dataset)
    if manifest["configuration"]["label_policy_version"] != "nextclick-v1" or config.candidate_cap != 100:
        raise ValueError("Frozen evaluation protocol mismatch")
    model = load_model(model_path)
    audit = {"dataset": "W3", "accessed_by": args.operator, "purpose": "Final independent report",
             "release_candidate": stable, "epoch_id": epoch["epoch_id"],
             "dataset_manifest_sha256": epoch["dataset_manifest_hash"],
             "query_manifest_sha256": epoch["query_manifest_hash"],
             "accessed_at": datetime.now(timezone.utc).isoformat()}
    with AUDIT.open("x", encoding="utf-8") as log:
        json.dump(audit, log, indent=2)
        log.write("\n")
        log.flush()
        os.fsync(log.fileno())
    evaluation, _ = paired_evaluation(w3(dataset, manifest, epoch, snapshot), snapshot, config, model)
    result = {"audit": audit, "evaluation": evaluation, "w2_gate_decision": DECISION,
              "training_run": lineage["run_id"], "label_policy": "nextclick-v1"}
    with Path("docs/stage4_final_evaluation.json").open("x", encoding="utf-8") as output:
        json.dump(result, output, indent=2)
        output.write("\n")


if __name__ == "__main__":
    main()
