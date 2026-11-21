"""Restore the Stage 4 snapshot and switch the HTTPS service to the restored DB."""
from datetime import datetime, timezone
import json
import subprocess
from time import perf_counter
from uuid import uuid4

from scripts.stage4_probes import AWS, WORK, alb_client, require_until


def run():
    deployment = json.loads((WORK / "deployment.json").read_bytes())
    evidence = {"snapshot_id": "rankflow-stage4-drill", "restore_id": "rankflow-stage4-restored"}

    def save():
        (WORK / "restore.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    client, roles = alb_client(deployment)
    viewer = roles["VIEWER"]
    rds = AWS.client("rds")
    tags = [{"Key": "project", "Value": "rankflow"}, {"Key": "stage", "Value": "stage4"}]

    def get(path):
        return client.get(path, headers=viewer).raise_for_status().json()

    def recommend():
        response = client.post("/v1/recommend", json={
            "request_id": "restore:" + uuid4().hex, "session_id": "stage4-restore", "events": [],
        }).raise_for_status().json()
        assert response["logging_status"] == "persisted" and response["served_strategy"] == "rule-v1"
        assert response["serving_generation"] == deployment["Stable"]
        return response

    with client:
        recommend()
        def drained_checkpoint():
            events = get("/operator/events")
            return events if events["outbox"]["pending"] == 0 else None

        evidence["checkpoint"] = require_until(drained_checkpoint)
        stage = get("/operator/status")
        evidence["checkpoint_config"] = stage["config_id"]
        evidence["checkpoint_revision"] = stage["revision"]
        evidence["checkpoint_configuration"] = stage["configuration"]
        evidence["checkpoint_traffic_history"] = stage["traffic_history"]
        evidence["checkpoint_epochs"] = get("/operator/epochs")
        evidence["checkpoint_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint = perf_counter()
        snapshot = rds.create_db_snapshot(DBInstanceIdentifier=deployment["DatabaseId"],
                                          DBSnapshotIdentifier=evidence["snapshot_id"], Tags=tags)
        evidence["snapshot_requested"] = snapshot["DBSnapshot"]["DBSnapshotIdentifier"]
        save()
        rds.get_waiter("db_snapshot_available").wait(DBSnapshotIdentifier=evidence["snapshot_id"],
                                                     WaiterConfig={"Delay": 15, "MaxAttempts": 80})
        snapshot = rds.describe_db_snapshots(DBSnapshotIdentifier=evidence["snapshot_id"])["DBSnapshots"][0]
        snapshot_at = snapshot["SnapshotCreateTime"]
        evidence["snapshot_created_at"] = snapshot_at.isoformat()
        evidence["post_snapshot_impression"] = recommend()["impression_id"]
        evidence["before_restore"] = get("/operator/events")
        start = perf_counter()
        evidence["restore_started_at"] = datetime.now(timezone.utc).isoformat()
        evidence["rpo_seconds"] = round((datetime.fromisoformat(evidence["restore_started_at"]) -
                                         snapshot_at).total_seconds(), 3)
        evidence["checkpoint_to_restore_start_seconds"] = round(start - checkpoint, 3)
        db = rds.describe_db_instances(DBInstanceIdentifier=deployment["DatabaseId"])["DBInstances"][0]
        rds.restore_db_instance_from_db_snapshot(
            DBInstanceIdentifier=evidence["restore_id"], DBSnapshotIdentifier=evidence["snapshot_id"],
            DBInstanceClass=db["DBInstanceClass"], DBSubnetGroupName=db["DBSubnetGroup"]["DBSubnetGroupName"],
            VpcSecurityGroupIds=[group["VpcSecurityGroupId"] for group in db["VpcSecurityGroups"]],
            PubliclyAccessible=False, MultiAZ=False, Tags=tags,
        )
        save()
        rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=evidence["restore_id"],
                                                     WaiterConfig={"Delay": 15, "MaxAttempts": 80})
        restored = rds.describe_db_instances(DBInstanceIdentifier=evidence["restore_id"])["DBInstances"][0]
        endpoint = restored["Endpoint"]["Address"]
        subprocess.run(["powershell", "-NoProfile", "-File", "infra/stage4_update.ps1", "-RestoreEndpoint", endpoint],
                       check=True)
        stack = AWS.client("cloudformation")
        stack.get_waiter("stack_update_complete").wait(StackName="RankFlowStage4",
                                                       WaiterConfig={"Delay": 10, "MaxAttempts": 90})
        evidence["restored_endpoint"] = endpoint
        evidence["restored_before_probe"] = get("/operator/events")
        save()
        assert evidence["restored_before_probe"] == evidence["checkpoint"]
        old_count = sum(row["decisions"] for row in evidence["before_restore"]["provenance"])
        recovered_count = sum(row["decisions"] for row in evidence["restored_before_probe"]["provenance"])
        evidence["unrecoverable_decisions"] = old_count - recovered_count
        old_outbox = sum(evidence["before_restore"]["outbox"].values())
        recovered_outbox = sum(evidence["restored_before_probe"]["outbox"].values())
        evidence["unrecoverable_outbox_events"] = old_outbox - recovered_outbox
        assert evidence["unrecoverable_decisions"] == evidence["unrecoverable_outbox_events"] == 1
        stage_status = get("/operator/status")
        assert stage_status["config_id"] == evidence["checkpoint_config"]
        assert stage_status["revision"] == evidence["checkpoint_revision"]
        assert stage_status["configuration"] == evidence["checkpoint_configuration"]
        assert stage_status["traffic_history"] == evidence["checkpoint_traffic_history"]
        assert get("/operator/epochs") == evidence["checkpoint_epochs"]
        evidence["restored_configuration_and_history_match"] = True

        restored_instances = set()

        def sample_restored_fleet():
            for _ in range(4):
                ready = client.get("/health/ready", headers={"Connection": "close"}).raise_for_status().json()
                if (ready["serving_ready"] and ready["release_ready"]
                        and ready["config_id"] == evidence["checkpoint_config"]
                        and ready["config_revision"] == evidence["checkpoint_revision"]):
                    restored_instances.add(ready["instance_id"])
            leased = {item["instance_id"] for item in get("/operator/status")["instances"] if item["leased"]}
            return len(leased) == 2 and leased <= restored_instances

        require_until(sample_restored_fleet)
        evidence["restored_instances"] = sorted(restored_instances)
        evidence["restored_probe"] = {key: value for key, value in recommend().items()
                                      if key in ("impression_id", "config_revision", "config_id",
                                                 "served_strategy", "serving_generation", "logging_status")}
        evidence["rto_seconds"] = round(perf_counter() - start, 3)
        save()


if __name__ == "__main__":
    run()
