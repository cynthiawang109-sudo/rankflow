"""Measure the Stage 1 retrieval ablation and boundary-exclusion follow-up."""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
from itertools import combinations
import json
from pathlib import Path
import platform
from time import perf_counter

from .data.ingestion import file_hash
from .evaluate_retrieval import CAPS, evaluate, protocol, queries, write_report
from .retrieval import RetrievalConfig, Snapshot, SOURCES


def slices(population, snapshot):
    started = perf_counter()
    groups = defaultdict(Counter)
    previous_session = None
    for query, events in population:
        session_id = query["query_id"][0]
        new_session = session_id != previous_session
        previous_session = session_id
        length = len(events)
        hours = (events[-1]["ts"] - events[0]["ts"]) / 3_600_000
        repeat = 1 - len({event["aid"] for event in events}) / length
        keys = (
            "Length ≤20" if length <= 20 else "Length 21–100" if length <= 100 else "Length >100",
            "Duration <1h" if hours < 1 else "Duration 1–24h" if hours < 24 else "Duration ≥24h",
            "Repeat share 0" if repeat == 0 else "Repeat share (0, 50%)" if repeat < .5 else "Repeat share ≥50%",
        )
        target = query["positive_aid"]
        hit = target is not None and target in snapshot.baseline(query["prefix_events"])
        for key in keys:
            row = groups[key]
            row["sessions"] += new_session
            row["queries"] += 1
            row["labeled"] += target is not None
            row["retrieved"] += hit
    for row in groups.values():
        row["label_yield"] = row["labeled"] / row["queries"]
        row["candidate_recall@100"] = row["retrieved"] / row["labeled"] if row["labeled"] else None
    return dict(groups), perf_counter() - started


def budget_tradeoff(results):
    alpha = results["quota:10/100/20"]
    deep = results["C:300"]
    recall_gain = 100 * (deep["candidate_recall@300"] - alpha["candidate_recall@100"])
    latency_ratio = deep["mean_retrieval_ms_per_labeled_query"] / alpha["mean_retrieval_ms_per_labeled_query"]
    return (f"The deepest measured configuration changed recall by {recall_gain:+.2f} percentage points "
            f"and used {latency_ratio:.2f} times the Alpha budget's mean retrieval latency.")


def run(directory, output, order=None):
    epoch = json.loads((directory / "evaluation_epoch.json").read_text())
    manifest = json.loads((directory / "data_manifest.json").read_text())
    if file_hash(directory / "sessions.jsonl") != manifest["artifacts"]["sessions.jsonl"]:
        raise ValueError("Session checksum mismatch")
    snapshot = Snapshot.load(directory)
    population = list(queries(directory, snapshot))
    base = RetrievalConfig(recent=100, covisitation=100, popularity=100)
    configs = {
        "+".join(combo): replace(base, **{source: 0 for source in SOURCES if source not in combo})
        for size in range(1, len(SOURCES) + 1) for combo in combinations(SOURCES, size)
    }
    configs.update({f"A:{mode}": replace(base, recent_mode=mode) for mode in ("repeat", "event_type")})
    configs.update({f"C:{cap}": replace(base, candidate_cap=cap, covisitation=cap, popularity=cap)
                    for cap in CAPS if cap != 100})
    configs["quota:10/100/20"] = replace(base, recent=10, popularity=20)
    results = {}
    for name, config in configs.items():
        results[name] = evaluate(population, snapshot, config, order)
        print(f"{name}: {results[name]['wall_seconds']:.1f}s", flush=True)
    groups, slice_seconds = slices(population, snapshot)
    total_labeled = sum(row["labeled"] for name, row in groups.items() if name.startswith("Length"))
    total_hits = sum(row["retrieved"] for name, row in groups.items() if name.startswith("Length"))
    if epoch["source"] == "otto_offline" and (total_labeled, total_hits) != (54776, 5591):
        raise ValueError("Run did not reproduce the signed-off W2-dev baseline")
    ordering = "rule-v1" if order else "deterministic retrieval order (interim)"
    header = protocol(snapshot, directory, ordering)
    rule_flag = " --rule" if order else ""
    header.update(platform=platform.platform(), command=f"python -m rankflow.study {directory} {output}{rule_flag}")
    if order:
        for result in results.values():
            result["rule-v1 HitRate@20"] = result["pre-rank hit rate@20"]
    markdown = ["", "## W2-dev boundary-exclusion follow-up", "",
                "Slices use the full retained session for diagnosis. Ranking uses only the prefix. "
                "The pinned Stage 0 co-visitation path supplies recall for this table.", "",
                "| Slice | Sessions | Queries | Labeled | Label yield | Pinned candidate_recall@100 |",
                "|---|---:|---:|---:|---:|---:|"]
    for name, row in sorted(groups.items()):
        recall = row["candidate_recall@100"]
        markdown.append(f"| {name} | {row['sessions']:,} | {row['queries']:,} | {row['labeled']:,} | "
                        f"{row['label_yield']:.2%} | {recall:.2%} |" if recall is not None else
                        f"| {name} | {row['sessions']:,} | {row['queries']:,} | {row['labeled']:,} | {row['label_yield']:.2%} | — |")
    markdown += ["", f"Reproduced the pinned baseline with {total_hits:,} hits across {total_labeled:,} "
                 f"labeled queries ({total_hits / total_labeled:.4%}). Slice computation took {slice_seconds:.3f}s.",
                 "", "The Stage 0 sign-off documents the wider boundary-excluded population. "
                 "The table measures label yield and retrieval coverage within retained W2-dev sessions."]
    chosen = results["quota:10/100/20"]
    full = results["recent+covisitation+popularity"]
    pair = results["recent+covisitation"]
    markdown += ["", "## Alpha retrieval budget", "",
                 "Use plain recency with a 100-candidate cap, 10 recent items, up to 100 co-visitation "
                 "candidates and 20 popularity candidates. The popularity backstop can fill the cap "
                 "when prefix items have no neighbours. "
                 f"This budget delivered {chosen['candidate_recall@100']:.4%} recall versus "
                 f"{full['candidate_recall@100']:.4%} with full popularity depth and "
                 f"{pair['candidate_recall@100']:.4%} for recent plus co-visitation. "
                 "It preserves the three-source design and the initial request budget. "
                 "Experiment A changes recent ordering within the short prefixes. "
                 "Experiment C varies the union cap and truncates individual source lists at that depth. "
                 "The formal recall/latency trade-off is reserved for Stage 2.", "", budget_tradeoff(results)]
    if order:
        markdown += ["", "## Rule-strategy ablation", "", "| Variant | End-to-end rule-v1 HitRate@20 |",
                     "|---|---:|"]
        markdown += [f"| {name} | {result['rule-v1 HitRate@20']:.4%} |" for name, result in results.items()]
    write_report(output, {"protocol": header, "variants": results, "baseline_slices": groups,
                          "slice_wall_seconds": slice_seconds, "markdown": markdown})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--rule", action="store_true")
    args = parser.parse_args()
    order = None
    if args.rule:
        from .strategies import rule_order
        order = rule_order
    run(args.directory, args.output, order)


if __name__ == "__main__":
    main()
