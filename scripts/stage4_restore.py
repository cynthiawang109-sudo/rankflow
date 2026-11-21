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
        evidence["checkpoint_epochs"] = get("/operator/epochs")
        evidence["checkpoint_at"] = datetime.now(timezone.utc).isoformat()
        checkpoint = perf_counter()
        snapshot = rds.create_db_snapshot(DBInstanceIdentifier=deployment["DatabaseId"],
                                          DBSnapshotIdentifier=evidence["snapshot_id"], Tags=tags)
        evidence["snapshot_requested"] = snapshot["DBSnapshot"]["DBSnapshotIdentifier"]
        save()
        rds.get_waiter("db_snapshot_available").wait(DBSnapshotIdentifier=evidence["snapshot_id"],
                                                     WaiterConfig={"Delay": 15, "MaxAttempts": 80})
        evidence["post_snapshot_impression"] = recommend()["impression_id"]
        evidence["before_restore"] = get("/operator/events")
        start = perf_counter()
        evidence["rpo_seconds"] = round(start - checkpoint, 3)
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
        stage_status = get("/operator/status")
        assert stage_status["config_id"] == evidence["checkpoint_config"]
        assert stage_status["revision"] == evidence["checkpoint_revision"]
        assert get("/operator/epochs") == evidence["checkpoint_epochs"]
        evidence["restored_probe"] = {key: value for key, value in recommend().items()
                                      if key in ("impression_id", "config_revision", "config_id",
                                                 "served_strategy", "serving_generation", "logging_status")}
        evidence["rto_seconds"] = round(perf_counter() - start, 3)
        save()


if __name__ == "__main__":
    run()
