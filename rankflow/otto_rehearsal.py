"""Rehearse the OTTO learning pipeline in a fresh, post-W3 epoch."""
import argparse
from copy import deepcopy
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .data.pipeline import build_run, read_config
from .epoch_registry import register_epoch
from .evaluate_retrieval import queries
from .release_gate import append_signed
from .retrieval import RetrievalConfig, Snapshot
from .store import PostgresStore
from .strategies import LIGHTGBM_CONFIG, load_model
from .train import fit_model
from .training_pipeline import BASELINE_PATH, SAMPLING, build_lineage, canonical, paired_evaluation, read_json


def run(source, out, download_manifest, store, signing_key):
    baseline = read_json(BASELINE_PATH)
    start = baseline["windows"]["W3"][1]
    day = 86_400_000
    config = deepcopy(read_config(BASELINE_PATH.parents[1] / "configs/stage0.yaml"))
    config.update(epoch_id="stage2-later-otto-v1", manifest_version="stage2-later-otto-v1")
    config["windows"]["otto"] = {
        "W0": [start, start + day], "W1": [start + day, start + 3 * day],
        "W2": [start + 3 * day, start + 5 * day], "W3": [start + 5 * day, start + 7 * day],
    }
    config["sampler"] = {"seed": "rankflow-stage2-later-otto-v1", "cap": 10_000}
    retrieval = RetrievalConfig(**{key: value for key, value in baseline["retrieval"].items()
                                   if key != "snapshot_id"})
    if out.exists():
        raise FileExistsError(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=out.parent) as workspace:
        staging = Path(workspace) / "rehearsal"
        manifest, _, _ = build_run(source, staging, config, "otto", download_manifest, later_otto=True)
        snapshot = Snapshot.load(staging)
        epoch = read_json(staging / "evaluation_epoch.json")
        if epoch["training_data_watermark"] < start or epoch["validation_window"][0] <= start:
            raise ValueError("Later-OTTO epoch is outside the registered time bounds")
        register_epoch(store, baseline["epoch"])
        register_epoch(store, epoch)
        model, counts, _ = fit_model(queries(staging, snapshot, "W1"), snapshot, retrieval, LIGHTGBM_CONFIG)
        artifact = staging / "lgbm-otto-rehearsal-v1.txt"
        model.booster_.save_model(str(artifact))
        strategy = replace(load_model(artifact), strategy_id="lgbm-otto-rehearsal-v1")
        evaluation, _ = paired_evaluation(queries(staging, snapshot), snapshot, retrieval, strategy)
        local_baseline = {**baseline, "retrieval": {**baseline["retrieval"], "snapshot_id": snapshot.snapshot_id}}
        report = {"feature_schema": baseline["features"]["schema"],
                  "feature_code_sha256": baseline["features"]["code_sha256"],
                  "lgbm_params": LIGHTGBM_CONFIG, "lightgbm": __import__("lightgbm").__version__}
        code_version = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        lineage = build_lineage((local_baseline, manifest, epoch, snapshot, retrieval), report, strategy, code_version)
        lineage.pop("run_id")
        lineage["evaluation_protocol_version"] = "stage2-later-otto-development-v1"
        lineage["run_id"] = hashlib.sha256(canonical(lineage)).hexdigest()
        (staging / "run.json").write_bytes(canonical({"lineage": lineage, "training": counts,
                                                     "evaluation": evaluation}) + b"\n")
        card = ["# lgbm-otto-rehearsal-v1 model card", "", SAMPLING, "",
                "The sampling note describes the pinned Stage 0 baseline. This rehearsal uses verified "
                "later OTTO session prefixes and reports development evidence for its own epoch.", "",
                "| Segment | Labeled | Coverage | HitRate@20 | MRR@20 |",
                "|---|---:|---:|---:|---:|"]
        for name, row in evaluation["slices"].items():
            metrics = row["metrics"][strategy.strategy_id]
            card.append(f"| {name} | {row['labeled']} | {row['candidate_coverage']:.4%} | "
                        f"{metrics['HitRate@20']:.6f} | {metrics['MRR@20']:.6f} |")
        (staging / "model_card.md").write_text("\n".join(card) + "\n", encoding="utf-8")
        append_signed(staging / "decision.json", {
            "lineage": lineage, "decision": "rejected",
            "reason": "Development-only rehearsal. No promotion comparison was authorized for this epoch.",
            "sampling_limitation": SAMPLING,
        }, signing_key)
        staging.rename(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("source", "download_manifest", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    key = os.environ["RANKFLOW_RELEASE_SIGNING_KEY"].encode()
    if len(key) < 32:
        parser.error("Release signing key must contain at least 32 bytes")
    store = PostgresStore(os.environ["RANKFLOW_DATABASE_URL"])
    store.initialize()
    run(args.source, args.output, args.download_manifest, store, key)


if __name__ == "__main__":
    main()
