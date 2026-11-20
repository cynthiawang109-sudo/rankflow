"""Reproduce the frozen OTTO ranker and register its training lineage."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .data.ingestion import file_hash
from .evaluate_retrieval import queries
from .features import build_features, feature_code_hash
from .retrieval import RetrievalConfig, Snapshot, retrieve
from .strategies import LIGHTGBM_CONFIG, RULE, load_model
from .train import credits, run

BASELINE_PATH = Path(__file__).resolve().parents[1] / "docs/stage1_baseline_manifest.json"
PROTOCOL = "stage2-development-v1"
SAMPLING = (
    "Boundary exclusion retained 62.1% of sessions with at most 20 events, "
    "23.1% with 21–100 events, and 4.6% with more than 100 events. "
    "Headline metrics describe the retained OTTO population."
)
METRICS = ("HitRate@20", "MRR@20", "NDCG@20")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def pinned_inputs(directory):
    baseline = read_json(BASELINE_PATH)
    prefix = "artifacts/stage0-otto/"
    for name in ("data_manifest.json", "evaluation_epoch.json", "sessions.jsonl"):
        if file_hash(directory / name) != baseline["files_sha256"][prefix + name]:
            raise ValueError(f"Unregistered OTTO input: {name}")
    manifest = read_json(directory / "data_manifest.json")
    epoch = read_json(directory / "evaluation_epoch.json")
    windows = manifest["configuration"]["windows"]["otto"]
    if windows["W1"][1] > epoch["final_test_window"][0]:
        raise ValueError("Training interval overlaps sealed W3")
    snapshot = Snapshot.load(directory)
    if snapshot.snapshot_id != epoch["retrieval_snapshot_id"]:
        raise ValueError("Retrieval snapshot differs from the pinned epoch")
    if feature_code_hash() != baseline["features"]["code_sha256"]:
        raise ValueError("Feature code differs from the pinned baseline")
    if LIGHTGBM_CONFIG != baseline["strategies"]["lgbm-v1"]["training_configuration"]:
        raise ValueError("Training configuration differs from the pinned baseline")
    config = RetrievalConfig(**{key: value for key, value in baseline["retrieval"].items()
                                if key != "snapshot_id"})
    return baseline, manifest, epoch, snapshot, config


def query_slices(query, session_events, snapshot):
    length = len(session_events)
    segment = "up_to_20" if length <= 20 else "21_to_100" if length <= 100 else "over_100"
    cold = not any(event["aid"] in snapshot.popularity_ranks for event in query["prefix_events"])
    rank = snapshot.popularity_ranks.get(query["positive_aid"])
    popularity = "unseen" if rank is None else "head" if rank <= 100 else "tail"
    return ("overall", f"session_length/{segment}", f"prefix/{'cold' if cold else 'warm'}",
            f"target_popularity/{popularity}")


def paired_evaluation(population, snapshot, config, model):
    clusters = defaultdict(lambda: defaultdict(lambda: [0, 0, 0., 0., 0., 0., 0., 0.]))
    no_label = 0
    for query, session_events in population:
        target = query["positive_aid"]
        if target is None:
            no_label += 1
            continue
        events = query["prefix_events"]
        candidates = retrieve(snapshot, events, config)
        covered = any(candidate.aid == target for candidate in candidates)
        values = [1, int(covered)]
        if covered:
            rows = build_features(snapshot, events, candidates)
            for strategy in (RULE, model):
                values.extend(credits([candidate.aid for candidate, _ in strategy.rank(candidates, rows)], target))
        else:
            values.extend([0] * 6)
        for segment in query_slices(query, session_events, snapshot):
            totals = clusters[segment][query["session_id_hash"]]
            for index, value in enumerate(values):
                totals[index] += value
    if not clusters:
        raise ValueError("Evaluation requires labeled queries")
    summaries = {}
    for segment, sessions in sorted(clusters.items()):
        totals = [sum(column) for column in zip(*sessions.values())]
        count = totals[0]
        summaries[segment] = {
            "sessions": len(sessions), "labeled": count, "retrieved": totals[1],
            "candidate_coverage": totals[1] / count,
            "metrics": {
                strategy.strategy_id: dict(zip(METRICS, (value / count for value in totals[start:start + 3])))
                for strategy, start in ((RULE, 2), (model, 5))
            },
        }
    return {"no_label": no_label, "slices": summaries}, clusters


def train_once(directory, output, code_version, inputs):
    baseline, manifest, epoch, snapshot, config = inputs
    report = run(directory, output, config, "python -m rankflow.training_pipeline")
    artifact = output / "lgbm-v1.txt"
    model = load_model(artifact)
    if model.artifact_hash != baseline["strategies"]["lgbm-v1"]["artifact_sha256"]:
        raise ValueError("Model does not reproduce the frozen lgbm-v1 checksum")
    evaluation, _ = paired_evaluation(queries(directory, snapshot), snapshot, config, model)
    lineage = {
        "source": "otto_offline",
        "epoch_id": epoch["epoch_id"],
        "data_manifest_version": manifest["configuration"]["manifest_version"],
        "data_manifest_sha256": epoch["dataset_manifest_hash"],
        "query_manifest_sha256": epoch["query_manifest_hash"],
        "label_policy_version": manifest["configuration"]["label_policy_version"],
        "feature_schema": report["feature_schema"],
        "feature_code_sha256": report["feature_code_sha256"],
        "retrieval_snapshot_id": snapshot.snapshot_id,
        "candidate_configuration": baseline["retrieval"],
        "training_configuration": report["lgbm_params"],
        "random_seed": report["lgbm_params"]["random_state"],
        "lightgbm": report["lightgbm"],
        "code_version": code_version,
        "artifact_sha256": model.artifact_hash,
        "evaluation_protocol_version": PROTOCOL,
    }
    lineage["run_id"] = hashlib.sha256(canonical(lineage)).hexdigest()
    training = {key: value for key, value in report["training"].items() if key != "fit_seconds"}
    return {"lineage": lineage, "training": training, "evaluation": evaluation,
            "sampling_limitation": SAMPLING}


def register(directory, registry, reproduce):
    repository = BASELINE_PATH.parents[1]
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=repository).strip():
        raise ValueError("Commit tracked code changes before registering a run")
    code_version = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repository, text=True).strip()
    inputs = pinned_inputs(directory)
    registry.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=registry) as temporary:
        staging = Path(temporary) / "run"
        record = train_once(directory, staging, code_version, inputs)
        if reproduce:
            second = train_once(directory, Path(temporary) / "replay", code_version, inputs)
            if canonical(record) != canonical(second):
                raise ValueError("Reproduction differs in lineage, counts or evaluation")
            record["reproduction"] = {
                "absolute_metric_tolerance": 0.0,
                "bit_identical": ["model bytes", "canonical lineage"],
                "numerically_identical": ["training counts", "development slice metrics"],
                "excluded": ["wall clock timings"],
            }
        run_id = record["lineage"]["run_id"]
        (staging / "run.json").write_bytes(canonical(record) + b"\n")
        lines = ["# lgbm-v1 model card", "", SAMPLING, "", "Evaluation population is W2-dev.", "",
                 "| Segment | Labeled | Coverage | HitRate@20 | MRR@20 |",
                 "|---|---:|---:|---:|---:|"]
        for segment, evidence in record["evaluation"]["slices"].items():
            metrics = evidence["metrics"]["lgbm-v1"]
            lines.append(f"| {segment} | {evidence['labeled']} | {evidence['candidate_coverage']:.4%} | "
                         f"{metrics['HitRate@20']:.4%} | {metrics['MRR@20']:.6f} |")
        (staging / "model_card.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        destination = registry / (run_id + ("-verified" if reproduce else ""))
        if destination.exists():
            if read_json(destination / "run.json") != record or file_hash(destination / "lgbm-v1.txt") != record["lineage"]["artifact_sha256"]:
                raise ValueError("Run registry already contains different evidence")
        else:
            staging.rename(destination)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--reproduce", action="store_true")
    args = parser.parse_args()
    print(register(args.directory, args.registry, args.reproduce))


if __name__ == "__main__":
    main()
