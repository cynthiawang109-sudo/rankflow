# RankFlow — Codex Kickoff: Stage 3 (Operated Release)

**Repository:** `C:\PROJECTS\rankflow` (Stages 0–2 complete and independently accepted)
**Governing documents:** `SPEC.md` (v3.0, product scope FROZEN — Stage 3 definition in §12), `ADDENDUM.md` (v3.0.4, implementation baseline). Do not change product scope, stage definitions, or non-goals; record conflicts in `docs/open_questions.md`.
**Also incorporated:** the owner's Stage 2 acceptance explainer (2026-11-20), workstream A.

**Language:** All code, comments, docs, and commit messages in English.

## Standing facts (do not redo, do not relitigate)

- `lgbm-v1` was **rejected** by the single governed W2-gate comparison (registered slice regression beyond the 0.5pp tolerance); the signed decision is immutable. `rule-v1` is the stable strategy. Do NOT re-run the gate for `lgbm-v1`, and do not train a v2 in this stage — model improvement is a separate workstream the owner has not commissioned here.
- W3 remains sealed. W2-gate aggregates stay in the authenticated Operator Console only.
- Stage 3 proves the **operated** behaviour of the platform using the stable strategy and clearly-labelled test candidates where a second generation is needed. It does not require any ML promotion.

## Stage 3 packages (in this order; commit each separately)

### 3.1 Structured logging, metrics, and actionable alerts (SPEC §11.1/§11.2, Addendum R18/R19)

- Structured request/outcome logs keyed by request ID across API, ranking, persistence, and outbox paths; no silent catch-and-continue on any decision path.
- Metrics with explicit numerator/denominator definitions per generation, cohort, and provenance source: request volume, fallback rate, degraded-logging rate, confirmation rate (send states kept orthogonal to confirmation states, per Addendum B03/C05), outbox lag, shadow divergence, gate/experiment state.
- Canary health states `healthy / degraded / unknown` from the pre-registered rules; sustained `unknown` or sustained fallback triggers the configured fail-safe (pause canary progression) — exercised in a drill, not just implemented.
- Every alert in the catalogue is bound to a concrete operator action (pause, rollback to a named `config_id`, kill, page) and the runbook entry is linked from the alert definition.

### 3.2 Multi-instance release behaviour (SPEC §10.2/§11, Addendum R23/F02/C02)

- Local multi-instance deployment (≥3 API instances) behind a simple local load balancer or direct per-instance probing: publish a new TrafficConfigSnapshot and measure per-instance convergence (config revision observed per instance over time); report the convergence bound actually achieved.
- Readiness semantics verified end to end: an instance that has not preloaded both generations of an activating canary config does not report `serving_ready` for that config and receives no canary traffic in the drill; `live`, `serving_ready`, `release_ready` stay distinct.
- Rollback drill to a named `config_id` and kill-switch drill at multi-instance scope, with audit history; stale-config instances are detected and reported, never silently serving mixed components.

### 3.3 Process isolation and inference failure behaviour (SPEC §10.1, Addendum R29)

- Model scoring runs isolated from request handling (separate process or bounded executor with hard resource limits): a hung or crashing scorer cannot block the API; the logical deadline produces a rule fallback with `assigned ≠ served` and the reason logged.
- Artifact distribution per Addendum R29: local content-addressed cache, checksum verification before load, atomic activation, bounded staleness; a corrupted or partial artifact is rejected and never partially served.
- Latency/resource report: retrieval + feature + scoring latency breakdown at the Alpha configuration, peak memory per instance, artifact sizes, and the measured cost of shadow mode.

### 3.4 Fault-injection suite (SPEC §10.3; Addendum stage mapping)

Automated, repeatable fault drills with pass/fail evidence per scenario: PostgreSQL unavailable at request time (degraded logging path), outbox consumer crash mid-delivery and duplicate redelivery (exactly-one effective delivery), control-plane outage at startup (designated rescue config serves), corrupted model artifact, scorer process kill/hang, traffic-config publish during in-flight requests (request keeps its pinned config), clock skew on attribution windows. Each drill records expected vs observed behaviour.

### 3.5 Security and privacy pass (SPEC §11.3, Addendum R30/F01)

- Role enforcement verified by tests: public / viewer / operator / admin boundaries on every route, including W2-gate and W3 surfaces (public reads rejected and counted, as in T13).
- CSRF protection on cookie-authenticated mutations, admin bearer handling, rate/size limits on public endpoints, pseudonymisation key separation (session HMAC key vs routing salt), retention/deletion job for pseudonymous records executed in a drill.
- Dependency and secret hygiene: no secrets in repo or logs (scan evidence), pinned dependencies.

### 3.6 Backup and restore (Addendum R19)

- PostgreSQL backup of the control-plane state (registry, traffic configs, decisions, feedback) and restore into a clean environment; after restore, the system serves the stable generation and the audit history verifies (signatures intact). Record RPO/RTO actually measured in the drill.

## Tests (Stage 3 gate evidence)

- Addendum stage mapping for Stage 3: **T01** (kill-and-restart mid-request → no partial decision, no duplicate effective outbox delivery), **T16** (operator drills: rollback + kill switch executed and audited), **T19** (corrupted/partial artifact rejected), **T20** (publish during in-flight requests → pinned config honoured), **T21** (same-millisecond events keep distinct query identities end to end), **T22** (late ack after cohort close → `late_confirmation`, finalized report unchanged), **T23** (two instances publish concurrently → CAS admits exactly one, the loser retries on the new revision).
- All Stage 0–2 tests still pass.
- **Test-evidence rule (owner requirement, standing):** final acceptance run executes DB-backed tests with the test DSN configured; the summary states passed / failed / skipped counts explicitly. Skipped DB tests = incomplete.

## Acceptance (Stage 3 exit gate, SPEC §12)

Release behaviour is verified in a multi-instance deployment (3.2 drills), the fault-injection suite (3.4) passes with recorded evidence, alerts are demonstrably bound to actions (3.1), and the backup/restore drill (3.6) reproduces a serving system with intact audit history. An exit evidence document records every drill's expected vs observed outcome, including the measured config-convergence bound and the latency/resource report (3.3).

## Hard constraints

- No W2-gate re-runs, no new model candidates, W3 sealed.
- No Kafka/Kubernetes/MLflow/LLM. The cloud reference deployment (AWS Fargate/CDK) is Stage 4, not this stage — Stage 3 multi-instance evidence is local.
- Never fabricate metrics; every number comes from a recorded run or drill.
