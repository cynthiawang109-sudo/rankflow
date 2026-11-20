"""Immutable evaluation epoch registration."""
from psycopg.types.json import Jsonb

SCHEMA = """
CREATE TABLE IF NOT EXISTS evaluation_epochs (
    epoch_id TEXT PRIMARY KEY, manifest JSONB NOT NULL,
    registered_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
"""


def register_epoch(store, epoch):
    required = {"epoch_id", "source", "history_statistics_watermark", "training_data_watermark",
                "validation_window", "final_test_window", "retrieval_snapshot_id",
                "dataset_manifest_hash", "query_manifest_hash", "candidate_family"}
    if not required <= epoch.keys() or epoch["source"] not in {"otto_offline", "demo"}:
        raise ValueError("Invalid epoch manifest")
    val_start, val_end = epoch["validation_window"]
    final_start, final_end = epoch["final_test_window"]
    history = epoch["history_statistics_watermark"]
    training = epoch["training_data_watermark"]
    if not history <= training < val_start < val_end <= final_start < final_end:
        raise ValueError("Epoch watermarks and windows overlap")
    with store.connect() as conn:
        conn.execute("LOCK TABLE evaluation_epochs IN SHARE ROW EXCLUSIVE MODE")
        existing = conn.execute("SELECT manifest FROM evaluation_epochs").fetchall()
        for row in existing:
            prior = row["manifest"]
            if prior["epoch_id"] == epoch["epoch_id"]:
                if prior == epoch:
                    return False
                raise ValueError("Epoch ID already identifies an immutable manifest")
            if prior["source"] == epoch["source"]:
                old_start = prior["validation_window"][0]
                old_end = prior["final_test_window"][1]
                if val_start < old_end and old_start < final_end:
                    raise ValueError("Evaluation windows overlap a registered epoch")
        conn.execute("INSERT INTO evaluation_epochs(epoch_id, manifest) VALUES (%s, %s)",
                     (epoch["epoch_id"], Jsonb(epoch)))
    return True
