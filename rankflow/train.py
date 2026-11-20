"""Train the frozen LambdaRank baseline and measure paired W2-dev rankings."""
import argparse
from array import array
from dataclasses import asdict
import json
import math
from pathlib import Path
from time import perf_counter

from .data.ingestion import file_hash
from .evaluate_retrieval import protocol, queries
from .features import FEATURE_NAMES, FEATURE_VERSION, build_features, feature_code_hash
from .retrieval import RetrievalConfig, Snapshot, retrieve
from .strategies import LIGHTGBM_CONFIG, RULE, RULE_CONFIG, load_model


def training_groups(population, snapshot, config):
    counts = dict(queries=0, no_label=0, all_negative=0, eligible=0)
    for query, _ in population:
        counts["queries"] += 1
        target = query["positive_aid"]
        if target is None:
            counts["no_label"] += 1
            continue
        events = query["prefix_events"]
        candidates = retrieve(snapshot, events, config)
        labels = [int(candidate.aid == target) for candidate in candidates]
        if not any(labels):
            counts["all_negative"] += 1
            continue
        counts["eligible"] += 1
        yield build_features(snapshot, events, candidates), labels, counts


def credits(aids, target, k=20):
    for rank, aid in enumerate(aids[:k], 1):
        if aid == target:
            return 1, 1 / rank, 1 / math.log2(rank + 1)
    return 0, 0, 0


def compare(population, snapshot, config, model):
    totals = {strategy.strategy_id: [0., 0., 0.] for strategy in (RULE, model)}
    labeled = no_label = hits = 0
    started = perf_counter()
    for query, _ in population:
        target = query["positive_aid"]
        if target is None:
            no_label += 1
            continue
        labeled += 1
        events = query["prefix_events"]
        candidates = retrieve(snapshot, events, config)
        hits += any(candidate.aid == target for candidate in candidates)
        rows = build_features(snapshot, events, candidates)
        for strategy in (RULE, model):
            ordered = [candidate.aid for candidate, _ in strategy.rank(candidates, rows)]
            for index, score in enumerate(credits(ordered, target)):
                totals[strategy.strategy_id][index] += score
    return {
        "labeled": labeled, "no_label": no_label, "retrieved": hits,
        "metrics": {strategy: dict(zip(("HitRate@20", "MRR@20", "NDCG@20"),
                                      (value / labeled for value in scores)))
                    for strategy, scores in totals.items()},
        "wall_seconds": perf_counter() - started,
    }


def run(directory, output, config, command):
    import lightgbm
    import numpy as np

    snapshot = Snapshot.load(directory)
    manifest = json.loads((directory / "data_manifest.json").read_text())
    if file_hash(directory / "sessions.jsonl") != manifest["artifacts"]["sessions.jsonl"]:
        raise ValueError("Session checksum mismatch")
    output.mkdir(parents=True, exist_ok=True)
    matrix, labels, groups = array("f"), array("b"), []
    counts = None
    for rows, target, counts in training_groups(queries(directory, snapshot, "W1"), snapshot, config):
        for row in rows:
            matrix.extend(row)
        labels.extend(target)
        groups.append(len(target))
    if not groups:
        raise ValueError("No eligible training groups")
    assert sum(groups) == len(labels) and len(matrix) == len(labels) * len(FEATURE_NAMES)
    started = perf_counter()
    model = lightgbm.LGBMRanker(**LIGHTGBM_CONFIG)
    model.fit(np.frombuffer(matrix, dtype=np.float32).reshape(-1, len(FEATURE_NAMES)),
              np.frombuffer(labels, dtype=np.int8), group=groups, feature_name=list(FEATURE_NAMES))
    model.booster_.save_model(str(output / "lgbm-v1.txt"))
    fit_seconds = perf_counter() - started
    del matrix, labels, groups
    strategy = load_model(output / "lgbm-v1.txt")
    comparison = compare(queries(directory, snapshot), snapshot, config, strategy)
    tolerance = .01
    metrics = comparison["metrics"]
    primary = ("HitRate@20", "MRR@20")
    passes = all(metrics[strategy.strategy_id][name] >= (1 - tolerance) * metrics[RULE.strategy_id][name]
                 for name in primary)
    eligible = counts["eligible"]
    labeled = eligible + counts["all_negative"]
    evaluation_header = protocol(snapshot, directory, "same candidates for both strategies")
    evaluation_header["caps"] = [config.candidate_cap]
    metadata = {
        "protocol": evaluation_header,
        "retrieval": asdict(config), "feature_schema": FEATURE_VERSION, "feature_names": FEATURE_NAMES,
        "feature_code_sha256": feature_code_hash(), "artifact_sha256": strategy.artifact_hash,
        "rule_configuration": RULE_CONFIG, "rule_configuration_sha256": RULE.artifact_hash,
        "command": command,
        "training_window": "W1", "lgbm_params": LIGHTGBM_CONFIG, "lightgbm": lightgbm.__version__,
        "training": {**counts, "training_query_exclusion_rate": counts["all_negative"] / labeled,
                     "single_positive_rate": eligible / labeled, "fit_seconds": fit_seconds},
        "comparison": comparison, "R1_primary": primary, "relative_tolerance": tolerance,
        "primary_absolute_delta": {name: metrics[strategy.strategy_id][name] - metrics[RULE.strategy_id][name]
                                   for name in primary},
        "decision": "lgbm-v1 passes the W2-dev primary check. Promotion is reserved for Stage 2" if passes
        else "W2-dev primary regression blocks lgbm-v1. Retain rule-v1",
    }
    (output / "strategy_report.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    write_markdown(output / "strategy_report.md", metadata)
    return metadata


def write_markdown(path, report):
    comparison = report["comparison"]
    training = report["training"]
    lines = [
        "# Stage 1 strategy comparison", "", "## Replay protocol", "",
        "LambdaRank was fit on labeled W1 queries whose target was retrieved. Both strategies scored "
        "the same candidate set and shared features on W2-dev. Every labeled query stayed in the "
        "end-to-end denominator. No-label queries were counted separately.",
        "", f"- Snapshot `{report['protocol']['snapshot_id']}`",
        f"- Feature schema `{report['feature_schema']}`",
        f"- Feature code SHA-256 `{report['feature_code_sha256']}`",
        f"- LightGBM artifact SHA-256 `{report['artifact_sha256']}`",
        f"- W1 groups fit {training['eligible']:,}, all-negative exclusions {training['all_negative']:,}, "
        f"no-label {training['no_label']:,}, exclusion rate {training['training_query_exclusion_rate']:.2%}, "
        f"single-positive rate {training['single_positive_rate']:.2%}",
        f"- W2-dev labeled {comparison['labeled']:,}, no-label {comparison['no_label']:,}, "
        f"retrieved {comparison['retrieved']:,}",
        f"- Fit wall time {training['fit_seconds']:.2f}s and evaluation wall time {comparison['wall_seconds']:.2f}s",
        "", "| Strategy | HitRate@20 | MRR@20 | NDCG@20 |", "|---|---:|---:|---:|",
    ]
    for name, scores in comparison["metrics"].items():
        lines.append(f"| {name} | {scores['HitRate@20']:.4%} | {scores['MRR@20']:.4f} | {scores['NDCG@20']:.4f} |")
    metrics = comparison["metrics"]
    winners = [max(metrics, key=lambda name: metrics[name][metric]) for metric in report["R1_primary"]]
    winner_line = (f"`{winners[0]}` led on both primary metrics." if winners[0] == winners[1]
                   else f"`{winners[0]}` led on HitRate@20 and `{winners[1]}` led on MRR@20.")
    lines.extend([
        "", "## R1 decision", "", winner_line, "",
        f"The primary metrics are end-to-end HitRate@20 and MRR@20. The W2-dev development check "
        f"allows a {report['relative_tolerance']:.0%} relative regression on each. NDCG@20 is secondary.",
        "", f"**Decision** ? {report['decision']}.",
        "", "The Alpha serves the registered rule strategy and exposes the fitted model in the Playground "
        "as a ranker-only comparison.",
        "", "[Run configuration, lineage, and unrounded metrics](stage1_strategy_report.json)",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("config", type=Path)
    args = parser.parse_args()
    config = RetrievalConfig(**json.loads(args.config.read_text(encoding="utf-8-sig")))
    run(args.directory, args.output, config,
        f"python -m rankflow.train {args.directory} {args.output} {args.config}")


if __name__ == "__main__":
    main()
