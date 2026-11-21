"""Probe the Stage 4 fleet exclusively through the HTTPS ALB."""
import argparse
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


def run(reliability_only=False, resume=False, confirm_task_drain=False):
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

        evidence_file = WORK / "probes.json"
        evidence = (json.loads(evidence_file.read_bytes()) if resume or confirm_task_drain else
                    {"started": datetime.now(timezone.utc).isoformat(), "phases": [], "modes": {}})
        ecs = AWS.client("ecs")
        service_description = ecs.describe_services(cluster=deployment["Cluster"],
                                                    services=[deployment["Service"]])["services"][0]
        service_key = "restored_task_drain_service" if confirm_task_drain else "service"
        evidence[service_key] = {key: service_description[key] for key in
                                 ("desiredCount", "runningCount", "pendingCount", "taskDefinition")}

        def save():
            evidence_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        def converge(revision, config_id, started, label):
            observations = {}
            sampled = {}

            def sample():
                for _ in range(4):
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
        stable_revision = 0
        retry_phase = None
        if confirm_task_drain:
            assert evidence["finished"] and (WORK / "restore.json").exists()
            restored = json.loads((WORK / "restore.json").read_bytes())
            assert restored["restored_probe"]["serving_generation"] == deployment["Stable"]
            fleet = status()
            assert fleet["release_ready"] and fleet["config_id"] == stable.config_id
            assert fleet["revision"] == restored["checkpoint_revision"]
        elif resume:
            fleet = status()
            assert fleet["release_ready"] and fleet["config_id"] == stable.config_id
            stable_revision = fleet["revision"]
            timeout = evidence.pop("convergence_timeout")
            retry_phase = timeout["phase"]
            if retry_phase == "stage4-named-shadow":
                evidence["first_publication_timeout"] = timeout
                evidence["history_before_retry"] = fleet["traffic_history"]
            else:
                assert retry_phase == "stage4-named-rollback"
                assert fleet["traffic_history"][0]["operation_id"] == retry_phase
                evidence["rollback_observation_timeout"] = timeout
                evidence["rollback_follow_up_history"] = fleet["traffic_history"]
            save()
        else:
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
            evidence["public_prefix_response"] = bool(prefixes)
            evidence["role_and_window_checks"] = "passed"
        examples = json.loads((Path("artifacts/stage1/generations") / deployment["Stable"] /
                               "public_prefixes.json").read_bytes())["W2-dev"]
        run_id = evidence.setdefault("run_id", uuid4().hex)

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

        def prepare(target):
            client.post("/operator/prepare", headers=roles["OPERATOR"], json=asdict(target),
                        timeout=60).raise_for_status()

            def prepared():
                leased = [row for row in status()["instances"] if row["leased"]]
                return len(leased) == 2 and all(target.config_id in row["prepared"] for row in leased)

            require_until(prepared)

        if reliability_only and not resume and not confirm_task_drain:
            baseline = request("initial-stable", 0)
            assert baseline["status"] == 200 and baseline["logging_status"] == "persisted"
            assert baseline["generation"] == stable.stable_generation_id and baseline["strategy"] == "rule-v1"
            evidence["initial_stable"] = baseline
            save()
        elif not reliability_only:
            measure("stable", 4)
            measure("peak", 12)
        if not confirm_task_drain:
            if retry_phase == "stage4-named-rollback":
                converge(stable_revision, stable.config_id, perf_counter(), "rollback follow-up sampling")
            else:
                shadow = replace(stable, state="shadowing", shadow_mode="live", shadow_generation_id=fixture)
                if reliability_only:
                    prepare(shadow)
                operation = "stage4-named-shadow-after-preload" if resume else "stage4-named-shadow"
                publish(stable_revision, operation, target=shadow)
                rollback_revision = stable_revision + 1
                if not reliability_only:
                    measure("shadow", 4)
                    canary = replace(stable, state="canary", canary_generation_id=fixture, canary_percent=100)
                    prepare(canary)
                    publish(rollback_revision, "stage4-named-canary", target=canary)
                    rollback_revision += 1
                    measure("canary", 4, generation=fixture)
                publish(rollback_revision, "stage4-named-rollback", rollback=stable.config_id)

        service = dict(cluster=deployment["Cluster"], serviceName=deployment["Service"])
        tasks = ecs.list_tasks(**service)["taskArns"]
        assert len(tasks) == 2
        initial_instances = {row["instance_id"] for row in status()["instances"] if row["leased"]}
        elb = AWS.client("elbv2")
        target_group = dict(TargetGroupArn=deployment["Targets"])

        def target_health():
            return {row["Target"]["Id"]: row["TargetHealth"]["State"]
                    for row in elb.describe_target_health(**target_group)["TargetHealthDescriptions"]}

        before = target_health()
        task_network = ecs.describe_tasks(cluster=deployment["Cluster"], tasks=[tasks[0]])["tasks"][0]
        target_ip = next(detail["value"] for attachment in task_network["attachments"]
                         for detail in attachment["details"] if detail["name"] == "privateIPv4Address")

        def stop():
            sleep(1)
            stopped_at = datetime.now(timezone.utc).isoformat()
            ecs.stop_task(cluster=deployment["Cluster"], task=tasks[0], reason="Stage 4 task-loss drill")
            samples = []
            deadline = perf_counter() + 120
            while perf_counter() < deadline:
                health = target_health()
                if not samples or health != samples[-1]["targets"]:
                    samples.append({"at": datetime.now(timezone.utc).isoformat(), "targets": health})
                if health.get(target_ip, "removed") in {"unused", "removed"}:
                    break
                sleep(.5)
            return stopped_at, samples

        label = "task-drain-confirmation" if confirm_task_drain else "task-loss"
        rows, batches = [], []

        def batch(executor):
            offset = len(rows)
            started = datetime.now(timezone.utc).isoformat()
            rows.extend(executor.map(lambda index: request(label, index), range(offset, offset + 4)))
            batches.append({"started": started, "finished": datetime.now(timezone.utc).isoformat(),
                            "first_request": offset, "requests": 4})

        traffic_started = datetime.now(timezone.utc).isoformat()
        with ThreadPoolExecutor(5) as executor:
            stopped = executor.submit(stop)
            while not stopped.done():
                next_batch = perf_counter() + 1
                batch(executor)
                sleep(max(0, next_batch - perf_counter()))
            stopped_at, after_stop = stopped.result()
            batch(executor)
        loss = {"stopped_task": tasks[0], "requests": rows, "traffic_batches": batches,
                "traffic_started": traffic_started, "traffic_finished": datetime.now(timezone.utc).isoformat(),
                "stop_requested_at": stopped_at, "stopped_target": target_ip,
                "targets_before": before, "targets_after_stop": after_stop,
                "initial_instances": sorted(initial_instances)}
        evidence["task_drain_confirmation" if confirm_task_drain else "task_loss"] = loss
        save()

        def replaced():
            instances = {row["instance_id"] for row in status()["instances"] if row["leased"]}
            targets = target_health()
            return (instances if len(instances) == 2 and len(initial_instances & instances) == 1
                    and list(targets.values()).count("healthy") == 2
                    else None)

        loss["replacement_instances"] = sorted(require_until(replaced, 180))
        loss["targets_after_replacement"] = target_health()
        finished = datetime.now(timezone.utc).isoformat()
        if confirm_task_drain:
            loss["finished"] = finished
        else:
            evidence["finished"] = finished
        save()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--reliability-only", action="store_true")
    modes.add_argument("--resume-reliability", action="store_true")
    modes.add_argument("--confirm-task-drain", action="store_true")
    args = parser.parse_args()
    run(args.reliability_only or args.resume_reliability or args.confirm_task_drain,
        args.resume_reliability, args.confirm_task_drain)
