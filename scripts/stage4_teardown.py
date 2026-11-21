"""Delete the Stage 4 deployment and archive AWS inventory and cost evidence."""
from datetime import datetime, timedelta, timezone
import json

from botocore.exceptions import ClientError

from scripts.stage4_probes import AWS, WORK


STACK = "RankFlowStage4"


def run():
    cf = AWS.client("cloudformation")
    rds = AWS.client("rds")
    s3 = AWS.client("s3")
    acm = AWS.client("acm")
    deployment_path = WORK / "deployment.json"
    deployment = json.loads(deployment_path.read_bytes()) if deployment_path.exists() else {}
    stack = cf.describe_stacks(StackName=STACK)["Stacks"][0]
    stack_id = stack["StackId"]
    inventory = cf.list_stack_resources(StackName=stack_id)["StackResourceSummaries"]
    evidence = {"stack_id": stack_id, "inventory_before_delete": inventory,
                "stack_created_at": stack["CreationTime"]}
    output = WORK / "teardown.json"

    def save():
        output.write_text(json.dumps(evidence, default=str, indent=2), encoding="utf-8")

    bucket = deployment.get("BundleBucket") or next(
        (row.get("PhysicalResourceId") for row in inventory
         if row["ResourceType"] == "AWS::S3::Bucket" and row["ResourceStatus"] == "CREATE_COMPLETE"), None)
    save()
    if bucket:
        for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
            keys = [{"Key": row["Key"], "VersionId": row["VersionId"]}
                    for group in ("Versions", "DeleteMarkers") for row in page.get(group, [])]
            if keys:
                response = s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
                if response.get("Errors"):
                    raise RuntimeError(response["Errors"])
    if deployment.get("Service"):
        ecs = AWS.client("ecs")
        cluster = deployment["Cluster"]
        tasks = set()
        for state in ("RUNNING", "STOPPED"):
            tasks.update(ecs.list_tasks(cluster=cluster, serviceName=deployment["Service"],
                                        desiredStatus=state)["taskArns"])
        if tasks:
            evidence["tasks_before_delete"] = [
                {key: task.get(key) for key in ("taskArn", "createdAt", "startedAt", "stoppedAt", "cpu", "memory")}
                for task in ecs.describe_tasks(cluster=cluster, tasks=sorted(tasks))["tasks"]]
    dr = WORK / "restore.json"
    if dr.exists():
        restore = json.loads(dr.read_bytes())
        restored = restore["restore_id"]
        snapshot = restore["snapshot_id"]
        instances = rds.describe_db_instances()["DBInstances"]
        temporary = next((row for row in instances if row["DBInstanceIdentifier"] == restored), None)
        if temporary:
            evidence["restore_instance_created_at"] = temporary["InstanceCreateTime"]
            rds.delete_db_instance(DBInstanceIdentifier=restored, SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
            rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=restored,
                                                       WaiterConfig={"Delay": 10, "MaxAttempts": 90})
        snapshots = rds.describe_db_snapshots(SnapshotType="manual")["DBSnapshots"]
        manual = next((row for row in snapshots if row["DBSnapshotIdentifier"] == snapshot), None)
        if manual:
            evidence["manual_snapshot_created_at"] = manual["SnapshotCreateTime"]
            rds.delete_db_snapshot(DBSnapshotIdentifier=snapshot)
        evidence["restore_instance_remaining"] = any(
            row["DBInstanceIdentifier"] == restored for row in rds.describe_db_instances()["DBInstances"])
        evidence["manual_snapshot_remaining"] = any(
            row["DBSnapshotIdentifier"] == snapshot
            for row in rds.describe_db_snapshots(SnapshotType="manual")["DBSnapshots"])
        save()
    cf.delete_stack(StackName=stack_id)
    cf.get_waiter("stack_delete_complete").wait(StackName=stack_id, WaiterConfig={"Delay": 10, "MaxAttempts": 100})
    if certificate := deployment.get("Certificate"):
        acm.delete_certificate(CertificateArn=certificate)
        evidence["certificate_remaining"] = any(
            row["CertificateArn"] == certificate
            for page in acm.get_paginator("list_certificates").paginate() for row in page["CertificateSummaryList"])
    evidence["inventory_after_delete"] = cf.list_stack_resources(StackName=stack_id)["StackResourceSummaries"]
    evidence["deleted_at"] = datetime.now(timezone.utc)
    all_events = cf.get_paginator("describe_stack_events").paginate(StackName=stack_id)
    evidence["cloudformation_events"] = [row for page in all_events for row in page["StackEvents"]
                                        if row["ResourceStatus"] in {"CREATE_COMPLETE", "DELETE_COMPLETE"}]
    evidence["tagged_resources"] = [
        mapping for page in AWS.client("resourcegroupstaggingapi").get_paginator("get_resources").paginate(
            TagFilters=[{"Key": "project", "Values": ["rankflow"]}, {"Key": "stage", "Values": ["stage4"]}])
        for mapping in page["ResourceTagMappingList"]]
    evidence["remaining_stage_db_backups"] = [
        item["DBInstanceIdentifier"] for item in rds.describe_db_instance_automated_backups()["DBInstanceAutomatedBackups"]
        if item["DBInstanceIdentifier"] in {deployment.get("DatabaseId"), "rankflow-stage4-restored"}]
    save()
    ce = AWS.client("ce", region_name="us-east-1")
    try:
        evidence["cost_query"] = ce.get_cost_and_usage(
            TimePeriod={"Start": stack["CreationTime"].date().isoformat(),
                        "End": (evidence["deleted_at"].date() + timedelta(days=1)).isoformat()},
            Granularity="DAILY", Metrics=["UnblendedCost"],
            Filter={"And": [{"Tags": {"Key": "project", "Values": ["rankflow"]}},
                            {"Tags": {"Key": "stage", "Values": ["stage4"]}}]},
        )["ResultsByTime"]
    except ClientError as error:
        evidence["cost_query_error"] = error.response["Error"]["Code"]
    save()


if __name__ == "__main__":
    run()
