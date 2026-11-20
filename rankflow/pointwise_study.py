"""Run the preregistered development-only pointwise comparison."""
import argparse
from dataclasses import replace
import subprocess
from pathlib import Path

from .evaluate_retrieval import queries
from .release_gate import intervals
from .strategies import LIGHTGBM_CONFIG, load_model
from .train import fit_model
from .training_pipeline import SAMPLING, canonical, paired_evaluation, pinned_inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("directory", "lambda_artifact", "output"):
        parser.add_argument(argument, type=Path)
    args = parser.parse_args()
    baseline, _, epoch, snapshot, config = pinned_inputs(args.directory)
    reference = load_model(args.lambda_artifact)
    if reference.artifact_hash != baseline["strategies"]["lgbm-v1"]["artifact_sha256"]:
        raise ValueError("The reference must be the frozen LambdaRank artifact")
    args.output.mkdir(parents=True, exist_ok=False)
    policy = {"protocol": "stage2-pointwise-development-v1", "bootstrap_replicates": 2000,
              "bootstrap_seed": 42, "confidence_level": .95, "primary_metrics": ["HitRate@20", "MRR@20"],
              "tolerance_absolute": .005,
              "tie_break": "Retain LambdaRank when the pointwise challenger is within tolerance",
              "release_eligibility": "Development comparison only"}
    (args.output / "protocol.json").write_bytes(canonical(policy) + b"\n")
    parameters = {key: value for key, value in LIGHTGBM_CONFIG.items() if key != "label_gain"}
    parameters["objective"] = "binary"
    model, counts, _ = fit_model(queries(args.directory, snapshot, "W1"), snapshot, config, parameters)
    path = args.output / "pointwise-v1.txt"
    model.booster_.save_model(str(path))
    candidate = replace(load_model(path), strategy_id="pointwise-v1")
    evaluation, clusters = paired_evaluation(queries(args.directory, snapshot), snapshot, config,
                                              candidate, reference=reference)
    material_regression = False
    for segment, sessions in clusters.items():
        metrics = evaluation["slices"][segment]
        metrics["delta_confidence_intervals"] = intervals(sessions, policy)
        metrics["primary_deltas"] = {
            metric: metrics["metrics"][candidate.strategy_id][metric] -
                    metrics["metrics"][reference.strategy_id][metric]
            for metric in policy["primary_metrics"]
        }
        material_regression |= any(delta < -policy["tolerance_absolute"]
                                   for delta in metrics["primary_deltas"].values())
    overall = evaluation["slices"]["overall"]["primary_deltas"]
    advantage = any(delta > policy["tolerance_absolute"] for delta in overall.values())
    report = {
        "source": "otto_offline", "window": "W2-dev", "policy": policy,
        "epoch": epoch, "feature_schema": baseline["features"]["schema"],
        "feature_code_sha256": baseline["features"]["code_sha256"],
        "retrieval": baseline["retrieval"], "training_configuration": parameters, "training_counts": counts,
        "candidate_sha256": candidate.artifact_hash, "reference_sha256": reference.artifact_hash,
        "code_version": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "evaluation": evaluation, "sampling_limitation": SAMPLING,
        "development_preference": "pointwise-v1" if advantage and not material_regression else "lgbm-v1",
        "release_decision": "no promotion",
    }
    (args.output / "comparison.json").write_bytes(canonical(report) + b"\n")


if __name__ == "__main__":
    main()
