"""Versioned deterministic and LightGBM ranking strategies."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from .data.ingestion import file_hash
from .features import FEATURE_VERSION, build_features

RULE_CONFIG = {"recency": 2, "repeat": 1, "event_type": .25, "covisitation": 3, "popularity": 1}
LIGHTGBM_CONFIG = {
    "objective": "lambdarank", "n_estimators": 50, "learning_rate": .1, "num_leaves": 15,
    "random_state": 42, "deterministic": True, "force_col_wise": True, "n_jobs": 2,
    "verbosity": -1, "label_gain": [0, 1],
}


def rule_scores(rows):
    weights = RULE_CONFIG
    return [
        weights["recency"] * (1 - row[2]) / (1 + row[1] / 60_000)
        + weights["repeat"] * row[0]
        + weights["event_type"] * (row[3] + 2 * row[4] + 3 * row[5])
        + weights["covisitation"] * row[6] / (1 + row[6])
        + weights["popularity"] / row[9] if row[9] else 0.0
        for row in rows
    ]


@dataclass(frozen=True)
class RankingStrategy:
    strategy_id: str
    strategy_type: str
    version: int
    status: str
    artifact_hash: str
    score: object
    feature_schema_version: str = FEATURE_VERSION

    def rank(self, candidates, rows):
        scores = self.score(rows) if rows else []
        if len(scores) != len(candidates):
            raise ValueError("Scorer did not return one score per candidate")
        return sorted(zip(candidates, map(float, scores)),
                      key=lambda result: (-result[1], result[0].aid))


RULE = RankingStrategy("rule-v1", "rule", 1, "active",
                       hashlib.sha256(json.dumps(RULE_CONFIG, sort_keys=True).encode()).hexdigest(),
                       rule_scores)


def load_model(path: Path, *, threads=2):
    import lightgbm
    import numpy as np

    model = lightgbm.Booster(model_file=str(path))
    return RankingStrategy("lgbm-v1", "lightgbm", 1, "evaluated", file_hash(path),
                           lambda rows: model.predict(np.asarray(rows, dtype=np.float32), num_threads=threads))


def rule_order(snapshot, events, candidates):
    return [candidate.aid for candidate, _ in RULE.rank(candidates, build_features(snapshot, events, candidates))]
