"""Run the Stage 3 local three-process release drill against an isolated schema."""
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from uuid import uuid4

import httpx
from psycopg import sql
from psycopg.conninfo import make_conninfo

from rankflow.generation import Generation, encoded, identity
from rankflow.store import PostgresStore
from rankflow.traffic import TrafficConfigSnapshot, TrafficRegistry


def port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def run(root, dsn, children):
    registry = Path("artifacts/stage1/generations")
    stable_id = (registry / "alpha.txt").read_text().strip()
    assert Generation.load(registry / stable_id).assigned.strategy_id == "rule-v1"
    manifest = json.loads((registry / stable_id / "manifest.json").read_bytes())
    manifest["test_only"] = "Stage 3 routing fixture, rule strategy"
    candidate_id = identity(manifest)
    stable = TrafficConfigSnapshot(stable_id)
    rescue = root / "rescue.json"
    rescue.write_bytes(encoded(asdict(stable)))
    fixture = root / "fixture"
    shutil.copytree(registry / stable_id, fixture)
    (fixture / "manifest.json").write_bytes(encoded(manifest))
    store = PostgresStore(dsn)
    nodes = []
    for index in range(3):
        node = root / f"node{index}"
        node.mkdir()
        shutil.copytree(registry / stable_id, node / stable_id)
        if index < 2:
            shutil.copytree(fixture, node / candidate_id)
        nodes.append((node, f"http://127.0.0.1:{port()}"))

    control = TrafficRegistry(store, root / "node0", stable, {"v1": b"unused-controller-salt"},
                              poll_seconds=.25, convergence_seconds=3, minimum_capacity=2)

    def launch(index):
        node, url = nodes[index]
        env = dict(os.environ, RANKFLOW_GENERATION=str(node / stable_id),
                   RANKFLOW_DATABASE_URL=dsn, RANKFLOW_RESCUE_CONFIG=str(rescue),
                   RANKFLOW_SESSION_KEY=uuid, RANKFLOW_CONFIG_POLL_SECONDS=".25",
                   RANKFLOW_CONVERGENCE_SECONDS="3", RANKFLOW_MINIMUM_CAPACITY="2")
        with (root / f"node{index}.log").open("wb") as log:
            child = subprocess.Popen([sys.executable, "-m", "uvicorn", "rankflow.api:from_environment",
                                      "--factory", "--port", url.rsplit(":", 1)[1]],
                                     env=env, stdout=log, stderr=log)
        children.append(child)

    client = httpx.Client(timeout=4, trust_env=False)
    evidence = {"poll_seconds": .25, "probe_interval_seconds": .05,
                "routing": "direct probing with fresh serving_ready checks", "phases": []}

    def probe(index):
        try:
            return client.get(nodes[index][1] + "/health/ready").raise_for_status().json()
        except httpx.ConnectError:
            return {}

    def until(predicate, timeout=110):
        end = monotonic() + timeout
        while monotonic() < end:
            result = predicate()
            if result:
                return result
            sleep(.05)
        raise AssertionError(f"Timed out: {[probe(i) for i in range(len(nodes))]}")

    def converge(revision, label, indices=range(3), started=None):
        started = monotonic() if started is None else started
        seen = {}
        history = []

        def record():
            sample = []
            for index in indices:
                value = probe(index)
                elapsed = round(monotonic() - started, 6)
                sample.append({"node": index, "elapsed_seconds": elapsed,
                               "revision": value.get("config_revision"),
                               "serving_ready": value.get("serving_ready")})
                if value.get("serving_ready") and value.get("config_revision") == revision:
                    seen.setdefault(index, elapsed)
            state = [(row["revision"], row["serving_ready"]) for row in sample]
            if not history or state != [(row["revision"], row["serving_ready"]) for row in history[-1]]:
                history.append(sample)
            return len(seen) == len(indices)

        until(record)
        evidence["phases"].append({"scenario": label, "revision": revision,
                                   "observed_upper_bound_seconds": max(seen.values()), "samples": history})

    launch(0)
    launch(1)
    converge(0, "stable startup", range(2))
    shadowing = replace(stable, state="shadowing")
    control.publish(shadowing, 0, "stage3-shadow", "stage3")
    converge(1, "shadowing transition", range(2))
    candidate = replace(shadowing, state="canary", canary_generation_id=candidate_id, canary_percent=100)
    control.prepare(candidate)
    until(lambda: len([row for row in control.fleet() if row["leased"]
                       and candidate.config_id in row["prepared"]]) == 2)
    started = monotonic()
    control.publish(candidate, 1, "stage3-canary", "stage3")
    converge(2, "canary activation", range(2), started)
    launch(2)
    until(lambda: probe(2).get("serving_ready") is False)
    third = probe(2)
    assert third["target_revision"] == 2 and third["release_ready"] is False
    assert client.get(nodes[2][1] + "/health/live").json()["live"]
    traffic = {"request_id": "stage3-three-process", "session_id": "fixture-session", "events": []}
    eligible = [i for i in range(3) if probe(i).get("serving_ready")]
    assert eligible == [0, 1]
    for i in eligible:
        response = client.post(nodes[i][1] + "/v1/recommend", json=traffic).raise_for_status().json()
        assert response["assignment"] == "canary" and response["serving_generation"] == candidate_id
    assert client.post(nodes[2][1] + "/v1/recommend", json=traffic).status_code == 503
    evidence["unprepared"] = {"expected": "live but unroutable", "observed": third,
                              "canary_requests_routed": eligible}
    shutil.copytree(fixture, nodes[2][0] / candidate_id)
    converge(2, "late node catches up")
    until(lambda: all(row["revision"] == 2 for row in control.fleet() if row["leased"]))
    started = monotonic()
    control.publish(stable.config_id, 2, "stage3-rollback", "stage3", "rollback")
    converge(3, "named rollback", started=started)
    killed = replace(stable, state="killed")
    started = monotonic()
    control.publish(killed, 3, "stage3-kill", "stage3", "kill")
    converge(4, "kill switch", started=started)
    for _, url in nodes:
        response = client.post(url + "/v1/recommend", json=traffic).raise_for_status().json()
        assert response["config_id"] == killed.config_id and response["assignment"] == "stable"
    with store.connect() as conn:
        audit = conn.execute("SELECT action, config_id, revision FROM traffic_audit ORDER BY revision").fetchall()
        assert [(a["action"], a["config_id"]) for a in audit[-2:]] == [
            ("rollback", stable.config_id), ("kill", killed.config_id)]
        evidence["audit"] = audit
    client.close()
    return evidence


if __name__ == "__main__":
    uuid = uuid4().hex
    schema = sql.Identifier("release_drill_" + uuid)
    admin = PostgresStore(os.environ["RANKFLOW_TEST_DATABASE_URL"])
    with admin.connect() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(schema))
    children = []
    try:
        with TemporaryDirectory() as directory:
            try:
                print(json.dumps(run(Path(directory), make_conninfo(admin.dsn,
                                     application_name="rankflow-release-drill",
                                     options=f"-c search_path=release_drill_{uuid}"), children), indent=2))
            finally:
                for child in children:
                    child.terminate()
                for child in children:
                    child.wait(timeout=10)
    finally:
        with admin.connect() as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(schema))

