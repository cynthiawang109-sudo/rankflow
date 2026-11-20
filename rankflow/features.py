"""The shared point-in-time feature builder for replay and serving."""
from pathlib import Path

from .data.ingestion import file_hash
from .retrieval import SOURCES

FEATURE_VERSION = "session-features-v1"
FEATURE_NAMES = (
    "prefix_frequency", "last_seen_age_ms", "last_seen_missing", "last_clicks",
    "last_carts", "last_orders", "covisitation_score", "has_covisitation",
    "candidate_known_without_neighbours", "popularity_rank", "popularity_missing",
    "candidate_is_unknown_item", "session_length", "prior_clicks", "prior_carts",
    "prior_orders", *(name for source in SOURCES for name in (f"source_{source}", f"rank_{source}")),
)


def feature_code_hash():
    return file_hash(Path(__file__))


def build_features(snapshot, events, candidates):
    cutoff = events[-1]["ts"] if events else 0
    if events and cutoff <= snapshot.watermark:
        raise ValueError("History snapshot must strictly precede the cutoff")
    prior = {}
    co = {}
    for event in events:
        aid = event["aid"]
        if aid not in snapshot.popularity_ranks:
            continue
        state = prior.setdefault(aid, [0, 0, 0, event])
        state[("clicks", "carts", "orders").index(event["type"])] += 1
        state[3] = event
    candidate_ids = {candidate.aid for candidate in candidates}
    for aid in prior:
        for other, count in snapshot.neighbours.get(aid, ()):
            if other in candidate_ids:
                co[other] = max(count, co.get(other, 0))
    rows = []
    for candidate in candidates:
        aid = candidate.aid
        clicks, carts, orders, last = prior.get(aid, (0, 0, 0, None))
        popularity = snapshot.popularity_ranks.get(aid, 0)
        covisitation = co.get(aid, 0)
        rows.append((
            clicks + carts + orders, cutoff - last["ts"] if last else 0, int(last is None),
            *(int(last is not None and last["type"] == kind) for kind in ("clicks", "carts", "orders")),
            covisitation, int(aid in co), int(bool(popularity) and not snapshot.neighbours.get(aid)),
            popularity, int(not popularity), int(not popularity), len(events), clicks, carts, orders,
            *(value for rank in candidate.ranks for value in (int(bool(rank)), rank)),
        ))
    return rows
