"""Assemble a content-addressed Stage 0 run and replay its query manifest."""
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from .epoch import EvaluationEpoch, generate_queries, validate_epoch
from .ingestion import (
    assign_window, check_windows, count_crossing, crossing_counts, file_hash, load_sessions,
    read_rows, sample_ids, validation_partition, write_row,
)
from .retrieval import DiskBudgetExceeded, build_snapshot, candidate_inputs

FIXTURE = Path("tests/fixtures/synthetic_otto.jsonl")
PARTITIONS = ("W0", "W1", "W2-dev", "W2-gate", "W3")


def save_json(path, obj):
    path.write_bytes((json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def read_json(path):
    return json.loads(path.read_bytes())


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def partition(source_path, selected, config, windows, directory, source):
    memberships = {window: [] for window in PARTITIONS}
    counts = {window: Counter(sessions=0, events=0) for window in PARTITIONS}
    lengths = crossing_counts()
    boundaries = Counter()
    outside = Counter(sessions=0, events=0)
    seen = set()
    watermarks = {}
    with ExitStack() as stack:
        def open_output(name):
            return stack.enter_context((directory / name).open("w", encoding="utf-8", newline="\n"))

        all_rows = open_output("sessions.jsonl")
        history = open_output("history.jsonl")
        for session_id, events in load_sessions(source_path):
            if session_id not in selected:
                continue
            if session_id in seen:
                raise ValueError(f"Duplicate session ID: {session_id}")
            seen.add(session_id)
            window, crossed = assign_window(events, windows)
            if window == "W2":
                window = validation_partition(session_id, **config["validation_split"])
            row = {"session": session_id, "events": events, "window": window, "source": source}
            write_row(all_rows, row)
            if window:
                memberships[window].append(session_id)
                counts[window].update(sessions=1, events=len(events))
                watermarks[window] = max(watermarks.get(window, events[-1]["ts"]), events[-1]["ts"])
            if window == "W0":
                write_row(history, row)
            if crossed:
                count_crossing(lengths, len(events), config["short_session_max_events"])
                boundaries.update(map(str, crossed))
            elif window is None:
                outside.update(sessions=1, events=len(events))
    if seen != selected:
        raise ValueError("Selected session IDs changed during ingestion")
    return memberships, counts, lengths, boundaries, outside, watermarks


def session_events(path):
    for row in read_rows(path):
        yield row["session"], row["events"]


def emit_queries(sessions, output, config, snapshot_id):
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for row in read_rows(sessions):
            if row["window"] in PARTITIONS[1:]:
                for query in generate_queries(
                    row["session"], row["events"], row["window"], config["epoch_id"],
                    snapshot_id, row["source"], config,
                ):
                    write_row(stream, query)


def replay_queries(directory, output, config):
    manifest = read_json(directory / "data_manifest.json")
    if config_hash(config) != manifest["configuration_sha256"]:
        raise ValueError("Replay configuration does not match manifest")
    for name, expected in manifest["artifacts"].items():
        if file_hash(directory / name) != expected:
            raise ValueError(f"Artifact hash mismatch: {name}")
    if output.exists():
        raise FileExistsError(output)
    emit_queries(directory / "sessions.jsonl", output, config, manifest["retrieval_snapshot_id"])
    if file_hash(output) != manifest["artifacts"]["queries.jsonl"]:
        output.unlink()
        raise ValueError("Replayed queries do not match manifest")


def coverage(directory, cap):
    """Count positive coverage for the Stage 0 co-visitation table."""
    stats = {window: Counter(queries=0, retrieved_positive=0, unretrieved_positive=0, no_label=0)
             for window in PARTITIONS[1:]}
    with (directory / "covisitation.jsonl").open("rb") as table:
        offsets = {}
        while line := table.readline():
            aid = json.loads(line)["aid"]
            offsets.setdefault(aid, table.tell() - len(line))

        def neighbours(aid):
            if aid in offsets:
                table.seek(offsets[aid])
                while line := table.readline():
                    row = json.loads(line)
                    if row["aid"] != aid:
                        break
                    yield row["neighbour_aid"]

        for query in read_rows(directory / "queries.jsonl"):
            count = stats[query["window"]]
            count["queries"] += 1
            positive = query["positive_aid"]
            if positive is None:
                count["no_label"] += 1
            elif positive in candidate_inputs(query, neighbours, cap):
                count["retrieved_positive"] += 1
            else:
                count["unretrieved_positive"] += 1
    return stats


def build_run(source_path, output, config, profile="fixture", download_manifest=None):
    if output.exists():
        raise FileExistsError(output)
    source = {"fixture": "synthetic_fixture", "otto": "otto_offline"}[profile]
    source_hash = file_hash(source_path)
    download_status = "Full OTTO download deferred. No OTTO run was performed."
    if profile == "otto":
        download = read_json(download_manifest) if download_manifest else {}
        if (download.get("source") != source or source_path.name != "train.jsonl"
                or download.get("files", {}).get("train.jsonl") != source_hash
                or (FIXTURE.exists() and file_hash(FIXTURE) == source_hash)):
            raise ValueError("OTTO runs require the verified train.jsonl from scripts/fetch_data")
        download_status = "OTTO download verified against the fetch manifest."
    windows = config["windows"][profile]
    check_windows(windows)
    selected = sample_ids(source_path, **config["sampler"])
    output.parent.mkdir(parents=True, exist_ok=True)
    # Temporary staging keeps an interrupted or failed run from publishing artifacts.
    with TemporaryDirectory(dir=output.parent) as temp:
        directory = Path(temp)
        members, counts, lengths, boundaries, outside, marks = partition(
            source_path, set(selected), config, windows, directory, source,
        )
        if file_hash(source_path) != source_hash:
            raise ValueError("Source changed during ingestion")
        if not members["W0"]:
            raise ValueError("At least one W0 session is required for a statistics watermark")
        history = directory / "history.jsonl"
        try:
            retrieval = build_snapshot(session_events(history), directory, config["retrieval"], source)
        except DiskBudgetExceeded:
            output.mkdir()
            (directory / "disk_budget_abort.json").replace(output / "disk_budget_abort.json")
            raise
        table_hash = file_hash(directory / "covisitation.jsonl")
        snapshot_id = config_hash({
            "history_sha256": file_hash(history), "configuration": config["retrieval"],
            "table_sha256": table_hash, "source": source,
        })
        retrieval.update(
            retrieval_snapshot_id=snapshot_id, source_sha256=source_hash,
            table_sha256=table_hash, history_statistics_watermark=marks["W0"],
        )
        save_json(directory / "retrieval_manifest.json", retrieval)
        queries = directory / "queries.jsonl"
        emit_queries(directory / "sessions.jsonl", queries, config, snapshot_id)
        query_stats = coverage(directory, config["retrieval"]["candidate_cap"])
        artifacts = {path.name: file_hash(path) for path in directory.iterdir()}
        manifest = {
            "version": config["manifest_version"], "source": source, "source_sha256": source_hash,
            "configuration_sha256": config_hash(config), "configuration": config,
            "windows": windows, "memberships": members, "counts": counts,
            "selected_session_ids": selected, "sampler": config["sampler"],
            "validation_split": config["validation_split"],
            "crossing_exclusions_by_length": lengths, "crossing_sessions_by_boundary": boundaries,
            "outside_windows": outside, "retrieval_snapshot_id": snapshot_id,
            "retrieval": config["retrieval"], "artifacts": artifacts,
            "query_coverage": query_stats,
            "cutoff_selection": "First eligible positions in increasing event_index order",
        }
        manifest_path = directory / "data_manifest.json"
        save_json(manifest_path, manifest)
        epoch = EvaluationEpoch(
            config["epoch_id"], marks["W0"], marks.get("W1", windows["W1"][0] - 1), tuple(windows["W2"]),
            tuple(windows["W3"]), snapshot_id, file_hash(manifest_path), file_hash(queries),
            tuple(config["candidate_family"]),
        )
        validate_epoch(
            epoch, windows, members, session_events(directory / "sessions.jsonl"), read_rows(queries),
            crossing_exclusions=lengths, short_session_max_events=config["short_session_max_events"],
        )
        save_json(directory / "evaluation_epoch.json", {"source": source, **asdict(epoch)})
        # Publish atomically from the same volume once registration succeeds.
        directory.replace(output)
    return manifest, retrieval, download_status


def read_config(path):
    return yaml.safe_load(path.read_bytes())
