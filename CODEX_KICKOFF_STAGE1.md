# RankFlow — Codex Kickoff: Stage 1 (Product Alpha)

**Repository:** `C:\PROJECTS\rankflow` (Stage 0 complete and verified; real OTTO run recorded in `docs/data_validation_report_real.md`)
**Governing documents:** `SPEC.md` (v3.0, product scope FROZEN), `ADDENDUM.md` (v3.0.4, implementation baseline). The Addendum governs technical contracts. Do not change product scope, stage definitions, or non-goals; record conflicts in `docs/open_questions.md` instead of improvising.
**Also incorporated:** the owner's Stage 0/Stage 1 engineering recommendations (2026-11-20): Stage 0 conditional pass with a focused data-quality review; three-source retrieval baseline before model tuning; retrieval evaluation and ablation on W2-dev before extensive LightGBM work.

**Language:** All code, comments, docs, and commit messages in English.

## Prerequisite — done, do not redo

Stage 0 is signed off. `docs/stage0_data_quality_report.md` records the disposition *proceed with a registered follow-up investigation* and pins the single-source baseline (`candidate_recall@100`: W1 11.20%, W2-dev 10.21%, W2-gate 10.21%, W3 9.10%; snapshot and configuration recorded there). All Stage 1 retrieval comparisons use that pinned definition and the W2-dev population. The registered follow-up investigation is folded into package 1.3 below.

## Stage 1 packages (in this order; commit each separately)

### 1.1 Three-source candidate retrieval (SPEC §4.3, Addendum R28)

- Sources, each independently switchable and unit-testable:
  - **Recent items:** items from the session prefix itself, ordered by recency with the deterministic tie-breaks of SPEC §4.3 (repeat events and event type are configuration, per Experiment A below).
  - **Co-visitation:** the Stage 0 exact table (epoch-pinned snapshot), per-item top-N as configured.
  - **Popularity:** most frequent items in the epoch's W0 statistics window only (point-in-time; never computed over later data).
- Union with deterministic deduplication and ordering; every candidate carries **source flags and per-source ranks**. `candidate_cap` is configuration (initial 100). Never inject the positive/label item into candidates.

### 1.2 Offline retrieval evaluator (Addendum R28 metric names are binding)

- Population: **W2-dev labeled queries only**, epoch-pinned snapshot, label policy `nextclick-v1`. No-label queries are counted and excluded from recall denominators; retrieval misses stay in every denominator (end-to-end semantics).
- Metrics: `candidate_recall@C` for C ∈ {50, 100, 200, 300}; pre-rank hit rate@20/50; per-source contribution and overlap; candidate-count distribution; cold-start query rate (R9a cases); unknown-item rate; wall-clock latency and peak memory per variant.
- The evaluator is a CLI producing a versioned JSON + Markdown report; the protocol (population, snapshot, caps, definitions) is recorded in the report header.

### 1.3 Retrieval ablation and budget study (baseline study; the formal R17 Pareto is Stage 2)

- Variants: each source alone, the three pairs, all three — reporting `candidate_recall@100`, rule-strategy HitRate@20 (using 1.5's rule strategy; a placeholder deterministic ordering is acceptable until 1.5 lands, but the final table must use `rule-v1`), latency, memory.
- Experiment A (recent-item variants: plain recency vs repeat-aware vs event-type-weighted) and Experiment C (caps 50/100/200/300) as configuration studies on the same protocol.
- Select the production configuration (source quotas + cap) from the measurements and record the rationale in the report. No universal recall threshold is pre-claimed.
- **Registered follow-up investigation (from the Step 0 sign-off):** on the fixed W2-dev query population, report session/query counts, label yield, and pinned `candidate_recall@100` sliced by session characteristics (length ≤20 / 21–100 / >100 events, duration bands, repeat-item share) to quantify which behaviours the boundary-exclusion rule underrepresents. Same governed windows and label rules; W2-dev only.

### 1.4 Shared feature builder (SPEC §4.4, Addendum R21/R16)

- One feature-builder code path used by training, offline evaluation, and serving (train/serve parity test required).
- Features per SPEC §4.4 plus source flags and per-source ranks from 1.1; explicit **unseen vs missing masks**; point-in-time only (prefix + epoch-pinned statistics); feature schema versioned, with the feature-code hash recorded (lineage fields per Addendum R16).

### 1.5 Strategies (SPEC §8, Addendum R7/R26)

- `rule-v1`: the deterministic rule strategy, registered as a versioned RankingStrategy.
- Initial LightGBM LambdaRank strategy trained on W1 queries (R6: all-negative groups excluded from fitting, retained in evaluation), configuration frozen and recorded.
- Compare both on the identical W2-dev query/candidate population: HitRate@20, MRR@20, NDCG@20 (secondary), with the R1 rule recorded in the report — **whichever strategy wins is reported honestly; a blocked ML promotion is a valid, reportable outcome.** Promotion machinery itself is Stage 2; Stage 1 records the measurement and the decision.

### 1.6 Serving: FastAPI + Playground (SPEC §6, §6.4; Addendum R23/R24 initial form)

- `POST /v1/recommend` implementing the §6.1 contract, including `serving_generation`, `retrieval_snapshot_id`, and `logging_status` in every response.
- Serving generations in their Stage 1 (single-instance) form: an immutable bundle (strategy artifact/config + feature schema + feature code hash + retrieval snapshot + compatibility manifest + checksums) registered and loaded as one unit.
- **Ranking Playground** per §6.4 and `docs/product_contract.md`: load a W2-dev or W1 session prefix (public data boundary per Addendum R30/F01 — **no W2-gate, no W3, no labels on the public surface**), show ranked results with provenance, side-by-side strategy comparison (labeled ranker-only mode, Addendum R25), and demo feedback submission linked to the impression.
- Cold-start behaviour per R9a (empty prefix, single event, all-unknown items) implemented and tested.

### 1.7 Reliability foundation (SPEC §8.1/§10; Addendum R14/R24)

- Request-scoped fallback: on ML scoring failure or logical-deadline expiry, serve `rule-v1` and log assigned ≠ served with the reason.
- Decision capture: impression + decision + outbox event in **one transaction** (Addendum §10.0); a basic outbox consumer with idempotent delivery; on write failure serve with `logging_status: degraded` and no usable impression ID.
- Feedback endpoint with Addendum R24 semantics: attribution only against a persisted decision, aid must be within the returned top-K (else reject with `not_in_returned_top_k`), `source=demo` provenance on Playground feedback, idempotent client acknowledgement endpoint (ack lifecycle basics, T15).
- Docker Compose brings up API + PostgreSQL with one command.

## Tests (Stage 1 gate evidence; all must pass)

- Addendum stage mapping for Stage 1: **T05** (disconnect after commit → durable decision, no confirmed impression), **T06** (feedback outside returned top-K rejected), **T13** public-boundary part (W2-gate/W3 not readable via any public API), **T15** ack lifecycle basics (duplicate/delayed acks idempotent, send states recorded).
- Retrieval determinism (same request → same candidates), feature train/serve parity, API contract tests, R6 golden fixture, cold-start cases.
- All Stage 0 tests still pass.

## Acceptance (Stage 1 exit gate, SPEC §12)

A reviewer can complete the §6.4 loop — session → ranked results with provenance → attributed demo interaction → the event visible — and reproduce the same request via the API with identical output under the same generation. The Step 0 data-quality report and the 1.3 ablation report are committed with honest numbers.

## Hard constraints

- W2-gate is used only through the governed evaluation path; W3 stays sealed. No tuning on W2-gate or W3.
- No Kafka/Kubernetes/MLflow/LLM. No fourth retrieval source without the ablation evidence required by Addendum R17.
- Never fabricate metrics; every number in every report must come from an actual run recorded in that report.
