"""Authenticated release, experiment and data-provenance views."""
from dataclasses import asdict
import hashlib
import hmac
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .epoch_registry import register_epoch
from .training_pipeline import canonical, read_json
from .traffic import TrafficConfigSnapshot


class PublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    operation_id: str = Field(min_length=1, max_length=128)
    configuration: dict | None = None
    rollback_config_id: str | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    override_seconds: int | None = Field(default=None, ge=1, le=600)


def verified_records(registry, key):
    if registry and key:
        for path in sorted(Path(registry).glob("*.json")):
            document = read_json(path)
            expected = hmac.new(key, canonical(document["record"]), hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, document["signature"]):
                yield document


def install_console(app, store, traffic, bearer, release_registry=None, signing_key=None, guardrails=None):
    def authenticate(request: Request):
        actual = request.headers.get("authorization", "")
        if not bearer or not hmac.compare_digest(actual.encode(), b"Bearer " + bearer):
            raise HTTPException(401, "operator_authentication_required", headers={"WWW-Authenticate": "Bearer"})

    operator_only = [Depends(authenticate)]

    if traffic:
        def approved(generation):
            for document in verified_records(release_registry, signing_key):
                record = document["record"]
                lineage = record["lineage"]
                if (record["decision"] == "approved" and lineage["source"] == "otto_offline"
                        and lineage["artifact_sha256"] == generation.assigned.artifact_hash
                        and lineage["retrieval_snapshot_id"] == generation.snapshot.snapshot_id):
                    return True
            return False

        traffic.promotion_allowed = approved

    @app.get("/operator", response_class=HTMLResponse, dependencies=operator_only)
    def console():
        return HTMLResponse("""<!doctype html><html lang="en"><meta charset="utf-8">
<title>RankFlow Operator Console</title><h1>RankFlow Operator Console</h1>
<nav><ul><li><a href="/operator/status">Traffic, generations and health</a></li>
<li><a href="/operator/releases">Release and evaluation history</a></li>
<li><a href="/operator/events">Provenance, outbox and acknowledgement counts</a></li>
<li><a href="/operator/epochs">Evaluation epochs</a></li></ul></nav></html>""", headers={"Cache-Control": "no-store"})

    @app.get("/operator/status", dependencies=operator_only)
    def status():
        pin = traffic.pin() if traffic else None
        generations, history = [], []
        if traffic:
            with traffic.lock:
                for path in sorted(traffic.generation_root.glob("gen-*")):
                    try:
                        generation = traffic.generation(path.name)
                    except (ValueError, OSError):
                        continue
                    generations.append({"generation_id": generation.generation_id,
                                        "strategy": generation.assigned.strategy_id,
                                        "snapshot_id": generation.snapshot.snapshot_id})
            with traffic.store.connect() as conn:
                history = conn.execute("""
                    SELECT a.*, t.state AS convergence, t.expected_instances, o.reason, o.expires_at
                    FROM traffic_audit a LEFT JOIN traffic_tracking t USING (revision)
                    LEFT JOIN traffic_overrides o USING (revision)
                    ORDER BY revision DESC LIMIT 100
                    """).fetchall()
            fleet = traffic.fleet()
        else:
            fleet = []
        leased = [instance for instance in fleet if instance["leased"]]
        convergence = None
        if history:
            revision = history[0]["revision"]
            convergence = "converged" if leased and all(
                instance["revision"] == revision for instance in leased) else "partially_converged"
        return {"live": True, "serving_ready": True, "release_ready": bool(store and store.ready() and
                (pin is None or not pin.degraded)), "generations": generations,
                "configuration": asdict(pin.config) if pin else None,
                "config_id": pin.config.config_id if pin else None,
                "revision": pin.revision if pin else None, "traffic_history": history,
                "instances": fleet, "convergence": convergence,
                "guardrail_health": guardrails.status if guardrails else None}

    @app.get("/operator/releases", dependencies=operator_only)
    def releases():
        return list(verified_records(release_registry, signing_key))

    @app.get("/operator/events", dependencies=operator_only)
    def events():
        if store is None:
            raise HTTPException(503, "event_store_unavailable")
        with store.connect() as conn:
            return {
                "provenance": conn.execute("""
                    SELECT payload->>'source' AS source, count(*) AS decisions
                    FROM decisions GROUP BY 1
                    """).fetchall(),
                "feedback": conn.execute("""
                    SELECT coalesce(payload->>'source', 'demo') AS source, count(*) AS attributed
                    FROM feedback_events GROUP BY 1
                    """).fetchall(),
                "live_shadow": conn.execute("""
                    SELECT payload->>'config_id' AS config_id, count(*) AS observations,
                           avg((payload->>'top_k_overlap')::integer) AS mean_top_k_overlap
                    FROM shadow_observations GROUP BY 1
                    """).fetchall(),
                "outbox": conn.execute("""
                    SELECT count(*) FILTER (WHERE delivered_at IS NULL) AS pending,
                           count(*) FILTER (WHERE delivered_at IS NOT NULL) AS delivered FROM outbox
                    """).fetchone(),
                "acknowledgements": conn.execute("""
                    SELECT kind, count(*) AS total FROM acknowledgements GROUP BY kind
                    """).fetchall(),
            }

    @app.get("/operator/epochs", dependencies=operator_only)
    def epochs():
        if store is None:
            raise HTTPException(503, "epoch_registry_unavailable")
        with store.connect() as conn:
            return conn.execute("SELECT * FROM evaluation_epochs ORDER BY registered_at").fetchall()

    @app.post("/operator/epochs", dependencies=operator_only)
    def add_epoch(manifest: dict):
        if store is None:
            raise HTTPException(503, "epoch_registry_unavailable")
        try:
            return {"registered": register_epoch(store, manifest)}
        except (TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/operator/prepare", dependencies=operator_only)
    def prepare(configuration: dict):
        if traffic is None:
            raise HTTPException(503, "traffic_control_unavailable")
        try:
            return {"config_id": traffic.prepare(TrafficConfigSnapshot(**configuration))}
        except (OSError, TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/operator/traffic/{action}", dependencies=operator_only)
    def change(action: str, operation: PublishRequest):
        if traffic is None:
            raise HTTPException(503, "traffic_control_unavailable")
        try:
            if action == "rollback" and operation.rollback_config_id and operation.configuration is None:
                target = operation.rollback_config_id
            elif action in {"publish", "kill", "resolve", "override"} and operation.configuration and operation.rollback_config_id is None:
                target = TrafficConfigSnapshot(**operation.configuration)
            else:
                raise ValueError("Invalid traffic operation")
            revision = traffic.publish(target, operation.expected_revision, operation.operation_id, "admin", action,
                                       reason=operation.reason, override_seconds=operation.override_seconds)
        except (TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return {"state": "pointer_committed", "revision": revision}
