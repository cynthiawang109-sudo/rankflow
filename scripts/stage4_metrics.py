"""Collect benchmark segment measurements and service utilization from AWS."""
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json

from scripts.stage3_benchmark import p95
from scripts.stage4_probes import AWS, WORK


def run():
    config = json.loads((WORK / "deployment.json").read_bytes())
    probes = json.loads((WORK / "probes.json").read_bytes())
    logs = AWS.client("logs")
    start = datetime.fromisoformat(probes["started"])
    ranking = defaultdict(list)
    persistence = {}
    run_id = probes["run_id"]
    for page in logs.get_paginator("filter_log_events").paginate(
            logGroupName=config["Logs"], startTime=int(start.timestamp() * 1000)):
        for event in page["events"]:
            line = event["message"].strip()
            if not line.startswith("{"):
                continue
            row = json.loads(line)
            request_id = row.get("request_id") or ""
            if f":{run_id}:" not in request_id:
                continue
            if row["event"] == "ranking_outcome":
                ranking[request_id].append(row)
            elif row["event"] == "recommendation_outcome":
                persistence[request_id] = row.get("persistence_ms")
    cw = AWS.client("cloudwatch")
    for mode, block in probes["modes"].items():
        foreground = []
        commits = []
        for index, response in enumerate(block["requests"]):
            request_id = f"{mode}:{run_id}:{index}"
            matches = [row for row in ranking[request_id] if row["generation"] == response["generation"]]
            if len(matches) == 1:
                foreground.extend(matches)
                response["foreground_segments_ms"] = {key: matches[0][key] for key in
                                                       ("retrieval_ms", "feature_ms", "scoring_ms")}
            if persistence.get(request_id) is not None:
                commits.append(persistence[request_id])
                response["persistence_ms"] = persistence[request_id]
        block["ranking_sample_count"] = len(foreground)
        block["persistence_sample_count"] = len(commits)
        block["segment_p95_ms"] = {key: p95([row[key] for row in foreground]) for key in
                                   ("retrieval_ms", "feature_ms", "scoring_ms")} if foreground else {}
        block["persistence_p95_ms"] = p95(commits) if commits else None
        api = [row["api_ms"] for row in block["requests"] if row.get("api_ms") is not None]
        block["api_p95_ms"] = p95(api) if api else None
        outside = [row["ms"] - row["api_ms"] for row in block["requests"] if row.get("api_ms") is not None]
        block["outside_handler_p95_ms"] = p95(outside) if outside else None
        block["utilization"] = {}
        for metric in ("CPUUtilization", "MemoryUtilization"):
            data = cw.get_metric_statistics(Namespace="AWS/ECS", MetricName=metric,
                                            StartTime=datetime.fromisoformat(block["started"]),
                                            EndTime=datetime.fromisoformat(block["finished"]).replace(
                                                second=0, microsecond=0) + timedelta(minutes=1),
                                            Period=60, Statistics=["Average", "Maximum"],
                                            Dimensions=[{"Name": "ClusterName", "Value": config["Cluster"]},
                                                        {"Name": "ServiceName", "Value": config["Service"]}])
            block["utilization"][metric] = data["Datapoints"]
    probes["collected_at"] = datetime.now(timezone.utc).isoformat()
    (WORK / "metrics.json").write_text(json.dumps(probes, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    run()
