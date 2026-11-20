"""Streaming session ingestion and stable sampling."""
import hashlib
import heapq
import json
from collections import Counter


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stable_hash(seed, session_id):
    return hashlib.sha256(f"{seed}:{session_id}".encode("utf-8")).hexdigest()


def write_row(stream, row):
    stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def read_rows(path):
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            try:
                yield json.loads(line)
            except ValueError as error:
                raise ValueError(f"{path}:{number}: invalid JSON") from error


def load_sessions(path):
    for row in read_rows(path):
        session_id = row["session"]
        if type(session_id) is not int or not row["events"]:
            raise ValueError(f"Invalid session ID or empty events: {session_id}")
        for event in row["events"]:
            if (type(event["aid"]) is not int or type(event["ts"]) is not int
                    or event["type"] not in {"clicks", "carts", "orders"}):
                raise ValueError(f"Invalid event in session {session_id}")
        # Python's stable sort preserves original order on ties.
        events = [
            {**event, "event_index": index}
            for index, event in enumerate(sorted(row["events"], key=lambda event: event["ts"]))
        ]
        yield session_id, events


def sample_ids(path, *, seed, cap):
    if cap < 1:
        raise ValueError("Sampler cap must be positive")
    selected = heapq.nsmallest(
        cap,
        ((stable_hash(seed, session_id), session_id) for session_id, _ in load_sessions(path)),
    )
    ids = sorted(session_id for _, session_id in selected)
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate sampled session ID")
    return ids


def check_windows(windows):
    names = ("W0", "W1", "W2", "W3")
    if set(windows) != set(names) or any(windows[name][0] >= windows[name][1] for name in names):
        raise ValueError("F05: windows must have valid ranges W0 through W3")
    if any(windows[left][1] != windows[right][0] for left, right in zip(names, names[1:])):
        raise ValueError("F05: windows must be consecutive and disjoint, ordered W0 through W3")


def assign_window(events, windows):
    first, last = events[0]["ts"], events[-1]["ts"]
    crossed = sorted({edge for bounds in windows.values() for edge in bounds
                      if first < edge <= last})
    if crossed:
        return None, crossed
    for name, (start, end) in windows.items():
        if start <= first <= last < end:
            return name, []
    return None, []


def validation_partition(session_id, *, seed, gate_percent):
    if not 0 < gate_percent < 100:
        raise ValueError("W2 gate percentage must be between 0 and 100")
    value = int(stable_hash(seed, session_id), 16)
    return "W2-gate" if value * 100 < (1 << 256) * gate_percent else "W2-dev"


def crossing_counts():
    return {bucket: Counter(sessions=0, events=0) for bucket in ("short", "long")}


def count_crossing(counts, session_length, short_max):
    bucket = "short" if session_length <= short_max else "long"
    counts[bucket].update(sessions=1, events=session_length)
