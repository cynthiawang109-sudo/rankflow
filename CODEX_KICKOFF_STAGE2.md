# RankFlow — Codex Kickoff: Stage 2 (ML Platform Beta)

**Repository:** `C:\PROJECTS\rankflow` (Stage 0 signed off; Stage 1 accepted with independent evidence)
**Governing documents:** `SPEC.md` (v3.0, product scope FROZEN), `ADDENDUM.md` (v3.0.4, implementation baseline — its traffic-config, readiness, send/ack, and gate-governance semantics are binding). Do not change product scope, stage definitions, or non-goals; record conflicts in `docs/open_questions.md`.
**Also incorporated:** the owner's Stage 1 acceptance / Stage 2 recommendations (2026-11-20), including its guardrails table and exit checklist.

**Language:** All code, comments, docs, and commit messages in English.

## Baselines (pinned; do not redo, do not tune against W2-gate/W3)

- Retrieval: three-source with popularity quota (10/100/20), `candidate_cap=100`; W2-dev `candidate_recall@100` = 22.33%; snapshot `cd5b998f…` (see `docs/stage1_retrieval_ablation.md`).
- Strategies: `rule-v1` serves the Alpha (W2-dev HitRate@20 19.63%, MRR@20 0.1340); `lgbm-v1` is the candidate (19.94% / 0.1425 on W2-dev — development numbers only, **not** a release approval).
- Stage 0 limitation that must follow every model card and release report: boundary exclusion retains ≤20-event sessions at 62.1%, 21–100 at 23.1%, >100 at 4.6%; headline metrics describe the retained population, not all OTTO sessions.

## Step 0 — Stage 1 artifact baseline (first commit)

Write `docs/stage1_baseline_manifest.md` (+ JSON) enumerating the frozen Stage 1 outputs with versions/checksums where available: data/window/query manifests, retrieval configuration and snapshot, ablation report, feature schema + feature-code hash, `rule-v1` and `lgbm-v1` artifacts, W2-dev metric reports, Playground/exit evidence, and the test inventory (passed/skipped counts from the independent acceptance). Later variants create new immutable versions; nothing in this manifest is edited in place afterwards.

## Stage 2 packages (in this order; commit each separately)

### 2.1 Versioned training pipeline + lineage (SPEC §7.1/§9, Addendum R16/R22)

- CLI pipeline: governed dataset builder (W1 queries for training; label policy `nextclick-v1`; R6 all-negative handling) → feature build via the Stage 1 shared builder → LightGBM LambdaRank training with frozen, recorded config → offline evaluation → artifact registration.
- Every run records the full R16 lineage: run ID, data manifest + label-policy versions, feature schema + feature-code hash, retrieval snapshot, training config, random seed, code version, artifact checksum, evaluation protocol version. A reproducibility check re-runs the pipeline from the pinned manifest/config and confirms identical artifact metadata and evaluation numbers (state the tolerance and what is bit-identical vs numerically identical).
- Training/serving parity remains enforced by the shared feature builder.

### 2.2 W2-gate release decision (SPEC §9, Addendum R1/R15/R27/R28)

- Governed evaluator path only (authenticated/operator context; **no** W2-gate numbers on any public surface, per F01).
- Exactly **one** promotion comparison for `lgbm-v1` vs `rule-v1` on the pinned W2-gate population (epoch gate split, 50%) with the same retrieval snapshot and candidate configuration as the Alpha.
- Gate rule from the epoch configuration: primary metrics HitRate@20 and MRR@20; non-regression tolerance 0.5pp; session-cluster bootstrap confidence intervals (Addendum R28); report candidate coverage and the registered slices alongside.
- Output: a signed, auditable decision record (`approved` or `rejected`) in `docs/stage2_release_decision.md` + registry entry. If rejected, `rule-v1` stays stable and that is the recorded outcome — do not re-tune and re-run the gate in this stage.

### 2.3 Serving generations + safe release (SPEC §10, Addendum R13/R23/R25, C02/C03)

- Generation registry: immutable bundles (strategy artifact + config, feature schema + feature-code hash, retrieval snapshot, compatibility manifest, checksums); registration validates compatibility before a generation can become servable.
- Traffic configuration per Addendum v3.0.3/v3.0.4: the serving pointer references an immutable **TrafficConfigSnapshot**; updates are config-level CAS with `expected_revision`; each request pins the config snapshot it loaded, then selects stable/canary generation by cohort; both generations preloaded before a canary config can activate; rollback names a `config_id` (never "the previous pointer"); a pre-provisioned **rescue config** (stable-only, minimal dependencies) is the final fallback when config loading fails.
- Cohort assignment: HMAC-based sticky assignment keyed by the pseudonymous session key (versioned salt), per Addendum R23; experiment state machine `draft → shadowing → canary → promoted / rolled_back / killed` with audited transitions; kill switch forces stable-only serving.
- Shadow, both modes (R25): `candidate_offline_replay` over historical queries, and live shadow on demo traffic — shadow results never alter served responses and are labelled synthetic operational validation, never online lift.
- Readiness signals separated (C02): `live`, `serving_ready`, `release_ready`; bounded convergence with config version reported in response/admin views.
- Request-level **fallback** (rule strategy on scoring failure/deadline) and release-level **rollback** are distinct mechanisms with distinct log fields and audit entries.

### 2.4 Feedback provenance + controlled learning loop (SPEC §7.2, Addendum R12/R24)

- Provenance classes enforced end to end: `otto_offline` vs `demo`. Demo-derived datasets are quarantined by default and never silently mixed into real training data; demo-trained strategies are labelled and **ineligible** for the real-data release gate (the gate rejects cross-provenance promotion attempts, with the rejection logged).
- Feedback correctness: impression linkage, returned-top-K membership (T06 behaviour retained), event deduplication, client-event idempotency, configurable attribution window; late/duplicate handling per the ack semantics of Addendum §10 (F03/F05 as amended by B03/C05).
- Manually triggered learning-loop rehearsal: collect demo events → build demo dataset (versioned) → train demo candidate → evaluate → record a decision entry that shows the full trace from input events to decision, including the provenance ineligibility for the real gate.

### 2.5 Epochs + Operator Console (SPEC §11, Addendum R22/R30)

- Epoch registry checks: overlapping/contaminating epoch definitions are rejected (T14 behaviour); registering a newer epoch must not change older generations' replay results (replay determinism re-verified).
- Operator Console (authenticated, admin bearer): generation registry, release/evaluation history including the 2.2 decision, experiment states and health, event provenance views, outbox/ack status. W2-gate aggregates appear only here, never on the public Playground (F01/T13 retained).

## Tests (Stage 2 gate evidence)

- Addendum stage mapping for Stage 2: **T02** (gate blocked when ML does not beat rule beyond tolerance — exercise with a deliberately weakened candidate), **T03** (canary cohort stickiness + config consistency under concurrent publish), **T04** (shadow/canary results never alter served responses), **T07** (demo-trained artifact rejected by the real-data gate), **T08** (unattributed feedback excluded from training datasets), **T10** (kill switch → stable-only + audited), **T11** (cohort stickiness across config updates), **T12** (outbox replay yields exactly one effective delivery), **T14** (epoch overlap rejected).
- All Stage 0 + Stage 1 tests still pass.
- **Test-evidence rule (owner requirement):** the final acceptance run must execute the database-backed tests with the test DSN configured (compose Postgres or a test container), and the result summary must state passed / failed / skipped counts explicitly. A summary in which DB tests were skipped counts as incomplete.

## Acceptance (Stage 2 exit gate, SPEC §12)

A candidate generation is trained reproducibly, gate-evaluated on W2-gate with a recorded decision, shadow-compared, canaried with sticky cohorts, and rolled back or killed in a drill — with complete audit history and no change to sealed W3. The learning-loop rehearsal (2.4) produces its traceable decision entry. Model cards for `lgbm-v1` and any new candidate carry the Stage 0 sampling-limitation note and segment metrics.

## Hard constraints

- W3 stays sealed. W2-gate: one promotion comparison per candidate, no iterative tuning against it.
- No Kafka/Kubernetes/MLflow/LLM. No new retrieval source. Demo traffic is synthetic validation — never claim online/CTR lift.
- Never fabricate metrics; every number comes from a recorded run.
