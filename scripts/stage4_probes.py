"""Probe the Stage 4 fleet exclusively through the HTTPS ALB."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import ssl
from time import perf_counter, sleep
from uuid import uuid4

import boto3
import httpx

from rankflow.traffic import TrafficConfigSnapshot
from scripts.stage3_benchmark import p95


WORK = Path("artifacts/stage4")
AWS = boto3.Session(region_name="ca-central-1")


def require_until(probe, seconds=90):
    end = perf_counter() + seconds
    while perf_counter() < end:
        if result := probe():
            return result
        sleep(.1)
    raise TimeoutError("Stage 4 probe timed out")


def alb_client(deployment):
    secrets = AWS.client("secretsmanager")
    stack = AWS.client("cloudformation")
    roles = {}
    for resource in stack.list_stack_resources(StackName="RankFlowStage4")["StackResourceSummaries"]:
        for role in ("ADMIN", "OPERATOR", "VIEWER"):
            if resource["ResourceType"] == "AWS::SecretsManager::Secret" and resource[
                    "LogicalResourceId"].startswith(role + "BEARER"):
                value = secrets.get_secret_value(SecretId=resource["PhysicalResourceId"])["SecretString"]
                roles[role] = {"Authorization": f"Bearer {value}"}
    tls = ssl.create_default_context(cafile=str(WORK / "alb-cert.pem"))
    url = "https://" + deployment["AlbDns"]
    return httpx.Client(base_url=url, verify=tls, trust_env=False, timeout=15), roles


def run():
    deployment_file = WORK / "deployment.json"
    deployment = json.loads(deployment_file.read_bytes())
    cf = AWS.client("cloudformation")
    cf.get_waiter("stack_update_complete").wait(StackName="RankFlowStage4",
                                                WaiterConfig={"Delay": 10, "MaxAttempts": 90})
    outputs = cf.describe_stacks(StackName="RankFlowStage4")["Stacks"][0]["Outputs"]
    deployment.update({row["OutputKey"]: row["OutputValue"] for row in outputs})
    deployment_file.write_text(json.dumps(deployment, indent=2), encoding="utf-8")
    client, roles = alb_client(deployment)
    with client:
        def status(headers=roles["VIEWER"]):
            return client.get("/operator/status", headers=headers).raise_for_status().json()

        evidence = {"started": datetime.now(timezone.utc).isoformat(), "phases": [], "modes": {}}
        ecs = AWS.client("ecs")
        service_description = ecs.describe_services(cluster=deployment["Cluster"],
                                                    services=[deployment["Service"]])["services"][0]
        evidence["service"] = {key: service_description[key] for key in
                               ("desiredCount", "runningCount", "pendingCount", "taskDefinition")}

        def save():
            (WORK / "probes.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        def converge(revision, config_id, started, label):
            observations = {}
            sampled = {}

            def sample():
                info = client.get("/health/ready", headers={"Connection": "close"}).raise_for_status().json()
                if info["release_ready"] and info["config_revision"] == revision and info["config_id"] == config_id:
                    observations.setdefault(info["instance_id"], round(perf_counter() - started, 6))
                fleet = status()
                leased = {row["instance_id"] for row in fleet["instances"] if row["leased"]}
                sampled.update(leased=sorted(leased), convergence=fleet["convergence"], latest_readiness=info)
                return len(leased) == 2 and leased <= observations.keys() and (
                    revision == 0 or fleet["convergence"] == "converged")

            try:
                require_until(sample)
            except TimeoutError:
                evidence["convergence_timeout"] = {"phase": label, "observations_seconds": observations, **sampled}
                save()
                raise
            evidence["phases"].append({"phase": label, "revision": revision, "config_id": config_id,
                                       "observations_seconds": observations})
            save()

        stable = TrafficConfigSnapshot(deployment["Stable"])
        fixture = deployment["Fixture"]
        assert client.get("/health/live").raise_for_status().json()["live"]
        assert client.get("/operator/status").status_code == 401
        assert client.post("/operator/prepare", headers=roles["VIEWER"], json={}).status_code == 403
        assert client.post("/operator/epochs", headers=roles["OPERATOR"], json={}).status_code == 403
        assert client.post("/operator/epochs", headers=roles["ADMIN"], json={}).status_code == 409
        converge(0, stable.config_id, perf_counter(), "initial stable")

        prefixes = client.get("/v1/playground/prefixes", params={"window": "W2-dev"}).raise_for_status().json()
        for sealed in ("W2-gate", "W3"):
            assert client.get("/v1/playground/prefixes", params={"window": sealed}).status_code == 404
        epoch = json.loads(Path("artifacts/stage0-otto/evaluation_epoch.json").read_bytes())
        assert client.post("/operator/epochs", headers=roles["ADMIN"], json=epoch).raise_for_status().json()["registered"]
        examples = json.loads((Path("artifacts/stage1/generations") / deployment["Stable"] /
                               "public_prefixes.json").read_bytes())["W2-dev"]
        evidence["public_prefix_response"] = bool(prefixes)
        evidence["role_and_window_checks"] = "passed"
        run_id = uuid4().hex
        evidence["run_id"] = run_id

        def request(label, index):
            started = perf_counter()
            try:
                response = client.post("/v1/recommend", json={
                    "request_id": f"{label}:{run_id}:{index}",
                    "session_id": str(index),
                    "events": examples[index % len(examples)]["events"],
                })
                elapsed = (perf_counter() - started) * 1000
                payload = response.json() if response.is_success else {}
                return {"ms": elapsed, "status": response.status_code,
                        "generation": payload.get("serving_generation"), "strategy": payload.get("served_strategy"),
                        "fallback_used": payload.get("fallback_used"), "api_ms": payload.get("latency_ms"),
                        "logging_status": payload.get("logging_status"), "impression_id": payload.get("impression_id")}
            except httpx.HTTPError as error:
                return {"ms": (perf_counter() - started) * 1000, "error": type(error).__name__}

        def measure(label, concurrency, count=48, generation=stable.stable_generation_id):
            started = datetime.now(timezone.utc).isoformat()
            with ThreadPoolExecutor(concurrency) as executor:
                rows = list(executor.map(lambda index: request(label, index), range(count)))
            values = sorted(row["ms"] for row in rows)
            evidence["modes"][label] = {
                "concurrency": concurrency, "client_p95_ms": p95(values), "client_p99_ms": round(values[-1], 3),
                "started": started, "finished": datetime.now(timezone.utc).isoformat(),
                "errors": sum(row.get("status") != 200 for row in rows), "requests": rows,
            }
            save()
            assert all(row.get("generation") == generation and row.get("strategy") == "rule-v1" for row in rows)

        def publish(revision, label, target=None, rollback=None):
            command = {"expected_revision": revision, "operation_id": label}
            if rollback:
                action = "rollback"
                command["rollback_config_id"] = rollback
            else:
                action = "publish"
                command["configuration"] = asdict(target)
            started = perf_counter()
            response = client.post("/operator/traffic/" + action, headers=roles["OPERATOR"], json=command)
            response.raise_for_status()
            assert response.json()["state"] == "pointer_committed"
            converge(revision + 1, rollback or target.config_id, started, label)

        measure("stable", 4)
        measure("peak", 12)
        shadow = replace(stable, state="shadowing", shadow_mode="live", shadow_generation_id=fixture)
        publish(0, "stage4-named-shadow", target=shadow)
        measure("shadow", 4)
        canary = replace(stable, state="canary", canary_generation_id=fixture, canary_percent=100)
        client.post("/operator/prepare", headers=roles["OPERATOR"], json=asdict(canary)).raise_for_status()

        def prepared():
            leased = [row for row in status()["instances"] if row["leased"]]
            return len(leased) == 2 and all(canary.config_id in row["prepared"] for row in leased)

        require_until(prepared)
        publish(1, "stage4-named-canary", target=canary)
        measure("canary", 4, generation=fixture)
        publish(2, "stage4-named-rollback", rollback=stable.config_id)

        service = dict(cluster=deployment["Cluster"], serviceName=deployment["Service"])
        tasks = ecs.list_tasks(**service)["taskArns"]
        assert len(tasks) == 2
        initial_instances = {row["instance_id"] for row in status()["instances"] if row["leased"]}

        def stop():
            sleep(1)
            return ecs.stop_task(cluster=deployment["Cluster"], task=tasks[0], reason="Stage 4 task-loss drill")

        with ThreadPoolExecutor(5) as executor:
            stopped = executor.submit(stop)
            rows = list(executor.map(lambda index: request("task-loss", index), range(200)))
            stopped.result()
        evidence["task_loss"] = {"stopped_task": tasks[0], "requests": rows}
        save()

        def replaced():
            instances = {row["instance_id"] for row in status()["instances"] if row["leased"]}
            targets = AWS.client("elbv2").describe_target_health(TargetGroupArn=deployment["Targets"])
            return (instances if len(instances) == 2 and len(initial_instances & instances) == 1
                    and sum(row["TargetHealth"]["State"] == "healthy" for row in targets["TargetHealthDescriptions"]) == 2
                    else None)

        evidence["task_loss"]["replacement_instances"] = sorted(require_until(replaced, 180))
        evidence["finished"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    run()
