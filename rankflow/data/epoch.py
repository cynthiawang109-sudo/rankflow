"""Next-click query generation and evaluation epoch registration predicates."""
from dataclasses import dataclass

from .ingestion import assign_window, check_windows, stable_hash


@dataclass(frozen=True)
class EvaluationEpoch:
    epoch_id: str
    history_statistics_watermark: int
    training_data_watermark: int
    validation_window: tuple[int, int]
    final_test_window: tuple[int, int]
    retrieval_snapshot_id: str
    dataset_manifest_hash: str
    query_manifest_hash: str
    candidate_family: tuple[str, int, str]


def generate_queries(session_id, events, window, epoch_id, snapshot_id, source, config):
    settings = config["queries"]
    start = settings["min_prefix_length"] - 1
    limit = settings["max_cutoffs_per_session"]
    if start < 0 or limit < 1:
        raise ValueError("Query prefix length and cutoff cap must be positive")
    next_clicks = [None] * len(events)
    next_click = None
    for index in range(len(events) - 1, -1, -1):
        next_clicks[index] = next_click
        if events[index]["type"] == "clicks":
            next_click = events[index]
    for index in range(start, min(start + limit, len(events))):
        label = next_clicks[index]
        yield {
            "query_id": [session_id, index],
            "session_id_hash": stable_hash(config["sampler"]["seed"], session_id),
            "cutoff_event_index": index,
            "cutoff_ts": events[index]["ts"],
            "prefix_events": events[:index + 1],
            "positive_aid": label["aid"] if label else None,
            "label_event_index": label["event_index"] if label else None,
            "label_event_ts": label["ts"] if label else None,
            "epoch_id": epoch_id,
            "retrieval_snapshot_id": snapshot_id,
            "source": source,
            "label_policy_version": config["label_policy_version"],
            "window": window,
        }


def validate_epoch(epoch, windows, memberships, sessions, queries):
    """Validate against full sampled sessions, including excluded sessions.

    Sessions and queries are streamed in the same session order.
    """
    check_windows(windows)
    if (tuple(windows["W2"]) != tuple(epoch.validation_window)
            or tuple(windows["W3"]) != tuple(epoch.final_test_window)):
        raise ValueError("F05: epoch W2 and W3 ranges must match governed windows")
    if epoch.training_data_watermark >= windows["W2"][0]:
        raise ValueError("F05: training data watermark must precede W2 start")
    owners = {}
    for window, ids in memberships.items():
        for session_id in ids:
            if session_id in owners:
                raise ValueError("F05: governed session memberships must be pairwise disjoint")
            owners[session_id] = window
    pending = next(queries, None)
    for session_id, events in sessions:
        owner = owners.pop(session_id, None)
        window, crossed = assign_window(events, windows)
        if crossed and owner:
            raise ValueError("F05: window-crossing session must be excluded")
        base = owner.split("-")[0] if owner else None
        if window != base:
            raise ValueError("F05: session membership must match its chronological window")
        if window == "W0" and events[-1]["ts"] > epoch.history_statistics_watermark:
            raise ValueError("F05: snapshot watermark must bound every snapshot event")
        if window == "W1" and events[-1]["ts"] > epoch.training_data_watermark:
            raise ValueError("F05: training watermark must bound every W1 event")
        previous = -1
        while pending and pending["query_id"][0] == session_id:
            if window not in {"W1", "W2", "W3"} or pending["window"] != owner:
                raise ValueError("F05: query membership must match its governed session")
            index = pending["cutoff_event_index"]
            if (not previous < index < len(events) or pending["query_id"] != [session_id, index]
                    or pending["cutoff_ts"] != events[index]["ts"]
                    or pending["prefix_events"] != events[:index + 1]):
                raise ValueError("R21: query identity and prefix must match the cutoff event index")
            previous = index
            if (pending["epoch_id"] != epoch.epoch_id
                    or pending["retrieval_snapshot_id"] != epoch.retrieval_snapshot_id):
                raise ValueError("R22: query must reference its registered epoch and pinned snapshot")
            if epoch.history_statistics_watermark >= pending["cutoff_ts"]:
                raise ValueError("F05: snapshot watermark must be strictly before query cutoff")
            label_ts = pending["label_event_ts"]
            if window == "W1" and label_ts is not None and label_ts >= windows["W2"][0]:
                raise ValueError("F05: W1 label event time must be strictly before W2 start")
            label = next((event for event in events[index + 1:] if event["type"] == "clicks"), None)
            actual = (pending["positive_aid"], pending["label_event_index"], label_ts)
            expected = (label["aid"], label["event_index"], label["ts"]) if label else (None,) * 3
            if actual != expected:
                raise ValueError("F05: label must be the first click strictly after cutoff event index")
            pending = next(queries, None)
    if pending is not None or owners:
        raise ValueError("F05: query or window membership references an unregistered session")
