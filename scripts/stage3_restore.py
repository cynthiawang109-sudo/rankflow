"""Exercise PostgreSQL backup and cold restore on two disposable Docker containers."""
from argparse import ArgumentParser
from dataclasses import asdict
from datetime import datetime, timezone
from hmac import compare_digest
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from rankflow.api import from_environment
from rankflow.security import signature
from rankflow.store import PostgresStore


TABLES = ("evaluation_epochs", "traffic_configs", "traffic_pointer", "traffic_audit",
          "admin_audit_log", "decisions", "feedback_events")


def docker_pg(container, *command, **streams):
    subprocess.run(["docker", "exec", "-i", container, *command], check=True, **streams)


def snapshot(store):
    with store.connect() as connection:
        return {table: connection.execute(sql.SQL("SELECT * FROM {} ORDER BY 1").format(
            sql.Identifier(table))).fetchall() for table in TABLES}


def exercise(args, database, root):
    from rankflow.traffic import TrafficConfigSnapshot

    registry = Path("artifacts/stage1/generations")
    stable_id = (registry / "alpha.txt").read_text().strip()
    stable = TrafficConfigSnapshot(stable_id)
    rescue, salts = root / "rescue.json", root / "salts.json"
    rescue.write_text(json.dumps(asdict(stable)))
    salts.write_text(json.dumps({"v1": uuid4().hex}))
    signing_key, admin = uuid4().hex, uuid4().hex
    headers = {"Authorization": f"Bearer {admin}"}
    source = make_conninfo(args.source_dsn, dbname=database)
    restored = make_conninfo(args.restore_dsn, dbname=database)
    settings = {"RANKFLOW_GENERATION": str(registry / stable_id), "RANKFLOW_RESCUE_CONFIG": str(rescue),
                "RANKFLOW_ROUTING_SALTS": str(salts), "RANKFLOW_SESSION_KEY": uuid4().hex,
                "RANKFLOW_RELEASE_SIGNING_KEY": signing_key, "RANKFLOW_ADMIN_BEARER": admin,
                "RANKFLOW_CONTROL_DATABASE_URL": ""}
    request = {"request_id": "backup-checkpoint", "session_id": "backup-fixture", "events": []}
    with patch.dict(os.environ, dict(settings, RANKFLOW_DATABASE_URL=source,
                                   RANKFLOW_ARTIFACT_CACHE=str(root / "source-cache"))):
        with TestClient(from_environment()) as client:
            epoch = {"epoch_id": "restore-fixture", "source": "otto_offline",
                     "history_statistics_watermark": 10, "training_data_watermark": 19,
                     "validation_window": [20, 30], "final_test_window": [30, 40],
                     "retrieval_snapshot_id": "fixture", "dataset_manifest_hash": "fixture",
                     "query_manifest_hash": "fixture", "candidate_family": ["LightGBM-LambdaRank", 1, "nextclick-v1"]}
            client.post("/operator/epochs", json=epoch, headers=headers).raise_for_status()
            client.post("/operator/traffic/publish", headers=headers, json={
                "operation_id": "backup-stable", "expected_revision": 0,
                "configuration": dict(asdict(stable), state="shadowing"),
            }).raise_for_status()
            recommendation = client.post("/v1/recommend", json=request).raise_for_status().json()
            client.post("/v1/feedback", json={
                "event_id": "backup-checkpoint", "impression_id": recommendation["impression_id"],
                "action": "click", "source": "demo", "aid": recommendation["items"][0]["aid"],
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }).raise_for_status()
            checkpoint = monotonic()
            expected = snapshot(PostgresStore(source))
            assert all(expected.values())
            archive = root / "rankflow.dump"
            with archive.open("wb") as output:
                docker_pg(args.source_container, "pg_dump", "-U", "postgres", "-Fc", database, stdout=output)
            # Leave one additional committed decision outside the backup.
            client.post("/v1/recommend", json=dict(request, request_id="after-backup")).raise_for_status()
            outage = monotonic()
            assert len(snapshot(PostgresStore(source))["decisions"]) == len(expected["decisions"]) + 1
    with archive.open("rb") as backup:
        docker_pg(args.restore_container, "pg_restore", "-U", "postgres", "--exit-on-error",
                  "--single-transaction", "-d", database, stdin=backup)
    recovered = snapshot(PostgresStore(restored))
    assert recovered == expected
    for audit in recovered["admin_audit_log"]:
        assert compare_digest(audit["signature"], signature(signing_key.encode(), audit["record"]))
    for audit in recovered["traffic_audit"]:
        assert any(signed["record"]["subject"] == {
            "operation_id": audit["operation_id"], "config_id": audit["config_id"], "revision": audit["revision"],
        } for signed in recovered["admin_audit_log"])
    clean_registry = root / "restored-generations"
    shutil.copytree(registry / stable_id, clean_registry / stable_id)
    with patch.dict(os.environ, dict(settings, RANKFLOW_DATABASE_URL=restored,
                                   RANKFLOW_GENERATION=str(clean_registry / stable_id),
                                   RANKFLOW_ARTIFACT_CACHE=str(root / "restore-cache"))):
        with TestClient(from_environment()) as client:
            assert client.get("/health/ready").raise_for_status().json()["serving_ready"]
            result = client.post("/v1/recommend", json=dict(request, request_id="restore-probe")).raise_for_status().json()
            assert result["serving_generation"] == stable_id and result["served_strategy"] == "rule-v1"
            assert result["config_id"] == recovered["traffic_pointer"][0]["config_id"]
            assert result["impression_id"]
            rto = monotonic() - outage
    return {"rpo_seconds": round(outage - checkpoint, 3), "rto_seconds": round(rto, 3),
            "decisions_lost_after_backup": 1, "archive_bytes": archive.stat().st_size,
            "verified_rows": {table: len(rows) for table, rows in recovered.items()},
            "stable_generation": stable_id, "restored_revision": recovered["traffic_pointer"][0]["revision"]}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("source_container")
    parser.add_argument("restore_container")
    parser.add_argument("--source-dsn", required=True)
    parser.add_argument("--restore-dsn", required=True)
    args = parser.parse_args()
    if args.source_container == args.restore_container:
        parser.error("Use distinct source and restore containers")
    database = "stage3_" + uuid4().hex
    created = []
    try:
        for container in (args.source_container, args.restore_container):
            docker_pg(container, "createdb", "-U", "postgres", "-T", "template0", database)
            created.append(container)
        with TemporaryDirectory() as directory:
            result = exercise(args, database, Path(directory))
        print(json.dumps(result, indent=2))
    finally:
        for container in created:
            docker_pg(container, "dropdb", "-U", "postgres", database)


if __name__ == "__main__":
    main()
