"""Delete the Stage 4 deployment and archive AWS inventory and cost evidence."""
from datetime import datetime, timedelta, timezone
import json

from botocore.exceptions import ClientError, WaiterError

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
    deployment.update({item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])})
    stack_id = stack["StackId"]
    inventory = cf.list_stack_resources(StackName=stack_id)["StackResourceSummaries"]
    evidence = {"stack_id": stack_id, "inventory_before_delete": inventory,
                "stack_created_at": stack["CreationTime"], "tags": stack.get("Tags", [])}
    output = WORK / "teardown.json"

    def save():
        output.write_text(json.dumps(evidence, default=str, indent=2), encoding="utf-8")

    bucket = deployment.get("BundleBucket") or next(
        (row.get("PhysicalResourceId") for row in inventory
         if row["ResourceType"] == "AWS::S3::Bucket" and row["ResourceStatus"] == "CREATE_COMPLETE"), None)
    save()
    if bucket:
        evidence["s3_versions_removed"] = 0
        for page in s3.get_paginator("list_object_versions").paginate(Bucket=bucket):
            keys = [{"Key": row["Key"], "VersionId": row["VersionId"]}
                    for group in ("Versions", "DeleteMarkers") for row in page.get(group, [])]
            if keys:
                response = s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
                if response.get("Errors"):
                    raise RuntimeError(response["Errors"])
                evidence["s3_versions_removed"] += len(keys)
        save()
    if deployment.get("Service"):
        ecs = AWS.client("ecs")
        cluster = deployment["Cluster"]
        service = deployment["Service"]
        running = ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus="RUNNING")["taskArns"]
        tasks = set(running)
        try:
            ecs.update_service(cluster=cluster, service=service, desiredCount=0)
            if running:
                ecs.get_waiter("tasks_stopped").wait(cluster=cluster, tasks=running,
                                                     WaiterConfig={"Delay": 5, "MaxAttempts": 24})
        except ClientError as error:
            evidence["task_drain_error"] = error.response["Error"]["Code"]
        except WaiterError:
            evidence["task_drain_error"] = "Timed out waiting for ECS tasks to stop"
        tasks.update(ecs.list_tasks(cluster=cluster, serviceName=service, desiredStatus="STOPPED")["taskArns"])
        if tasks:
            evidence["tasks_before_delete"] = [
                {key: task.get(key) for key in ("taskArn", "createdAt", "startedAt", "stoppedAt", "cpu", "memory")}
                for task in ecs.describe_tasks(cluster=cluster, tasks=sorted(tasks))["tasks"]]
        save()
    dr = WORK / "restore.json"
    if dr.exists():
        restore = json.loads(dr.read_bytes())
        restored = restore["restore_id"]
        snapshot = restore["snapshot_id"]
        instances = rds.describe_db_instances()["DBInstances"]
        temporary = next((row for row in instances if row["DBInstanceIdentifier"] == restored), None)
        if temporary:
            evidence["restore_instance_created_at"] = temporary["InstanceCreateTime"]
            evidence["restore_instance_delete_requested_at"] = datetime.now(timezone.utc)
            rds.delete_db_instance(DBInstanceIdentifier=restored, SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
            rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=restored,
                                                       WaiterConfig={"Delay": 10, "MaxAttempts": 90})
            evidence["restore_instance_deleted_at"] = datetime.now(timezone.utc)
        snapshots = rds.describe_db_snapshots(SnapshotType="manual")["DBSnapshots"]
        manual = next((row for row in snapshots if row["DBSnapshotIdentifier"] == snapshot), None)
        if manual:
            evidence["manual_snapshot_created_at"] = manual["SnapshotCreateTime"]
            rds.delete_db_snapshot(DBSnapshotIdentifier=snapshot)
            evidence["manual_snapshot_delete_requested_at"] = datetime.now(timezone.utc)
        evidence["restore_instance_remaining"] = any(
            row["DBInstanceIdentifier"] == restored for row in rds.describe_db_instances()["DBInstances"])
        evidence["manual_snapshot_remaining"] = any(
            row["DBSnapshotIdentifier"] == snapshot
            for row in rds.describe_db_snapshots(SnapshotType="manual")["DBSnapshots"])
        save()
    evidence["delete_requested_at"] = datetime.now(timezone.utc)
    save()
    cf.delete_stack(StackName=stack_id)
    cf.get_waiter("stack_delete_complete").wait(StackName=stack_id, WaiterConfig={"Delay": 10, "MaxAttempts": 100})
    def tagged_resources():
        return [
            mapping for page in AWS.client("resourcegroupstaggingapi").get_paginator("get_resources").paginate(
                TagFilters=[{"Key": "project", "Values": ["rankflow"]}, {"Key": "stage", "Values": ["stage4"]}])
            for mapping in page["ResourceTagMappingList"]]

    if deployment.get("Certificate"):
        certificates = {item["ResourceARN"] for item in tagged_resources()
                        if ":acm:" in item["ResourceARN"]}
        certificates.add(deployment["Certificate"])
        for certificate in sorted(certificates):
            try:
                acm.delete_certificate(CertificateArn=certificate)
            except acm.exceptions.ResourceNotFoundException:
                pass

        def certificate_exists(certificate):
            try:
                acm.describe_certificate(CertificateArn=certificate)
            except acm.exceptions.ResourceNotFoundException:
                return False
            return True

        evidence["certificate_remaining"] = any(certificate_exists(value) for value in certificates)
    evidence["inventory_after_delete"] = cf.list_stack_resources(StackName=stack_id)["StackResourceSummaries"]
    evidence["deleted_at"] = datetime.now(timezone.utc)
    all_events = cf.get_paginator("describe_stack_events").paginate(StackName=stack_id)
    evidence["cloudformation_events"] = [row for page in all_events for row in page["StackEvents"]
                                        if row["ResourceStatus"] in {"CREATE_COMPLETE", "DELETE_COMPLETE"}]
    evidence["tagged_resources"] = tagged_resources()
    evidence["remaining_stage_db_backups"] = [
        item["DBInstanceIdentifier"] for item in rds.describe_db_instance_automated_backups()["DBInstanceAutomatedBackups"]
        if item["DBInstanceIdentifier"] in {deployment.get("DatabaseId"), "rankflow-stage4-restored"}]
    save()

    def check_missing(name, call, missing_codes):
        try:
            call()
        except ClientError as error:
            code = error.response["Error"]["Code"]
            evidence["service_checks"][name] = {"missing": code in missing_codes, "code": code}
        else:
            evidence["service_checks"][name] = {"missing": False}
        save()

    evidence["service_checks"] = {}
    if bucket:
        check_missing("s3_bucket", lambda: s3.head_bucket(Bucket=bucket), {"404", "NoSuchBucket"})
    if database := deployment.get("DatabaseId"):
        check_missing("rds_instance", lambda: rds.describe_db_instances(DBInstanceIdentifier=database),
                      {"DBInstanceNotFound"})
    if repository := deployment.get("Repository"):
        ecr = AWS.client("ecr")
        check_missing("ecr_repository", lambda: ecr.describe_repositories(repositoryNames=[repository.split("/", 1)[1]]),
                      {"RepositoryNotFoundException"})
    for row in inventory:
        if row["ResourceType"] == "AWS::ElasticLoadBalancingV2::LoadBalancer":
            elb = AWS.client("elbv2")
            check_missing("load_balancer", lambda: elb.describe_load_balancers(
                LoadBalancerArns=[row["PhysicalResourceId"]]), {"LoadBalancerNotFound"})
    if log_group := deployment.get("Logs"):
        logs = AWS.client("logs")
        groups = logs.describe_log_groups(logGroupNamePrefix=log_group)["logGroups"]
        evidence["service_checks"]["log_group"] = {
            "missing": all(item["logGroupName"] != log_group for item in groups)}
    if cluster := deployment.get("Cluster"):
        ecs = AWS.client("ecs")
        response = ecs.describe_clusters(clusters=[cluster])
        evidence["service_checks"]["ecs_cluster"] = {
            "missing": (all(item["status"] == "INACTIVE" and not item.get("runningTasksCount")
                            for item in response["clusters"])
                        and all(item["reason"] == "MISSING" for item in response["failures"]))}
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
