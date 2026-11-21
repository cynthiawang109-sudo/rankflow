"""Authenticated release, experiment and data-provenance views."""
from dataclasses import asdict
import hashlib
import hmac
from html import escape
import json
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from .operations import ALERT_CATALOGUE
from .drift import reports as drift_reports
from .security import LEVELS, csrf
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
            if document["record"].get("window") != "W3" and hmac.compare_digest(expected, document["signature"]):
                yield document


def install_console(app, store, traffic, bearers, release_registry=None, signing_key=None, guardrails=None):
    def require(minimum):
        def authenticate(request: Request):
            actual = request.headers.get("authorization", "").encode()
            role = next((role for role, token in bearers.items()
                         if hmac.compare_digest(actual, b"Bearer " + token)), None)
            if not role or LEVELS[role] < LEVELS[minimum]:
                if request.url.path == "/operator/releases":
                    app.state.count("protected_release_read_denied")
                if role:
                    raise HTTPException(403, "insufficient_role")
                raise HTTPException(401, "operator_authentication_required", headers={"WWW-Authenticate": "Bearer"})
            if request.method == "POST":
                csrf(request)
            return role

        return authenticate

    operator_role, admin_role = require("operator"), require("admin")
    viewer_role = require("viewer")
    viewer_only = [Depends(viewer_role)]
    operator_only = [Depends(operator_role)]

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

    @app.get("/operator", response_class=HTMLResponse, dependencies=viewer_only)
    def console():
        return HTMLResponse("""<!doctype html><html lang="en"><meta charset="utf-8">
<title>RankFlow Operator Console</title><h1>RankFlow Operator Console</h1>
<nav><ul><li><a href="/operator/status">Traffic, generations and health</a></li>
<li><a href="/operator/releases">Release and evaluation history</a></li>
<li><a href="/operator/events">Provenance, outbox and acknowledgement counts</a></li>
<li><a href="/operator/epochs">Evaluation epochs</a></li></ul></nav>
<form action="/operator/drift"><label>Drift demo ID <input name="demo_id" required></label>
<button>View drift measurements and alerts</button></form></html>""", headers={"Cache-Control": "no-store"})

    @app.get("/operator/drift", response_class=HTMLResponse, dependencies=viewer_only)
    def drift(demo_id: str):
        if not (store and signing_key):
            raise HTTPException(503, "drift_audit_unavailable")
        records = drift_reports(store, signing_key, demo_id)
        if not records:
            raise HTTPException(404, "drift_demo_not_found")
        evidence = escape(json.dumps(records, indent=2))
        return HTMLResponse(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<title>RankFlow Operator Console | Feature drift</title>'
            '<h1>Feature drift demo</h1><pre>' + evidence + '</pre></html>',
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/operator/status", dependencies=viewer_only)
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
        readiness = traffic.readiness() if traffic else {"serving_ready": True, "release_ready": True}
        readiness["release_ready"] = bool(readiness["release_ready"] and store and store.ready())
        convergence = history[0]["convergence"] if history else None
        return {"live": True, **readiness, "generations": generations,
                "configuration": asdict(pin.config) if pin else None,
                "config_id": pin.config.config_id if pin else None,
                "revision": pin.revision if pin else None, "traffic_history": history,
                "instances": fleet, "convergence": convergence,
                "guardrail_health": guardrails.status if guardrails else None,
                "live_shadow_counters": {name: value for name, value in app.state.counters.copy().items()
                                         if name.startswith("synthetic_shadow_")}}

    @app.get("/operator/releases", dependencies=operator_only)
    def releases():
        return list(verified_records(release_registry, signing_key))

    @app.get("/operator/runbook", response_class=HTMLResponse, dependencies=viewer_only)
    def runbook():
        return """<h1>RankFlow operations runbook</h1>
<h2 id="canary-health">Canary health</h2>
<p>Check closed canary windows and the auto_pause audit row. If the pause failed,
page the on-call operator and POST /operator/traffic/kill with the current revision
and a new operation ID. Investigate missing telemetry or scoring failures before resuming.</p>
<h2 id="database-and-outbox">Database and outbox</h2>
<p>Page the database on-call. Check connectivity and the oldest pending outbox
event. Restore connectivity and verify delivery resumes. Degraded responses have no attribution ID.</p>
<h2 id="fleet-convergence">Fleet convergence</h2>
<p>Read the instance revisions and prior stable config_id from traffic history.
POST /operator/traffic/rollback with that rollback_config_id, the current
expected_revision and a new operation ID. Verify every serving instance reports the rollback revision.</p>"""

    @app.get("/operator/metrics")
    def metrics(role: str = Depends(viewer_role)):
        groups = []
        if store:
            with store.connect() as conn:
                groups = conn.execute("""
                    SELECT coalesce(d.payload->>'assigned_generation_id', i.generation) AS generation,
                           d.payload->>'assignment' AS cohort, d.payload->>'source' AS source,
                           count(*) FILTER (WHERE i.created_at + %s <= statement_timestamp()) AS closed_impressions,
                           count(a.impression_id) FILTER (WHERE i.created_at + %s <= statement_timestamp()) AS confirmed,
                           count(*) FILTER (WHERE i.send_state = 'send_completed') AS send_completed,
                           count(*) FILTER (WHERE i.send_state = 'send_failed') AS send_failed,
                           count(*) FILTER (WHERE i.send_state = 'send_unknown') AS send_unknown,
                           count(*) FILTER (WHERE o.delivered_at IS NULL AND o.event_id IS NOT NULL) AS pending_outbox,
                           max(extract(epoch FROM statement_timestamp() - o.created_at))
                               FILTER (WHERE o.delivered_at IS NULL) AS oldest_pending_seconds,
                           count(*) FILTER (WHERE s.payload->>'comparison_status' = 'compared') AS compared_shadow,
                           sum(1 - (s.payload->>'top_k_overlap')::numeric /
                               nullif((s.payload->>'top_k')::numeric, 0))
                               FILTER (WHERE s.payload->>'comparison_status' = 'compared') AS shadow_divergence_sum
                    FROM impressions i JOIN decisions d ON d.impression_id = i.id
                    LEFT JOIN acknowledgements a ON a.impression_id = i.id AND a.kind = 'confirmed'
                    LEFT JOIN outbox o ON o.impression_id = i.id
                    LEFT JOIN shadow_observations s ON s.impression_id = i.id
                    GROUP BY 1, 2, 3
                    """, (store.ack_window, store.ack_window)).fetchall()
        return {"instance_id": traffic.instance_id if traffic else None,
                "requests": app.state.request_metrics.snapshot(), "durable": groups,
                "alert_catalogue": ALERT_CATALOGUE,
                "experiment": traffic.pin().config.state if traffic else None,
                "gate_decisions": [record["record"]["decision"]
                                   for record in verified_records(release_registry, signing_key)]
                                  if LEVELS[role] >= LEVELS["operator"] else None,
                "canary": guardrails.status if guardrails else None}

    @app.get("/operator/events", dependencies=viewer_only)
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
                    SELECT payload->>'config_id' AS config_id, payload->>'shadow_generation' AS shadow_generation,
                           count(*) AS observations,
                           avg((payload->>'top_k_overlap')::integer) AS mean_top_k_overlap
                    FROM shadow_observations GROUP BY 1, 2
                    """).fetchall(),
                "outbox": conn.execute("""
                    SELECT count(*) FILTER (WHERE delivered_at IS NULL) AS pending,
                           count(*) FILTER (WHERE delivered_at IS NOT NULL) AS delivered FROM outbox
                    """).fetchone(),
                "acknowledgements": conn.execute("""
                    SELECT kind, count(*) AS total FROM acknowledgements GROUP BY kind
                    """).fetchall(),
            }

    @app.get("/operator/epochs", dependencies=viewer_only)
    def epochs():
        if store is None:
            raise HTTPException(503, "epoch_registry_unavailable")
        with store.connect() as conn:
            return conn.execute("SELECT * FROM evaluation_epochs ORDER BY registered_at").fetchall()

    @app.post("/operator/epochs")
    def add_epoch(manifest: dict, role: str = Depends(admin_role)):
        if store is None:
            raise HTTPException(503, "epoch_registry_unavailable")
        try:
            return {"registered": register_epoch(store, manifest, audit=(signing_key or bearers[role], role))}
        except (TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/operator/prepare")
    def prepare(configuration: dict, role: str = Depends(operator_role)):
        if traffic is None:
            raise HTTPException(503, "traffic_control_unavailable")
        try:
            return {"config_id": traffic.prepare(TrafficConfigSnapshot(**configuration),
                                                       audit=(signing_key or bearers[role], role))}
        except (OSError, TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error

    @app.post("/operator/traffic/{action}")
    def change(action: str, operation: PublishRequest, role: str = Depends(operator_role)):
        if traffic is None:
            raise HTTPException(503, "traffic_control_unavailable")
        try:
            if action == "rollback" and operation.rollback_config_id and operation.configuration is None:
                target = operation.rollback_config_id
            elif action in {"publish", "kill", "resolve", "override"} and operation.configuration and operation.rollback_config_id is None:
                target = TrafficConfigSnapshot(**operation.configuration)
            else:
                raise ValueError("Invalid traffic operation")
            if (action == "resolve" or getattr(target, "state", None) == "promoted") and role != "admin":
                raise HTTPException(403, "admin_role_required")
            revision = traffic.publish(target, operation.expected_revision, operation.operation_id, role, action,
                                       reason=operation.reason, override_seconds=operation.override_seconds,
                                       audit_key=signing_key or bearers[role])
        except (TypeError, ValueError) as error:
            raise HTTPException(409, str(error)) from error
        return {"state": "pointer_committed", "revision": revision}
