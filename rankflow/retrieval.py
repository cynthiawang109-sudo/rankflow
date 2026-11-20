"""Deterministic retrieval from a governed W0 snapshot and an observed prefix."""
from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from types import MappingProxyType

from .data.ingestion import read_rows, file_hash
from .data.retrieval import candidate_inputs

SOURCES = ("recent", "covisitation", "popularity")
EVENT_WEIGHTS = {"clicks": 1, "carts": 2, "orders": 3}


@dataclass(frozen=True)
class RetrievalConfig:
    candidate_cap: int = 100
    recent: int = 100
    covisitation: int = 100
    popularity: int = 100
    top_n_per_item: int = 100
    recent_mode: str = "recency"

    def __post_init__(self):
        for name in (*SOURCES, "candidate_cap", "top_n_per_item"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name in SOURCES else 1):
                raise ValueError(f"Invalid {name}")
        if self.recent_mode not in {"recency", "repeat", "event_type"}:
            raise ValueError("Invalid recent mode")


@dataclass(frozen=True)
class Candidate:
    aid: int
    ranks: tuple[int, int, int]

    def provenance(self):
        return {source: {"present": bool(rank), "rank": rank or None}
                for source, rank in zip(SOURCES, self.ranks)}


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    watermark: int
    neighbours: dict
    popularity: tuple
    popularity_ranks: dict

    @classmethod
    def load(cls, directory):
        epoch = json.loads((directory / "evaluation_epoch.json").read_text())
        manifest_path = directory / "data_manifest.json"
        if file_hash(manifest_path) != epoch["dataset_manifest_hash"]:
            raise ValueError("Dataset manifest hash mismatch")
        manifest = json.loads(manifest_path.read_text())
        snapshot_id = epoch["retrieval_snapshot_id"]
        if manifest["retrieval_snapshot_id"] != snapshot_id:
            raise ValueError("Snapshot does not match epoch")
        for name in ("history.jsonl", "covisitation.jsonl"):
            if file_hash(directory / name) != manifest["artifacts"][name]:
                raise ValueError(f"Snapshot checksum mismatch for {name}")

        counts = Counter()
        watermark = epoch["history_statistics_watermark"]
        for row in read_rows(directory / "history.jsonl"):
            if row["window"] != "W0":
                raise ValueError("Statistics must come from W0")
            for event in row["events"]:
                if event["ts"] > watermark:
                    raise ValueError("Event beyond history watermark")
                counts[event["aid"]] += 1
        neighbours = defaultdict(list)
        for row in read_rows(directory / "covisitation.jsonl"):
            neighbours[row["aid"]].append((row["neighbour_aid"], row["count"]))
        popularity = tuple(sorted(counts, key=lambda aid: (-counts[aid], aid)))
        return cls(snapshot_id, watermark, MappingProxyType({
            aid: tuple(rows) for aid, rows in neighbours.items()
        }), popularity, MappingProxyType({aid: rank for rank, aid in enumerate(popularity, 1)}))

    def baseline(self, events, cap=100):
        return candidate_inputs({"prefix_events": events},
                                lambda aid: (other for other, _ in self.neighbours.get(aid, ())), cap)


def recent_items(events, mode):
    last = {}
    weights = Counter()
    for event in events:
        aid = event["aid"]
        last[aid] = event["ts"]
        weights[aid] += EVENT_WEIGHTS[event["type"]] if mode == "event_type" else 1
    return sorted(last, key=lambda aid: (
        -weights[aid] if mode != "recency" else 0, -last[aid], aid
    ))


def retrieve(snapshot, events, config):
    known = [event for event in events if event["aid"] in snapshot.popularity_ranks]
    recent = recent_items(known, config.recent_mode)[:config.recent] if config.recent else ()
    co = ()
    if config.covisitation and known:
        co = tuple(candidate_inputs(
            {"prefix_events": known},
            lambda aid: (other for other, _ in snapshot.neighbours.get(aid, ())[:config.top_n_per_item]),
            config.covisitation,
        ))
    has_neighbours = any(snapshot.neighbours.get(event["aid"]) for event in known)
    popularity_depth = config.popularity
    if popularity_depth and not has_neighbours:
        popularity_depth = max(popularity_depth, config.candidate_cap)
    rankings = recent, co, snapshot.popularity[:popularity_depth]
    ranks = [{aid: rank for rank, aid in enumerate(items, 1)} for items in rankings]
    # Interleave source ranks so every enabled source can contribute at bounded depth.
    union = dict.fromkeys(aid for offset in range(max(map(len, rankings)))
                          for items in rankings if offset < len(items)
                          for aid in (items[offset],))
    return [Candidate(aid, tuple(source.get(aid, 0) for source in ranks))
            for aid in list(union)[:config.candidate_cap]]
