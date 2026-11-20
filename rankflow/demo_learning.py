"""Rehearse the generated-list learning loop in the demo namespace."""
import argparse
from collections import defaultdict
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from .features import FEATURE_NAMES, FEATURE_VERSION, build_features, feature_code_hash
from .generation import Generation
from .release_gate import append_signed
from .store import PostgresStore
from .strategies import LIGHTGBM_CONFIG
from .training_pipeline import canonical
from .data.ingestion import file_hash


def collect(store, generation):
    with store.connect() as conn:
        return conn.execute("""
            SELECT DISTINCT ON (f.impression_id) f.event_id, f.impression_id,
                   f.payload, d.payload AS decision
            FROM feedback_events f JOIN decisions d USING (impression_id)
            WHERE f.payload->>'action' = 'click' AND f.payload->>'attributed' = 'true'
              AND d.payload->>'source' = 'demo' AND d.payload->>'serving_generation' = %s
              AND d.payload ? 'prefix_events'
              AND (NOT (f.payload ? 'source') OR f.payload->>'source' = 'demo')
            ORDER BY f.impression_id, f.occurred_at, f.event_id
            """, (generation.generation_id,)).fetchall()


def dataset(events, generation):
    examples = []
    for row in events:
        decision, feedback = row["decision"], row["payload"]
        if decision.get("source") != "demo" or not feedback.get("attributed"):
            continue
        displayed = decision["items"]
        if not any(item["aid"] == feedback["aid"] for item in displayed):
            continue
        examples.append({
            "source": "demo", "event_id": row["event_id"], "impression_id": row["impression_id"],
            "session_hash": decision["session_hash"], "prefix_events": decision["prefix_events"],
            "target": feedback["aid"], "displayed": [item["aid"] for item in displayed],
            "confirmation_state": feedback["confirmation_state"], "occurred_at": feedback["occurred_at"],
        })
    return {"source": "demo", "label_policy_version": "demo-generated-list-v1",
            "generation_id": generation.generation_id, "examples": examples}


def rehearse(store, generation, registry, signing_key):
    import lightgbm
    import numpy as np

    from .retrieval import retrieve
    from .train import credits

    data = dataset(collect(store, generation), generation)
    dataset_id = hashlib.sha256(canonical(data)).hexdigest()
    groups = defaultdict(list)
    for example in data["examples"]:
        groups[example["session_hash"]].append(example)
    sessions = sorted(groups)
    if len(sessions) < 2:
        raise ValueError("Rehearsal needs attributed clicks from at least two demo sessions")
    rows, labels, sizes = [], [], []
    held_out = []
    for index, session in enumerate(sessions):
        for example in groups[session]:
            events = example["prefix_events"]
            displayed = set(example["displayed"])
            candidates = [candidate for candidate in retrieve(generation.snapshot, events, generation.config)
                          if candidate.aid in displayed]
            positive = [int(candidate.aid == example["target"]) for candidate in candidates]
            features = build_features(generation.snapshot, events, candidates)
            if index % 2:
                held_out.append((candidates, features, example["target"]))
            elif any(positive):
                rows.extend(features)
                labels.extend(positive)
                sizes.append(len(positive))
    if not sizes or not held_out:
        raise ValueError("Demo training and evaluation require usable groups")
    model = lightgbm.LGBMRanker(**LIGHTGBM_CONFIG)
    model.fit(np.asarray(rows, dtype=np.float32), np.asarray(labels), group=sizes,
              feature_name=list(FEATURE_NAMES))
    outcomes = []
    for candidates, features, target in held_out:
        scores = model.predict(np.asarray(features, dtype=np.float32)) if features else []
        ranking = [candidate.aid for candidate, _ in sorted(zip(candidates, scores),
                   key=lambda pair: (-pair[1], pair[0].aid))]
        outcomes.append(credits(ranking, target))
    registry.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=registry) as workspace:
        staging = Path(workspace) / "rehearsal"
        staging.mkdir()
        artifact = staging / "demo-lgbm.txt"
        model.booster_.save_model(str(artifact))
        lineage = {
            "source": "demo", "status": "demo-trained", "data_manifest_sha256": dataset_id,
            "label_policy_version": data["label_policy_version"],
            "feature_schema": FEATURE_VERSION, "feature_code_sha256": feature_code_hash(),
            "retrieval_snapshot_id": generation.snapshot.snapshot_id, "artifact_sha256": file_hash(artifact),
            "training_configuration": LIGHTGBM_CONFIG, "random_seed": LIGHTGBM_CONFIG["random_state"],
            "evaluation_protocol_version": "demo-session-holdout-v1",
        }
        lineage["run_id"] = hashlib.sha256(canonical(lineage)).hexdigest()
        evaluation = {"source": "demo", "labeled": len(outcomes), "metrics": dict(zip(
            ("HitRate@20", "MRR@20", "NDCG@20"), (sum(column) / len(outcomes) for column in zip(*outcomes))))}
        (staging / "dataset.json").write_bytes(canonical(data) + b"\n")
        (staging / "run.json").write_bytes(canonical({"lineage": lineage, "evaluation": evaluation}) + b"\n")
        append_signed(staging / "decision.json", {
            "lineage": lineage, "evaluation": evaluation, "decision": "rejected",
            "reason": "Demo provenance is ineligible for the OTTO gate",
            "validation": "synthetic operational validation",
        }, signing_key)
        target = registry / lineage["run_id"]
        if target.exists():
            if (target / "run.json").read_bytes() != (staging / "run.json").read_bytes():
                raise ValueError("Demo registry contains different evidence for the same run")
        else:
            staging.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generation", type=Path)
    parser.add_argument("demo_registry", type=Path)
    args = parser.parse_args()
    signing_key = os.environ["RANKFLOW_RELEASE_SIGNING_KEY"].encode()
    if len(signing_key) < 32:
        parser.error("Release signing key must contain at least 32 bytes")
    print(rehearse(PostgresStore(os.environ["RANKFLOW_DATABASE_URL"]), Generation.load(args.generation),
                   args.demo_registry, signing_key))


if __name__ == "__main__":
    main()
