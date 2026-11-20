"""W2-dev retrieval evaluation with end-to-end labeled-query denominators."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

from .data.epoch import generate_queries
from .data.ingestion import file_hash
from .data.retrieval import peak_rss_bytes
from .retrieval import RetrievalConfig, Snapshot, SOURCES, retrieve

CAPS = (50, 100, 200, 300)
LABEL_POLICY = "nextclick-v1"


def governed_sessions(directory, window):
    if window not in {"W1", "W2-dev"}:
        raise ValueError("Only W1 and W2-dev are available")
    manifest = json.loads((directory / "data_manifest.json").read_text())
    members = set(manifest["memberships"][window])
    # The Stage 0 file is sorted JSON. Filter its final window field before decoding.
    suffix = ('"window":"' + window + '"}').encode()
    with (directory / "sessions.jsonl").open("rb") as stream:
        for line in stream:
            if line.rstrip().endswith(suffix):
                row = json.loads(line)
                if row["session"] not in members:
                    raise ValueError("Session is outside the manifest membership")
                yield row


def queries(directory, snapshot, window="W2-dev"):
    manifest = json.loads((directory / "data_manifest.json").read_text())
    epoch = json.loads((directory / "evaluation_epoch.json").read_text())
    config = manifest["configuration"]
    if config["label_policy_version"] != LABEL_POLICY:
        raise ValueError("Wrong label policy")
    for session in governed_sessions(directory, window):
        if session["events"][0]["ts"] <= snapshot.watermark:
            raise ValueError("Query overlaps the history snapshot")
        for query in generate_queries(session["session"], session["events"], window,
                                      epoch["epoch_id"], snapshot.snapshot_id,
                                      session["source"], config):
            yield query, session["events"]


def evaluate(population, snapshot, config, order=None):
    started = perf_counter()
    counts, sizes, overlap, targets, cold = (Counter() for _ in range(5))
    for query, _ in population:
        events, target = query["prefix_events"], query["positive_aid"]
        counts["queries"] += 1
        if target is None:
            counts["no_label"] += 1
            continue
        counts["labeled"] += 1
        known = [event for event in events if event["aid"] in snapshot.popularity_ranks]
        counts["prefix_events"] += len(events)
        counts["unknown_item_events"] += len(events) - len(known)
        if not events:
            cold["empty"] += 1
        elif not known:
            cold["all_unknown"] += 1
        elif not any(snapshot.neighbours.get(event["aid"]) for event in known):
            cold["no_neighbours"] += 1
        candidates = retrieve(snapshot, events, config)
        sizes[len(candidates)] += 1
        for candidate in candidates:
            sources = "+".join(source for source, rank in zip(SOURCES, candidate.ranks) if rank)
            overlap[sources] += 1
            if candidate.aid == target:
                targets[sources] += 1
                counts["retrieved"] += 1
        ordered = order(snapshot, events, candidates) if order else [c.aid for c in candidates]
        for k in (20, 50):
            counts[f"pre_rank_hits@{k}"] += target in ordered[:k]
    denominator = counts["labeled"]
    return {
        "configuration": asdict(config), "counts": dict(counts),
        f"candidate_recall@{config.candidate_cap}": counts["retrieved"] / denominator,
        **{f"pre-rank hit rate@{k}": counts[f"pre_rank_hits@{k}"] / denominator for k in (20, 50)},
        "candidate_count_distribution": dict(sizes), "source_overlap": dict(overlap),
        "target_source_overlap": dict(targets),
        "source_contribution": {source: sum(n for key, n in targets.items() if source in key.split("+"))
                                for source in SOURCES},
        "cold_start_cases": dict(cold), "cold_start_query_rate": sum(cold.values()) / denominator,
        "unknown_item_rate": counts["unknown_item_events"] / max(1, counts["prefix_events"]),
        "wall_seconds": perf_counter() - started, "peak_process_rss_bytes": peak_rss_bytes(),
    }


def protocol(snapshot, directory, ordering):
    return {
        "report_version": "retrieval-v1", "window": "W2-dev", "label_policy": LABEL_POLICY,
        "snapshot_id": snapshot.snapshot_id, "watermark": snapshot.watermark,
        "epoch": json.loads((directory / "evaluation_epoch.json").read_text()),
        "caps": CAPS, "ordering": ordering,
        "denominator": "Labeled queries, including retrieval misses. No-label queries counted separately.",
        "recall_definition": "Target membership anywhere in the capped candidate union.",
        "pre_rank_definition": "Target membership within ordered candidate depth.",
        "memory_definition": "Peak process resident memory through variant completion.",
    }


def write_report(output, report):
    output.parent.mkdir(parents=True, exist_ok=True)
    output.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    sections = ["# Retrieval evaluation", "", "## Protocol", ""]
    sections += [f"- **{key}** — {value}" for key, value in report["protocol"].items()]
    sections += ["", "| Variant | Cap | Candidate recall | Pre-rank hit rate@20 | Pre-rank hit rate@50 | Seconds | Peak RSS bytes |",
                 "|---|---:|---:|---:|---:|---:|---:|"]
    for name, result in report["variants"].items():
        cap = result["configuration"]["candidate_cap"]
        sections.append(f"| {name} | {cap} | {result[f'candidate_recall@{cap}']:.4%} | "
                        f"{result['pre-rank hit rate@20']:.4%} | {result['pre-rank hit rate@50']:.4%} | "
                        f"{result['wall_seconds']:.3f} | {result['peak_process_rss_bytes']:,} |")
    sections += ["", f"[Full metric breakdown]({output.with_suffix('.json').name})"]
    sections.extend(report.get("markdown", []))
    output.with_suffix(".md").write_text("\n".join(sections) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    snapshot = Snapshot.load(args.directory)
    manifest = json.loads((args.directory / "data_manifest.json").read_text())
    if file_hash(args.directory / "sessions.jsonl") != manifest["artifacts"]["sessions.jsonl"]:
        raise ValueError("Session checksum mismatch")
    write_report(args.output, {
        "protocol": protocol(snapshot, args.directory, "deterministic retrieval order"),
        "variants": {str(cap): evaluate(queries(args.directory, snapshot), snapshot,
                                        RetrievalConfig(candidate_cap=cap, covisitation=cap, popularity=cap))
                     for cap in CAPS},
    })


if __name__ == "__main__":
    main()

