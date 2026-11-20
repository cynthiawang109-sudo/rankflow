"""Replay a candidate generation over governed historical development queries."""
import argparse
from pathlib import Path

from .api import rank_request
from .evaluate_retrieval import queries
from .generation import Generation
from .training_pipeline import canonical, pinned_inputs


def replay(directory, stable, challenger, limit):
    _, _, _, snapshot, _ = pinned_inputs(directory)
    compared = identical = 0
    for query, _ in queries(directory, snapshot):
        events = query["prefix_events"]
        if events[-1]["ts"] <= max(stable.snapshot.watermark, challenger.snapshot.watermark):
            continue
        left, _ = rank_request(stable, events, 20, float("inf"))
        right, _ = rank_request(challenger, events, 20, float("inf"))
        identical += [item["aid"] for item in left["items"]] == [item["aid"] for item in right["items"]]
        compared += 1
        if compared == limit:
            break
    return {"mode": "candidate_offline_replay", "validation": "synthetic operational validation",
            "population": "W2-dev", "source": "otto_offline", "queries_compared": compared,
            "identical_rankings": identical, "stable_generation": stable.generation_id,
            "challenger_generation": challenger.generation_id}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("directory", "stable", "challenger", "output"):
        parser.add_argument(argument, type=Path)
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("Replay limit must be positive")
    result = replay(args.directory, Generation.load(args.stable), Generation.load(args.challenger), args.limit)
    with args.output.open("xb") as stream:
        stream.write(canonical(result) + b"\n")


if __name__ == "__main__":
    main()
