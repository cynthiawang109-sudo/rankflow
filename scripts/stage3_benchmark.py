"""Measure Alpha stage timing and client latency on the local host."""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import logging
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from time import perf_counter, sleep
from uuid import uuid4

import httpx
import psutil
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo

from rankflow.api import create_app
from rankflow.generation import cached_generation
from rankflow.store import PostgresStore
from rankflow.traffic import TrafficConfigSnapshot, TrafficRegistry
from scripts.stage3_release import port


class Timings(logging.Handler):
    def __init__(self):
        super().__init__()
        self.stages = defaultdict(list)

    def emit(self, record):
        row = json.loads(record.getMessage())
        request_id = row.get("request_id") or ""
        if row["event"] == "ranking_outcome":
            self.stages[request_id.split(":")[0]].append([row[field] for field in
                                                        ("retrieval_ms", "feature_ms", "scoring_ms")])


def p95(values):
    return round(sorted(values)[math.ceil(.95 * len(values)) - 1], 3)


def run(source, dsn):
    with TemporaryDirectory() as directory:
        cold = perf_counter()
        generation = cached_generation(source, Path(directory))
        cache_load_ms = (perf_counter() - cold) * 1000
        manifest = json.loads((source / "manifest.json").read_bytes())
        sizes = {name: (source / name).stat().st_size for name in ["manifest.json", *manifest["checksums"]]}
        store = PostgresStore(dsn)
        store.initialize()
        stable = TrafficConfigSnapshot(generation.generation_id)
        traffic = TrafficRegistry(store, source.parent, stable, {"v1": os.urandom(32)})
        traffic.generations[generation.generation_id] = generation
        # The in-memory benchmark challenger reuses the verified rule bundle.
        candidate = replace(generation, generation_id="gen-" + "f" * 64)
        traffic.generations[candidate.generation_id] = candidate
        traffic.initialize()
        traffic.refresh()
        app = create_app(generation, store, traffic=traffic)
        service_port = port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=service_port, access_log=False))
        thread = Thread(target=server.run)
        handler = Timings()
        logger = logging.getLogger("rankflow.operations")
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
        thread.start()
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{service_port}", timeout=15, trust_env=False) as client:
                deadline = perf_counter() + 15
                while not server.started:
                    if perf_counter() > deadline:
                        raise RuntimeError("Benchmark API startup timed out")
                    sleep(.02)
                examples = generation.examples["W2-dev"]
                process = psutil.Process()

                def measure(label, parallelism):
                    peak = [process.memory_info().rss]
                    stop = Event()

                    def sample():
                        while not stop.wait(.02):
                            peak[0] = max(peak[0], process.memory_info().rss)

                    def request(index):
                        events = examples[index % len(examples)]["events"]
                        started = perf_counter()
                        response = client.post("/v1/recommend", json={
                            "request_id": f"{label}:{index}", "session_id": str(index), "events": events})
                        elapsed = (perf_counter() - started) * 1000
                        return elapsed, response.status_code

                    sampler = Thread(target=sample)
                    sampler.start()
                    try:
                        with ThreadPoolExecutor(parallelism) as executor:
                            replies = list(executor.map(request, range(48)))
                    finally:
                        stop.set()
                        sampler.join()
                    stages = handler.stages[label][:48]
                    return {"requests": len(replies), "http_errors": sum(code != 200 for _, code in replies),
                            "concurrency": parallelism, "client_p95_ms": p95([ms for ms, _ in replies]),
                            "peak_api_rss_bytes": peak[0],
                            "ranking_sample_count": len(stages),
                            "retrieval_p95_ms": p95([row[0] for row in stages]),
                            "feature_p95_ms": p95([row[1] for row in stages]),
                            "scoring_p95_ms": p95([row[2] for row in stages])}

                baseline = measure("stable", 4)
                peak = measure("peak", 12)
                shadow = replace(stable, state="shadowing", shadow_generation_id=candidate.generation_id,
                                 shadow_mode="live")
                traffic.publish(shadow, 0, "benchmark-shadow", "benchmark")
                traffic.refresh()
                shadowed = measure("shadow", 4)
                drained = perf_counter() + 10
                while sum(app.state.counters[name] for name in (
                        "synthetic_shadow_completed", "synthetic_shadow_failed",
                        "synthetic_shadow_shed", "synthetic_shadow_timed_out")) < 48:
                    if perf_counter() > drained:
                        raise RuntimeError("Shadow work did not settle")
                    sleep(.02)
                shadowed["shadow_counters"] = dict(app.state.counters)
                canary = replace(shadow, state="canary", canary_percent=100,
                                 canary_generation_id=candidate.generation_id,
                                 shadow_generation_id=None, shadow_mode=None)
                traffic.prepare(canary)
                traffic.refresh()
                traffic.publish(canary, 1, "benchmark-canary", "benchmark")
                traffic.refresh()
                canary_results = measure("canary", 4)
                return {"artifact_bytes": sizes, "cold_verified_cache_ms": round(cache_load_ms, 3),
                        "stable": baseline, "peak": peak, "shadow": shadowed, "canary_fixture": canary_results,
                        "shadow_minus_stable_client_p95_ms": round(
                            shadowed["client_p95_ms"] - baseline["client_p95_ms"], 3)}
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            logger.removeHandler(handler)


if __name__ == "__main__":
    root = Path("artifacts/stage1/generations")
    source = root / (root / "alpha.txt").read_text().strip()
    name = "benchmark_" + uuid4().hex
    admin = PostgresStore(os.environ["RANKFLOW_TEST_DATABASE_URL"])
    with admin.connect() as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        print(json.dumps(run(source, make_conninfo(admin.dsn, options=f"-c search_path={name}")), indent=2))
    finally:
        with admin.connect() as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))
