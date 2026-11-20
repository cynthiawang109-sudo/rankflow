"""Write Stage 0 sign-off evidence from the governed run (run from repo root)."""
from collections import Counter
from math import ceil
from pathlib import Path
from statistics import mean, median
from time import perf_counter

from rankflow.data.ingestion import assign_window, file_hash, read_rows
from rankflow.data.pipeline import read_json, save_json


def distribution(values):
    ordered = sorted(values)
    return {
        "mean": mean(ordered),
        "median": median(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        **{f"p{p}": ordered[ceil(len(ordered) * p / 100) - 1]
           for p in (25, 75, 90, 95, 99)},
    }


def summarize(counts, durations, event_types, repeats, short_max):
    sessions, events = len(counts), sum(counts)
    long = sum(count > short_max for count in counts)
    above_100 = sum(count > 100 for count in counts)
    return {
        "sessions": sessions,
        "events": events,
        "event_count": distribution(counts),
        "duration_ms": distribution(durations),
        "long_sessions": {"count": long, "share": long / sessions},
        "sessions_above_100_events": {"count": above_100, "share": above_100 / sessions},
        "event_types": {kind: {"count": count, "share": count / events}
                        for kind, count in event_types.items()},
        "repeat_item_events": {"count": repeats, "share": repeats / events},
    }


def main():
    run_path = Path("docs/data_validation_report_real.json")
    manifest_path = Path("artifacts/stage0-otto/data_manifest.json")
    sessions_path = manifest_path.with_name("sessions.jsonl")
    run = read_json(run_path)
    manifest = read_json(manifest_path)
    config = manifest["configuration"]
    short_max = config["short_session_max_events"]
    started = perf_counter()
    digest = file_hash(sessions_path)
    if digest != run["artifact_hashes"]["sessions.jsonl"]:
        raise ValueError("Session artifact differs from the verified run")

    counts = {"kept": [], "boundary_excluded": []}
    durations = {group: [] for group in counts}
    event_types = {group: Counter() for group in counts}
    repeats = Counter()
    for row in read_rows(sessions_path):
        events = row["events"]
        window, crossed = assign_window(events, manifest["windows"])
        if not window and not crossed:
            raise ValueError("Expected zero sessions outside all windows")
        group = "boundary_excluded" if crossed else "kept"
        counts[group].append(len(events))
        durations[group].append(events[-1]["ts"] - events[0]["ts"])
        event_types[group].update(event["type"] for event in events)
        repeats[group] += len(events) - len({event["aid"] for event in events})

    groups = {group: summarize(counts[group], durations[group], event_types[group],
                               repeats[group], short_max)
              for group in counts}
    elapsed = perf_counter() - started
    for group, expected in (
        ("kept", run["window_counts"].values()),
        ("boundary_excluded", run["crossing_exclusions_by_length"].values()),
    ):
        expected = list(expected)
        for key in ("sessions", "events"):
            if groups[group][key] != sum(row[key] for row in expected):
                raise ValueError(f"{group} {key} disagree with the verified run")
    if groups["boundary_excluded"]["long_sessions"]["count"] != (
        run["crossing_exclusions_by_length"]["long"]["sessions"]
    ):
        raise ValueError("Long-session exclusions disagree with the verified run")

    partitions = {}
    for partition, coverage in run["query_coverage"].items():
        retrieved = coverage["retrieved_positive"]
        all_negative = coverage["unretrieved_positive"]
        labeled = retrieved + all_negative
        if labeled + coverage["no_label"] != coverage["queries"]:
            raise ValueError(f"Query accounting differs for {partition}")
        partitions[partition] = {
            **run["window_counts"][partition],
            "eligible_prefixes": coverage["queries"],
            "labeled_next_click_queries": labeled,
            "no_label_queries": coverage["no_label"],
            "all_negative_queries": all_negative,
            "retrieved_positive": retrieved,
            "candidate_recall_at_cap": retrieved / labeled,
        }
    save_json(Path("docs/stage0_data_quality_report.json"), {
        "inputs": {
            "run_report": run_path.as_posix(),
            "data_manifest": manifest_path.as_posix(),
            "session_artifact": sessions_path.as_posix(),
            "session_artifact_sha256": digest,
        },
        "sampled_sessions": run["sampled_session_count"],
        "sampler": run["sampler"],
        "outside_windows": run["outside_windows"],
        "short_session_max_events": short_max,
        "recomputed_groups": groups,
        "recompute_wall_seconds_including_artifact_hash": round(elapsed, 3),
        "query_configuration": config["queries"],
        "label_policy_version": config["label_policy_version"],
        "candidate_source": run["coverage_scope"],
        "retrieval_snapshot": run["retrieval"],
        "partitions": partitions,
        "total_queries": sum(row["eligible_prefixes"] for row in partitions.values()),
        "disposition": "proceed to Stage 1 with a registered follow-up data-quality investigation",
    })


if __name__ == "__main__":
    main()
