"""RankFlow Product Alpha API."""
import asyncio
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
import hashlib
import hmac
import logging
import math
import os
from pathlib import Path
import secrets
from threading import BoundedSemaphore, Lock
from time import perf_counter
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .features import FEATURE_VERSION, build_features
from .generation import Generation
from .retrieval import retrieve
from .strategies import RULE

LOGGER = logging.getLogger(__name__)
EventAid = Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
MAX_BODY = 64 * 1024


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(Input):
    aid: EventAid
    ts: Annotated[int, Field(strict=True, ge=0, le=2**63 - 1)]
    type: Literal["clicks", "carts", "orders"]


class Recommendation(Input):
    request_id: Identifier
    session_id: Identifier
    events: Annotated[list[Event], Field(max_length=500)]
    top_k: Annotated[int, Field(strict=True, ge=1, le=100)] = 20

    @model_validator(mode="after")
    def check_event_order(self):
        if any(left.ts > right.ts for left, right in zip(self.events, self.events[1:])):
            raise ValueError("Event timestamps must be monotonic")
        return self


class Feedback(Input):
    event_id: Identifier
    impression_id: Identifier | None
    aid: EventAid
    action: Literal["click", "cart", "order"]
    occurred_at: datetime
    source: Literal["demo"]

    @model_validator(mode="after")
    def check_timezone(self):
        if self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return self


def rank_request(generation, events, top_k, deadline_ms, compare=False):
    snapshot = generation.snapshot
    candidates = retrieve(snapshot, events, generation.config)
    rows = build_features(snapshot, events, candidates)
    unknown = sum(event["aid"] not in snapshot.popularity_ranks for event in events)
    assigned = generation.assigned
    served = assigned
    reason = None
    scoring_path = assigned.strategy_type
    if unknown == len(events):
        # Scores are from the popularity path even when ML is assigned.
        ranking = RULE.rank(candidates, rows)
        scoring_path = "popularity"
    elif assigned.strategy_type == "lightgbm":
        started = perf_counter()
        try:
            ranking = assigned.rank(candidates, rows)
            if (perf_counter() - started) * 1000 >= deadline_ms:
                raise TimeoutError
            if not all(math.isfinite(score) for _, score in ranking):
                raise ValueError("Non-finite model scores")
        except Exception as error:
            reason = "logical_deadline" if isinstance(error, TimeoutError) else "ml_scoring_error"
            served, scoring_path = RULE, "rule"
            ranking = RULE.rank(candidates, rows)
    else:
        ranking = RULE.rank(candidates, rows)

    def items(scored):
        return [{"aid": candidate.aid, "rank": rank, "score": score,
                 "sources": candidate.provenance()}
                for rank, (candidate, score) in enumerate(scored[:top_k], 1)]

    result = {"assigned_strategy": assigned.strategy_id, "served_strategy": served.strategy_id,
              "assignment": "stable", "serving_generation": generation.generation_id,
              "retrieval_snapshot_id": snapshot.snapshot_id, "feature_version": FEATURE_VERSION,
              "fallback_used": reason is not None, "items": items(ranking)}
    decision = {"fallback_reason": reason, "unknown_aid_count": unknown,
                "candidate_count": len(candidates), "scoring_path": scoring_path}
    if compare:
        challenger = generation.challenger
        try:
            comparison_path = "popularity" if scoring_path == "popularity" else challenger.strategy_type
            alternative = items((RULE if comparison_path == "popularity" else challenger).rank(candidates, rows))
            left = {candidate.aid: rank for rank, (candidate, _) in enumerate(ranking, 1)}
            right = {item["aid"]: item["rank"] for item in alternative}
            intersection = {item["aid"] for item in result["items"]} & right.keys()
            result["comparison"] = {"mode": "ranker-only", "strategy": challenger.strategy_id,
                                    "scoring_path": comparison_path,
                                    "items": alternative, "top_k_overlap": len(intersection),
                                    "same_rank": sum(left[aid] == right[aid] for aid in intersection),
                                    "movements": {aid: left[aid] - rank for aid, rank in right.items()}}
        except Exception:
            LOGGER.exception("Playground comparison failed")
            result["comparison"] = {"mode": "ranker-only", "status": "unavailable"}
    return result, decision


class DeliveryObservation:
    def __init__(self, app, store):
        self.app, self.store = app, store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"] == "POST":
            incoming = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                incoming.extend(message.get("body", b""))
                if len(incoming) > MAX_BODY:
                    await send({"type": "http.response.start", "status": 413,
                                "headers": [(b"content-type", b"application/json")]})
                    await send({"type": "http.response.body", "body": b'{"detail":"payload_too_large"}'})
                    return
                if not message.get("more_body"):
                    break

            original_receive = receive

            async def receive():
                nonlocal incoming
                if incoming is None:
                    return await original_receive()
                body, incoming = bytes(incoming), None
                return {"type": "http.request", "body": body, "more_body": False}

        async def observe(message):
            impression_id = scope.get("state", {}).get("persisted_impression")
            try:
                await send(message)
            except BaseException:
                if impression_id:
                    await run_in_threadpool(self.record, impression_id, "send_failed")
                raise
            if impression_id and message["type"] == "http.response.body" and not message.get("more_body"):
                await run_in_threadpool(self.record, impression_id, "send_completed")

        await self.app(scope, receive, observe)

    def record(self, impression_id, state):
        try:
            self.store.record_send(impression_id, state)
        except Exception:
            LOGGER.exception("Send observation could not be persisted")


async def consume_outbox(store, stop):
    delay = 0.5
    while not stop.is_set():
        try:
            delivered = await run_in_threadpool(store.drain)
            delay = 0.5
            if delivered:
                continue
        except Exception:
            LOGGER.exception("Outbox delivery will retry")
            delay = min(delay * 2, 30)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass


def create_app(generation, store=None, session_key=None, deadline_ms=20, traffic=None,
               admin_bearer=None, release_registry=None, signing_key=None):
    session_key = session_key or secrets.token_bytes(32)
    shadow_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rankflow-shadow") if traffic else None
    shadow_capacity = BoundedSemaphore(2)
    guardrails = None
    if store and traffic:
        from .guardrails import Guardrails

        guardrails = Guardrails(store, traffic)

    @asynccontextmanager
    async def lifespan(app):
        stop = asyncio.Event()
        worker = traffic_worker = None
        if store:
            await run_in_threadpool(store.initialize)
            worker = asyncio.create_task(consume_outbox(store, stop))
        if traffic:
            await run_in_threadpool(traffic.initialize)
            await run_in_threadpool(traffic.refresh)
            async def refresh_traffic():
                while not stop.is_set():
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=traffic.poll_seconds)
                    except TimeoutError:
                        await run_in_threadpool(traffic.refresh)
                        if not traffic.pin().degraded:
                            try:
                                await run_in_threadpool(traffic.observe_convergence)
                            except Exception:
                                LOGGER.exception("Traffic convergence observation failed")
                        if guardrails:
                            await run_in_threadpool(guardrails.sample, traffic.pin())
            traffic_worker = asyncio.create_task(refresh_traffic())
        try:
            yield
        finally:
            stop.set()
            if worker:
                await worker
            if traffic_worker:
                await traffic_worker
            if shadow_executor:
                await run_in_threadpool(shadow_executor.shutdown)

    app = FastAPI(title="RankFlow", lifespan=lifespan)
    app.state.counters = Counter()
    counters_lock = Lock()

    def count(name):
        with counters_lock:
            app.state.counters[name] += 1
    app.add_middleware(DeliveryObservation, store=store)

    def csrf(request):
        token = request.cookies.get("rankflow_csrf")
        supplied = request.headers.get("x-csrf-token", "")
        if (token or request.headers.get("origin")) and (not token or not hmac.compare_digest(token, supplied)):
            raise HTTPException(403, "csrf_token_required")

    @app.get("/health/live")
    def live():
        return {"live": True}

    @app.get("/health/ready")
    def ready():

        pin = traffic.pin() if traffic else None
        return {"serving_ready": True, "release_ready": bool(store and store.ready() and
                (pin is None or not pin.degraded)),
                **({"config_id": pin.config.config_id, "config_revision": pin.revision} if pin else {})}

    @app.get("/playground", response_class=HTMLResponse)
    def playground():
        token = secrets.token_urlsafe(32)
        response = HTMLResponse(Path(__file__).with_name("playground.html").read_text(encoding="utf-8-sig")
                                .replace("__CSRF__", token))
        response.headers["Cache-Control"] = "no-store"
        response.set_cookie("rankflow_csrf", token, httponly=True, samesite="strict")
        return response

    @app.get("/v1/playground/prefixes")
    def prefixes(window: str = "W2-dev"):
        if window not in generation.examples:
            count("public_window_denied")
            LOGGER.warning("Public Playground partition read denied")
            raise HTTPException(404, "window_unavailable")
        return generation.examples[window]

    def recommend(data, request, compare):
        csrf(request)
        started = perf_counter()
        events = [event.model_dump() for event in data.events]
        session_hash = hmac.new(session_key, data.session_id.encode(), hashlib.sha256).hexdigest()
        pin = traffic.pin() if traffic else None
        selected, cohort = pin.select(session_hash) if pin else (generation, "stable")
        if events and events[-1]["ts"] <= selected.snapshot.watermark:
            raise HTTPException(422, "cutoff_must_follow_snapshot")
        result, decision = rank_request(selected, events, data.top_k, deadline_ms, compare)
        if pin:
            result.update(config_id=pin.config.config_id, config_revision=pin.revision, assignment=cohort)
            decision.update(assigned_generation_id=selected.generation_id,
                            served_generation_id=selected.generation_id, traffic_degraded=pin.degraded)
            if pin.shadow:
                count("synthetic_shadow_attempted")
                if shadow_capacity.acquire(blocking=False):
                    def evaluate_shadow():
                        try:
                            comparison, reasons = rank_request(pin.shadow, events, data.top_k, deadline_ms)
                            actual = {item["aid"]: item["rank"] for item in result["items"]}
                            alternative = {item["aid"]: item["rank"] for item in comparison["items"]}
                            common = actual.keys() & alternative.keys()
                            overlap = len(common)
                            same_rank = sum(actual[aid] == alternative[aid] for aid in common)
                            if store and result["impression_id"]:
                                store.record_shadow(result["impression_id"], {
                                    "source": "demo", "mode": "live", "comparison": "full-generation",
                                    "validation": "synthetic operational validation",
                                    "config_id": pin.config.config_id,
                                    "served_generation": selected.generation_id,
                                    "shadow_generation": pin.shadow.generation_id,
                                    "top_k": data.top_k, "top_k_overlap": overlap,
                                    "intersection_size": overlap, "rank_agreement": same_rank / overlap if overlap >= 2 else None,
                                    "comparison_status": "compared" if overlap >= 2 else "insufficient_overlap",
                                    "shadow_fallback_used": comparison["fallback_used"],
                                    "shadow_fallback_reason": reasons["fallback_reason"],
                                })
                            if reasons["fallback_reason"] == "logical_deadline":
                                count("synthetic_shadow_timed_out")
                            elif comparison["fallback_used"]:
                                count("synthetic_shadow_failed")
                            else:
                                count("synthetic_shadow_completed")
                        except Exception:
                            LOGGER.exception("Synthetic live shadow failed")
                            count("synthetic_shadow_failed")

                    async def shadow():
                        try:
                            await asyncio.get_running_loop().run_in_executor(shadow_executor, evaluate_shadow)
                        finally:
                            shadow_capacity.release()

                    request.state.shadow_task = shadow
                else:
                    count("synthetic_shadow_shed")
        result.update(request_id=data.request_id, impression_id=None, logging_status="degraded")
        if store:
            decision.update(result)
            decision.update(cutoff_ts=events[-1]["ts"] if events else None,
                            decision_latency_ms=round((perf_counter() - started) * 1000, 3),
                            source="demo", prefix_events=events, surface="playground" if compare else "api")
            decision["session_hash"] = session_hash
            decision["session_key_id"] = os.environ.get("RANKFLOW_SESSION_KEY_ID", "local-v1")
            try:
                impression_id = store.persist(decision)
                result.update(impression_id=impression_id, logging_status="persisted")
                request.state.persisted_impression = impression_id
                count("impressions_persisted")
            except Exception:
                LOGGER.exception("Recommendation decision persistence failed")
        count("impressions_served")
        result["latency_ms"] = round((perf_counter() - started) * 1000, 3)
        if task := getattr(request.state, "shadow_task", None):
            return JSONResponse(result, background=BackgroundTask(task))
        return result

    @app.post("/v1/recommend")
    def recommend_api(data: Recommendation, request: Request):
        return recommend(data, request, False)

    @app.post("/v1/playground/rank")
    def recommend_playground(data: Recommendation, request: Request):
        return recommend(data, request, True)

    @app.post("/v1/feedback")
    def feedback(data: Feedback, request: Request):
        csrf(request)
        if not data.impression_id or not store:
            raise HTTPException(404, "logging_degraded_no_decision")
        result = store.feedback(data.model_dump(mode="json"))
        if not result["attributed"]:
            count("unattributable_feedback")
            if result["reason"] == "outside_attribution_window":
                count("late_events")
            raise HTTPException(422, result["reason"])
        return result

    @app.post("/v1/impressions/{impression_id}/ack")
    def acknowledge(impression_id: Identifier, request: Request):
        csrf(request)
        result = store.ack(impression_id) if store else None
        if result is None:
            raise HTTPException(404, "logging_degraded_no_decision")
        return result

    if admin_bearer:
        from .operator_console import install_console

        install_console(app, store, traffic, admin_bearer, release_registry, signing_key, guardrails)
    return app


def from_environment():
    if configured := os.environ.get("RANKFLOW_GENERATION"):
        path = Path(configured)
    else:
        registry = Path(os.environ.get("RANKFLOW_GENERATION_REGISTRY", "artifacts/stage1/generations"))
        identifier = (registry / "alpha.txt").read_text(encoding="ascii").strip()
        if len(identifier) != 68 or not identifier.startswith("gen-") or any(
            character not in "0123456789abcdef" for character in identifier[4:]
        ):
            raise ValueError("Invalid Alpha generation identifier")
        path = registry / identifier
    from .store import PostgresStore

    store = None
    if dsn := os.environ.get("RANKFLOW_DATABASE_URL"):
        store = PostgresStore(dsn)
    key = os.environ.get("RANKFLOW_SESSION_KEY")
    traffic = None
    if rescue_path := os.environ.get("RANKFLOW_RESCUE_CONFIG"):
        import json
        from .traffic import TrafficConfigSnapshot, TrafficRegistry
        if not store or not key:
            raise ValueError("Traffic routing requires PostgreSQL and a shared session key")
        rescue = TrafficConfigSnapshot(**json.loads(Path(rescue_path).read_text(encoding="utf-8-sig")))
        control_dsn = os.environ.get("RANKFLOW_CONTROL_DATABASE_URL")
        control = PostgresStore(control_dsn) if control_dsn else store
        salts = {"v1": key.encode()}
        if salt_path := os.environ.get("RANKFLOW_ROUTING_SALTS"):
            configured_salts = json.loads(Path(salt_path).read_text(encoding="utf-8-sig"))
            if not isinstance(configured_salts, dict) or any(not isinstance(value, str) or not value
                                                           for value in configured_salts.values()):
                raise ValueError("Routing salts file must map version IDs to nonempty strings")
            salts.update({version: value.encode() for version, value in configured_salts.items()})
        traffic = TrafficRegistry(control, path.parent, rescue, salts)
    admin = os.environ.get("RANKFLOW_ADMIN_BEARER")
    signing_key = os.environ.get("RANKFLOW_RELEASE_SIGNING_KEY")
    return create_app(Generation.load(path), store, key.encode() if key else None, traffic=traffic,
                      admin_bearer=admin.encode() if admin else None,
                      release_registry=os.environ.get("RANKFLOW_RELEASE_REGISTRY"),
                      signing_key=signing_key.encode() if signing_key else None)
