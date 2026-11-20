# Project 5 — RankFlow: Production-Ready E-commerce Ranking Service

**Document type:** Product Specification (implementation-ready)  
**Version:** 3.0 — **FROZEN (product scope)** on 2026-11-19 by owner decision, after incorporation of R11–R21  
**Date:** 2026-11-19  
**Scope:** Four completion stages — **Product Alpha → ML Platform Beta → Operated Release → Product Complete** (§12, §15), preceded by a foundations phase (data semantics and product contract)  
**Target effort:** No fixed day limit (owner decision, 2026-11-19). Development proceeds stage by stage against acceptance gates, targeting **Product Complete** (§15). Stage durations are planning references only, never a reason to cut acceptance criteria or core design.  

> **Freeze rule:** v3.0 freezes the *product scope*: product identity, the four stages and their gates, the ML lifecycle, and the non-goals. Changing any of these requires the owner's explicit unfreeze plus a new review round, as with the previous frozen specs in this portfolio. Implementation-level configuration — exact sampled-subset size, hyperparameters, gate tolerances chosen on W2 under §9, infrastructure instance sizes — is **not** scope; it is recorded in versioned manifests/configs as work proceeds.
**Primary language:** Python  

**Revision history**

- v0.1 (2026-11-19): Initial proposed spec.
- v2.0 (2026-11-19): Incorporates the four pre-review revisions R1–R4 agreed before external review. No scope expansion beyond these revisions.
  - **R1 — ML may not beat the baseline (pre-registered outcome handling):** Primary metrics reordered to HitRate@20 / MRR@20, with NDCG@20 as a secondary diagnostic (single-positive labels make NDCG narrow). The release gate's failure path is specified in advance: if an ML version does not clear the gate, promotion is blocked, stable keeps serving the rule baseline, and that blocked promotion is itself the documented evidence that the gate works. Project completion does **not** require an ML version to win; it requires the gate to evaluate, record, and act correctly either way (see §4.2, §9.2–§9.3, §15).
  - **R2 — Co-visitation table capacity bound:** The item–item co-visitation table is pruned to a configurable top-N neighbours per item with a minimum co-occurrence threshold; its row count, on-disk size, and pruning configuration are recorded in the data manifest and bounded by an acceptance test (see §3.2, §4.3, §12 Stage 0/1).
  - **R3 — Search-ranking translation note (interview bridge):** final evidence package adds a one-page mapping between this session-based recommendation service and query-based search ranking (e.g. marketplace listing search), stating explicitly what transfers and what is **not** claimed — RankFlow has no query text, no filters, and no human relevance judgements, and is not a search system (see §2.4, §12 Evidence package).
  - **R4 — Hardening prioritisation and timebox protection:** Hardening work is tiered P0 / P1 / P2. On overrun, cut P2 first, then P1; never cut MVP-A or MVP-B to save Hardening. The dashboard stays a single minimal read-only page, and drift monitoring in Hardening is limited to 2–3 named features (see §12 Hardening). *(Superseded in part by R10 in v2.1: the tiers remain as build order, but time pressure is no longer a reason to cut them.)*
- v2.1 (2026-11-19): Incorporates the external technical review of v2.0 (Conditional GO) and one owner decision. Review findings were each verified against v2.0 before adoption; none were rejected.
  - **R5 (P0) — Point-in-time statistics:** Fixed chronological window scheme — statistics/history window, then training-query, validation, and frozen-test windows in that order — with the invariant `max(statistics_event_ts) < min(query_cutoff_ts)` for the single shared statistics snapshot, explicit session-boundary and timestamp-tie rules, and a future-event mutation test (see §3.2, §9.1).
  - **R6 (P0) — All-negative training queries:** LambdaRank training excludes groups whose positive was not retrieved (counted and reported); end-to-end evaluation retains them as misses; conditional diagnostics stay explicitly labeled. Golden fixture required (see §4.2, §4.4, §9.2).
  - **R7 (P0) — Ranking strategies, not just models:** The rule baseline becomes a versioned, registered ranking strategy (`rule-v1`) alongside LightGBM strategies under one abstraction. Stable/shadow/canary point at strategies; fallback (request-scoped) and rollback (control-plane) are defined as different mechanisms; decision logs record both assigned and actually-served strategy (see §6–§8).
  - **R8 (P0) — Two completion levels:** §15 now defines **MVP Complete** and **Portfolio Complete** with separate checklists, resolving the v2.0 conflict between cuttable Hardening items and mandatory completion evidence.
  - **R9 (P1) — Operational contracts:** Cold-start behaviour, candidate/Recall@K definitions, experiment-scoped sticky hashing, decision-log durability metrics, and a staged latency budget with a distinct model-scoring deadline (see §4.3, §6, §8.2, §9.3, §10).
  - **R10 (owner decision) — No 7-day limit:** The 5–7 day timebox is removed. The project target is **Portfolio Complete**; phases run in the recommended order (§12) and finish on acceptance criteria, not on the calendar. R4's tiers survive only as sequencing/priority order. Scope discipline (§2.2, §5.2) is unchanged — "ideal product" means completing this spec well, not expanding it with new subsystems.
- v3.0 (2026-11-19): Incorporates the product-oriented review of v2.1 (R11–R21, Conditional GO) and the owner's four-stage completion model, then **freezes product scope**. Each finding was verified against v2.1 before adoption; none were rejected. The investment goes to the complete ML lifecycle, a real product interaction surface, and reliable release/operations — explicitly **not** to Kafka, Kubernetes, or additional model algorithms (§2.2).
  - **R11 (P0) — Product identity frozen:** RankFlow is a ranking product with two surfaces — an interactive **Ranking Playground** (consumer experience) and an **Operator Console** (operations) — over the ranking API. Not a full storefront (§2, §5, §6.4).
  - **R12 (P0) — Closed learning loop:** A versioned, manually triggered feedback→attribution→dataset→train→evaluate→promotion-decision pipeline with full run lineage and provenance quarantine (§7, §9.4, §12).
  - **R13 (P0) — Serving generations:** Releases are immutable, content-addressed **serving generations** (strategy + feature schema/code + retrieval snapshot + compatibility manifest), preloaded and validated on every instance before an atomic pointer promotion; experiments follow an audited state machine with a kill switch (§8).
  - **R14 (P0) — Event durability:** Impression/decision capture moves to a transactional **outbox** with at-least-once idempotent consumption, retry and dead-letter handling; the persistence guarantee and its degraded mode are explicit (§7, §10).
  - **R15 (P0) — Evaluation governance:** W2 is the repeatable development/gate set; **W3 is a sealed acceptance test** — access-logged, opened only for a finalized release candidate's final report, never for routine gating (§3, §9).
  - **R16 (P1) — Full lineage:** Every release binds `dataset_snapshot → retrieval_snapshot → feature_schema + feature_code_hash → strategy_artifact → evaluation_protocol → serving_generation`; recorded requests replay exactly under their pinned generation, using event-time (never wall-clock) for historical sessions (§5, §7, §8).
  - **R17 (P1) — Retrieval science:** Candidate-source ablation, configurable retrieval depth distinct from `top_k`, and a measured recall-vs-latency Pareto before any depth or source change (§4, §9).
  - **R18 (P1) — Operability:** Operator workflows, quality/data-freshness metrics, SLOs, and alerts each bound to a defined operator action (§10).
  - **R19 (P1) — Security and recovery:** Roles, API/client auth, pseudonymisation and retention contracts, CI scanning, one reference deployment beyond Compose, migrations, and a tested backup/restore (§11, §12).
  - **R20 (P1) — Four-stage completion:** §12/§15 replace MVP/Portfolio levels with **Product Alpha → ML Platform Beta → Operated Release → Product Complete**, each with its own exit gate; Product Complete uses the product-quality reproducibility matrix.
  - **R21 (correctness) — Identity and build algorithm:** Query identity is `(session_id, cutoff_event_index)`; the co-visitation build uses an exact on-disk aggregation algorithm (no unproven bounded-streaming claim); unseen-vs-missing feature masks are explicit (§3, §4).

---

## 1. Executive Summary

**RankFlow** is a production-like, session-based e-commerce recommendation and ranking service built from real user interaction data. It demonstrates how to deploy and operate a classical ML ranking model inside a reliable backend product: candidate generation, shared feature engineering, low-latency inference, deterministic fallback, model versioning, shadow/canary releases, decision logging, reproducible offline evaluation, feedback capture, and feature/score drift monitoring.

**Core thesis:** The project is **not** a Kaggle leaderboard solution, not an LLM wrapper, and not a full recommender platform. It is a small, demonstrable **ML-in-product vertical slice** with engineering artifacts that support senior backend / ML platform interviews.

**Dataset:** OTTO Recommender Systems Dataset (real click, cart, and order session events). Product metadata, catalog photos, demographics, query text, and randomized impression logs are **not assumed to exist** in this dataset. The API is a **session-based recommendation API**, not a keyword-search API.

**Primary task:** Given a prefix of observed events in a shopping session, return the top-K product IDs (`aid`) most likely to be the **next clicked item**. Cart/order prediction is a later extension (§12, optional); their events may be used as *historical input features when they precede the prediction cutoff*, never as future information.

**Product identity (R11, frozen):** RankFlow is presented and built as a product with two surfaces over the ranking API — an interactive **Ranking Playground** where a reviewer can replay or build a session, inspect ranked results with their strategy/generation provenance, compare two strategies side by side, and submit attributed demo interactions; and an **Operator Console** for releases, experiments, evaluation, data freshness, alerts, and incident history. It is a *production-like ML ranking platform operating on a real historical interaction dataset, with a synthetic/local consumer environment* — that sentence, and nothing stronger, is the approved product claim.

## 2. Goals, Non-Goals, and Interview Evidence

### 2.1 Goals (G)

- **G1:** Serve a reproducible top-K ranking from an HTTP endpoint under an explicit latency budget.
- **G2:** Separate candidate retrieval from LightGBM reranking; quantify recall ceiling and ranking quality independently.
- **G3:** Fail safely to a deterministic, documented rule strategy on inference error/timeout/missing artifact or incompatible features.
- **G4:** Register immutable ranking strategies and release them as atomic serving generations through shadow and canary stages, with an idempotent, observed rollback.
- **G5:** Replay held-out real sessions chronologically; compare strategies under a governed evaluation protocol (W2 for development/gating, sealed W3 for final acceptance reporting only).
- **G6:** Capture decisions and feedback durably, attribute them under provenance rules, and run the versioned feedback→dataset→train→evaluate→decision pipeline end to end.
- **G7:** Provide a real product interaction surface (Ranking Playground) and an operator workflow (Operator Console) — not merely an API and a status page.
- **G8:** Detect operational and quality issues — latency, fallback, drift, data freshness, attribution loss — with every alert bound to a defined operator action.

### 2.2 Explicit non-goals (NG)

- Win the OTTO competition or build a state-of-the-art sequence recommender.
- Build a full e-commerce website, checkout, payment system, inventory service, or image-rich catalog. (The Ranking Playground is an interaction/evaluation surface, not a storefront.)
- Claim online CTR lift from offline data, or present the local Playground/feedback environment as a real user-facing production experiment.
- Build a distributed feature store, stream processor (Kafka etc.), Kubernetes platform, or full MLflow infrastructure.
- Train an LLM or use an LLM in the synchronous scoring path.
- Add model algorithms beyond the specified comparisons (LambdaRank primary; pointwise comparison in Beta) — depth goes to lifecycle, product, and operations, not algorithm count.
- Automated *scheduled* retraining is not required; the learning-loop pipeline is manually triggered with complete lineage (a schedule may be added later as an extension, §12).

### 2.3 The mandatory evidence artifacts

These artifacts define the **Product Complete** evidence set (§15); earlier stages cover specified subsets of them.

| Evidence | What the reviewer can inspect |
|---|---|
| Online inference and fallback | `/v1/recommend`, traced feature assembly, p95 load-test report, injected failure demo, Playground interaction |
| Strategies and safe release | Immutable strategy registry, serving generations, experiment state machine, multi-instance promotion and rollback tests |
| Reproducible offline evaluation | Governed W2/W3 protocol, exact cutoff/event-index rules, strategy comparison metrics with uncertainty, CI gate |
| Closed learning loop | A pipeline run ID linking raw events → validated/quarantined events → attribution → training dataset version → candidate strategy → evaluation report → release decision |
| Durable event capture | Outbox semantics, kill/restart recovery test, attribution and persistence metrics |
| Drift, quality, and freshness monitoring | Missing-rate/PSI/score histograms, snapshot-age and quality metrics, Operator Console, alert→action runbooks |

### 2.4 Interview translation note (R3)

RankFlow is a **session-based recommendation** service: its ranking context is a session event prefix, not a search query. Several target roles (e.g. marketplace listing search) are **query-based search ranking** roles. The two share an engineering core, and the final evidence package must include a one-page translation note (`docs/search_ranking_translation.md`) mapping them explicitly:

| RankFlow (this project) | Query-based search ranking (analogue) |
|---|---|
| Session event prefix as ranking context | Query text + user/filter context |
| Candidate generation (recent / co-visitation / popularity) | Retrieval stage over an index |
| LightGBM reranking of a bounded candidate set | Learning-to-rank reranking stage |
| Next observed click as the label | Click / engagement labels on results |
| Offline replay over held-out sessions | Offline evaluation over logged queries |
| Shadow / canary / rollback, latency budget, drift | Same release and operations discipline |

The note must also state what does **not** transfer and is **not claimed**: RankFlow has no query understanding, no text relevance features, no faceted filters, and no human relevance judgements, and it is not a search system. The claim is transfer of the ranking-service engineering (candidate generation, feature parity, offline/online evaluation discipline, safe release), not prior search-product experience.

## 3. Data Source, Licensing, and Integrity

**Official data:** https://github.com/otto-de/recsys-dataset  
**Competition and task definition:** https://www.kaggle.com/competitions/otto-recommender-system/data  
**License:** Dataset CC BY 4.0; retain attribution and document source/version. Verify current download terms before redistributing data.  

### 3.1 Assumed core input schema

```json
{"session": 1001, "events": [
  {"aid": 101, "ts": 1661111000000, "type": "clicks"},
  {"aid": 222, "ts": 1661111060000, "type": "carts"}
]}
```

The numeric values above are illustrative; do not treat them as sample rows from OTTO.

### 3.2 Data partitions and resource budget

- Provide a **deterministic sampled subset** for fast local development (e.g. a few hundred thousand sessions, configurable); do not hardcode an unverified download size.
- Use a **chronological train / validation / frozen test** split defined by session cutoff time, with no session spanning split boundaries. Freeze test membership and random seed in a versioned manifest.
- For a session with events `e1...en`, a training example observes only events through an earlier cutoff `t`, and labels the first **future click after `t`**. If no future click exists, skip that query for the primary metric and count/report its exclusion.
- Sample no more than a documented number of cutoffs per training session; record sampling policy and train/validation query counts.
- **No future-event leakage:** candidate generation, popularity counters, item co-occurrence statistics, and features used at cutoff `t` must be constructed from permitted historical data only. Static aggregates computed from training data may be used at validation/test time, but must not include those validation/test futures.
- **Co-visitation table capacity bound (R2):** The item–item co-visitation table must be pruned at build time: keep at most a configurable `top_n_per_item` neighbours per item (initial default: 100) and drop pairs below a configurable minimum co-occurrence count (initial default recorded in the training configuration before any model is trained). Total table rows are therefore bounded by `distinct_items × top_n_per_item`. The data manifest must record the pruning configuration, the actual row count, the on-disk size, and the peak memory observed while building/loading the table on the documented local machine. If the table exceeds the recorded local resource budget, reduce the sampled subset or `top_n_per_item` — do not silently let the table grow unbounded. The **build process itself** must also respect the bound (external-review caution on R2): the build uses the exact on-disk aggregation algorithm specified next — never a naive in-memory pair matrix, and never an approximate streaming top-N whose error is unmeasured.
- **Co-visitation build algorithm (R21 — exact, disk-based):** (1) Stream W0 sessions in bounded chunks and emit `(item_a, item_b)` co-occurrence increments into an embedded on-disk store (e.g. SQLite/DuckDB with a configured memory cache limit and disk spill). (2) After all chunks, aggregate exact counts per pair in the on-disk store (`GROUP BY` over the spilled table). (3) For each item, select its exact top-N neighbours from its fully aggregated counts (per-item ordering over that item's group only), applying the minimum-count threshold. Selection therefore happens **after** exact aggregation, so the output top-N is exact, while process memory stays bounded by the store's cache setting plus one item group. The manifest records the store, cache limit, spill size on disk, and build time. An approximate heavy-hitter algorithm may only replace this if its recall error against the exact build is measured and recorded — not by default.
- Use held-out sessions for testing; never fit features, thresholds, or model selection against the frozen test set.
- **Point-in-time window scheme (R5):** The sampled data is divided into four consecutive, non-overlapping chronological windows, recorded with exact boundaries in the versioned manifest:
  1. **W0 — Statistics/history window (earliest).** The single shared statistics snapshot — co-visitation table, popularity lists, and all aggregate features — is built **only** from W0 sessions.
  2. **W1 — Training-query window.** Training queries (prefix + next-click label) are generated only from sessions in W1.
  3. **W2 — Validation window.** Validation queries for model selection and gate-threshold setting, from W2 sessions only.
  4. **W3 — Frozen test window (latest).** Queried once, for the final independent report.
  For the shared snapshot, the invariant **`max(statistics_event_ts) < min(query_cutoff_ts)`** must hold for every query in W1–W3. Aggregate statistics are therefore never "train-only but later than the query": they are strictly earlier than every query they serve. (Per-session prefix features — counts, recency, last-event type within the observed prefix — are point-in-time by construction, since they use only events at or before that query's cutoff position.) Later snapshot versions (R16, §3.2) are built as new immutable snapshots under this same scheme; a true rolling per-query as-of snapshot design is outside frozen scope and would require the equivalent per-query as-of invariant to be validated instead.
- **Session boundaries and timestamp ties (R5):** A session is assigned wholly to one window by its **first event timestamp**; a session whose events cross a window boundary is excluded from query generation in all windows and counted in the manifest (its events also never enter the statistics snapshot unless the session is assigned to W0 and lies wholly inside W0). Within a session, event **list order is authoritative** when timestamps tie: a query prefix is defined by cutoff **position** in the event list, and its label is the first click after that position. Window membership, by contrast, is decided by timestamps as above. Both rules, and the exclusion counts they produce, are recorded in the manifest.
- **Window-exclusion accounting (R21):** The manifest also reports how many sessions and events were excluded by the boundary rule, split by session length (short vs long), so any skew the exclusion introduces is visible in the evaluation report rather than silent.
- **Query identity (R21):** Every event carries a persisted `event_index` (its position in its session's event list, assigned at ingestion). A query is identified by **`(session_id, cutoff_event_index)`** — never by `(session_id, cutoff_ts)` alone, which can collide when two cutoffs share a millisecond. Query IDs in all manifests, reports, and lineage records derive from this pair.
- **Snapshot refresh and replay clock (R16):** The W0 snapshot is the *initial* statistics snapshot. Later snapshots are new immutable versions built under the same point-in-time rules from later history windows, and a release binds exactly one `retrieval_snapshot_id` (§8). Features that depend on time (recency, age) are always computed against the **query's cutoff timestamp / the request's last prefix event timestamp** — the replay clock — never against wall-clock "now", which would corrupt historical-session scoring.
- **Future-event mutation test (R5):** The test suite must prove that appending or modifying events that occur after a query's cutoff — or anywhere in a later window — does not change that query's candidate set or feature vector. This test is part of the Stage 0/Stage 1 acceptance gates (§12), not a later-stage extra.
- Preserve source dataset provenance, subset hash/checksum, split manifests, feature schema version, and training configuration.

### 3.3 Critical limitations

OTTO contains interactions, **not a logged record of all products displayed to the user** and not randomized exposure propensity. Observed future actions can form next-event relevance labels, but unobserved candidates are **not verified negative impressions**. Therefore offline metrics estimate performance on a historical-proxy evaluation task, not unbiased counterfactual online uplift.

Runtime demo impressions/actions are **synthetic or locally generated** and must be labeled `source=demo`. They prove logging and data-pipeline correctness, **not real business conversion lift**. Never merge them into the real-data evaluation set without explicit provenance filters.

## 4. Product Contract and Ranking Semantics

### 4.1 User story

> As a session-based shopping recommendation consumer, I send a recent event history and request top-K product IDs. RankFlow generates candidates and returns an ordered list with a model version, trace identifier, and fallback state. As an operator, I can shadow a new model, ramp up canary traffic, compare replay metrics, and roll back without redeploying code.

### 4.2 Model target

- **Frozen task:** Next-click recommendation: predict `aid` for the **first subsequent click** after a session cutoff.
- **Candidate universe:** Items reachable by the documented retrieval method; default K=20, max request K=50.
- **Query unit:** `(session_id, cutoff_event_index)` (R21); candidate labels are binary for next-click membership, with exactly one relevant positive **if retrieved**, otherwise all candidate labels are 0 for that query.
- **Metrics (R1 — primary/secondary ordering):** **Primary** end-to-end metrics are `HitRate@20` and `MRR@20` on the **full held-out query set**, including queries for which the true next item was not retrieved. `NDCG@20` is a **secondary diagnostic**: with exactly one relevant positive per query it carries the same ordering information in a narrower, less interpretable form, and must not be presented as the headline result. Retrieval `Recall@20` / `Recall@50` and candidate coverage are reported alongside, separately from ranking quality. Where ranking software excludes all-negative queries, compute end-to-end metrics separately from raw held-out ground truth to avoid inflated results. Also report conditional ranker-only metrics on retrieved-positive queries, clearly labeled.
- **Secondary:** v1 vs v2 delta; p95 inference latency; fallback and error rates.

### 4.3 Candidate generation — keep it small

Generate and deduplicate a bounded union (target ≤100 candidates pre-rank) of:

1. Recent items seen in the current session (repeat-interest signal).
2. Top co-visitation items from a **train-only**, time-safe item-item table, pruned per §3.2 (R2): at most `top_n_per_item` neighbours per item, minimum co-occurrence threshold applied at build time.
3. Popular items from a **train-only** global popularity list (cold-start backstop).

Record candidate source flags and ranks; ensure deterministic tie-breaking by `aid`. If the target is missing from the candidate union, it remains an end-to-end miss and is **not** forcibly injected for evaluation. Candidate lookup must only ever read the pruned table; there is no unpruned fallback table at request time.

**Retrieval depth and ablation (R17):** Retrieval depth is a configuration distinct from the response `top_k`: the candidate cap starts at 100 and is studied, not assumed. The Beta stage (§12) must produce a candidate-source ablation report: per-source and leave-one-source-out Recall@20/50, source overlap, cold-start coverage, and end-to-end metrics, at several retrieval depths, with measured latency and memory for each — a **recall-vs-latency Pareto** summary from which the production depth and any per-source quotas are chosen and recorded. An additional retrieval source (e.g. event-type/recency-weighted co-visitation variants, or an embedding/ANN source) is added only if the ablation shows it adds recall the existing sources miss, at acceptable cost.

**Candidate and Recall@K definitions (R9b):** The pre-rank candidate set is capped at **100** items. For measurement, the retrieval stage also produces a deterministic **retrieval order**: candidates ordered by the rule strategy's score (which is defined for every candidate, ML or not). `Recall@20` / `Recall@50` mean: the fraction of held-out queries whose target appears within the first 20 / 50 positions of that retrieval order. These are **retrieval coverage** numbers. End-to-end `HitRate@20` is a different number: the target's presence in the top 20 **after the assigned strategy reranks the full candidate set (≤100)**. Reports must never conflate the two, and every metric table labels which stage it describes.

**Cold-start behaviour (R9a):** Three distinct cases, all deterministic:
- **Empty session** (valid request, zero events): return the top-K of the W0 popularity list, served by the assigned strategy's popularity path (for ML strategies, this is the rule/popularity path and is logged as such, not as a model inference).
- **Unseen item IDs in the prefix** (aids absent from the statistics snapshot): they are **ignored as signals** — not rejected as malformed — and counted in the decision log as `unknown_aid_count`. If every prefix item is unseen, the request behaves as an empty session.
- **No co-visitation neighbours** for the known prefix items: the popularity source fills the candidate set up to its available depth; a smaller candidate set is valid and is logged with its actual count.

**Unseen vs missing feature semantics (R21):** The shared feature builder emits explicit indicator/mask features so the rule and ML paths interpret absence identically: e.g. `candidate_is_unknown_item`, `has_covisitation` (0/1) with the co-visitation score set to a documented neutral value only when the mask is 0, `popularity_missing` mask, and per-source presence flags. "Item unseen in the snapshot", "item known but no neighbours", and "feature not applicable" are three distinct, named states in the feature schema — never a single ambiguous null/zero.

### 4.4 Ranking approaches

- **Rule baseline:** Weighted recency + repeated events + co-visitation + popularity; stable, deterministic scoring. This baseline is always available without the ML artifact.
- **ML v1:** LightGBM (`LGBMRanker`, `lambdarank`) on the same candidate universe. Group by query; no sessions split across train/validation. Initial labels 0/1. Feature examples: item frequency in prefix, last-seen age, last-event type, co-visitation score, popularity rank, session length, candidate-source flags, prior click/cart/order counts.
- **All-negative training groups (R6):** A query whose positive target was **not retrieved** has all-zero candidate labels and carries no within-group relevance contrast for `lambdarank`. Such groups are **excluded from LambdaRank fitting** — never "fixed" by injecting the target — and the exclusion is counted and reported (`training_query_exclusion_rate`, alongside `single_positive_rate` and the eligible-group count). The same queries are **retained** in end-to-end validation/test, where they count as retrieval misses with zero ranking credit; only the explicitly labeled conditional diagnostics exclude them. A golden fixture with one positive-containing query and one all-negative query must verify both behaviours (excluded from fitting, included in end-to-end evaluation), and LightGBM group boundaries must be asserted in tests so groups are never split or merged.
- **ML v2:** A single documented enhancement (e.g. normalized recency + source interactions). v2 must be trained from a frozen configuration and compared with the same replay harness; no requirement to win on every metric.
- **Feature parity:** Offline training and request-time scoring call the **same feature builder and versioned schema**; golden-case parity tests.
- **Hard deadline:** ML scoring is synchronous but guarded by a per-request deadline. Use bounded input sizes and demonstrate failover with a deterministic injected timeout/error. Document the difference between a logical timeout in-process and a hard timeout requiring process isolation; avoid claiming a thread can forcibly stop an unsafe native call. Execution staging for this contract is defined in §8.5 (in-process at Alpha, process-pool isolation at Operated Release).

## 5. System Architecture

```text
                        OFFLINE / CONTROL PLANE
OTTO JSONL -> validate -> W0-W3 windows -> retrieval snapshot -> feature rows
                                            |               |
                                        rule-v1         LightGBM strategies
                                            |               |
                            W2 replay + evaluation protocol (governed, §9)
                                            |
                        immutable release bundle = serving generation (§8)
                                            |
                     experiment state machine: shadow -> canary -> stable
                                            |
                                      audited promotions

                         ONLINE / DATA PLANE
Ranking Playground / API consumer -> POST /v1/recommend
        -> validate -> pinned serving generation -> candidate retrieval
        -> shared point-in-time features -> assigned strategy scoring
        -> timeout / error -> rule fallback (served strategy recorded)
        -> ranked response (generation + snapshot IDs) 
        -> impression + decision written with outbox event (one transaction)
        -> outbox consumer (retry / DLQ) -> feedback store + monitoring
        -> attribution (provenance-checked) -> versioned training datasets
        -> manually triggered retrain pipeline -> next candidate strategy

                       OPERATOR / OBSERVABILITY PLANE
Operator Console: experiments | generations | evaluation | freshness |
                  drift & quality | alerts -> actions | audit trail
```

Logical modules first: split into separate deployable services only if scaling, fault isolation, or ownership demands it. PostgreSQL/Redis plus the outbox mechanism implement the release and event guarantees without Kafka or a feature-store product.

### 5.1 Technology choices

| Component | Technology | Why |
|---|---|---|
| API / server | Python 3.12+, FastAPI, Pydantic | Simple typed HTTP interface |
| ML | LightGBM, NumPy, pandas/polars | Classic, fast, inspectable ML |
| Primary DB | PostgreSQL | Registry, generations, logs, outbox, feedback, aggregate tables |
| Cache | Redis | Optional hot session features / retrieval-table cache; service must tolerate cache outage |
| Artifacts | Local immutable, content-addressed versioned directory | Release bundles (§8) without dedicated registry infrastructure |
| Product surfaces | Server-rendered lightweight web UI (same FastAPI app) | Playground + Operator Console without a separate frontend application |
| Inference isolation | Bounded process pool for ML inference (Operated Release stage) | A hung native call can be terminated; a thread timeout cannot (§8, §10) |
| Test | pytest, httpx, locust or k6 | Functional, replay, fault-injection and load tests |
| Packaging | Docker Compose (baseline) + one reference deployment (§11) | One command locally; one reproducible hosted environment |
| CI | GitHub Actions | Format/test/feature parity/evaluation gate/dependency & image scanning |

### 5.2 Scope discipline

Do **not** include Kafka, Kubernetes, Airflow, Spark, SageMaker, a full feature store, or a multi-service frontend at any stage. They increase infrastructure complexity without strengthening the core ML-productization proof. Depth is added to the ML lifecycle, the product surfaces, and release/operations reliability instead (R11–R19).

## 6. API Contracts

### 6.1 `POST /v1/recommend`

```json
{
  "request_id": "req-123",
  "session_id": "s-1001",
  "events": [
    {"aid": 101, "ts": 1661111000000, "type": "clicks"},
    {"aid": 222, "ts": 1661111060000, "type": "carts"}
  ],
  "top_k": 20
}
```

Response:

```json
{
  "request_id": "req-123",
  "impression_id": "imp-unique",
  "assigned_strategy": "lgbm-v1",
  "served_strategy": "lgbm-v1",
  "assignment": "stable",
  "serving_generation": "gen-9f3c…",
  "retrieval_snapshot_id": "retrieval-w0-v1",
  "logging_status": "persisted",
  "feature_version": "session-features-v1",
  "fallback_used": false,
  "items": [{"aid": 222, "rank": 1, "score": 0.739}],
  "latency_ms": 28.1
}
```

Response is illustrative, not an observed latency. `score` is a relative ranking score, **not** a calibrated probability. Request timestamps must be monotonic after normalization; apply maximum event count, K bound, input size, and validation rules. Do not accept client-provided model assignment.

**Strategy identity (R7):** `assigned_strategy` is the strategy the traffic configuration selected for this request; `served_strategy` is the strategy that actually produced the returned ranking. They differ exactly when fallback occurred, in which case `served_strategy` is the healthy rule strategy and `fallback_used` is true with a logged reason. Both values are persisted in the decision log (§7).

**Provenance fields (R13/R14/R16):** `serving_generation` and `retrieval_snapshot_id` identify the exact pinned release that produced the response, so any recorded request can be replayed under its own generation (§8). `logging_status` is `persisted` when the impression/decision record and its outbox event were durably written in the request transaction, or `degraded` when they were not — in which case the response is still served, but the impression is **not eligible for attributed feedback** and the loss is counted (§10). Detailed internal traces stay server-side, referenced by `request_id`, not in the public response.

### 6.2 Supporting endpoints

| Method / route | Behavior |
|---|---|
| `GET /health/live` | Process liveness, no DB dependency |
| `GET /health/ready` | Critical dependencies / chosen baseline availability |
| `GET /v1/strategies` | Registered ranking strategies (rule and LightGBM), versions, validation state |
| `GET /v1/traffic` | Stable/shadow/canary strategy config, read-only |
| `POST /v1/admin/traffic` | Change traffic config (local dev/admin-only; audit every action) |
| `POST /v1/admin/rollback` | Atomically restore the previous known-good traffic configuration (stable strategy, canary off); audit action |
| `POST /v1/feedback` | Store locally generated impression-linked event, idempotently |
| `GET /v1/metrics/summary` | Windowed latency/fallback/model/feedback/drift summaries |
| `GET /console` | Operator Console (§6.4): generations, experiments, evaluation, freshness, alerts, audit |
| `GET /playground` | Ranking Playground (§6.4): session replay/build, ranked results, strategy comparison, demo feedback |

### 6.3 `POST /v1/feedback`

```json
{
  "event_id": "evt-abc",
  "impression_id": "imp-unique",
  "aid": 222,
  "action": "click",
  "occurred_at": "2026-11-19T20:00:00Z",
  "source": "demo"
}
```

- Supported demo events: `click`, `cart`, `order`; `impression` is created server-side when a ranked response is served.
- Enforce idempotency by `event_id`; require valid `impression_id` and item membership for attributable feedback.
- Store event time and ingest time separately. Permit late events within a documented attribution window.
- Store anonymous session IDs; never collect names, emails, IPs, or payment information for this project.
- Return clear 4xx on malformed input; keep feedback logging failures from blocking the recommendation response when safe to do so, with a counted operational error.

### 6.4 Product surfaces (R11)

**Ranking Playground (consumer surface).** A reviewer can, without database access:
- Load a held-out OTTO session prefix (labeled with its window and cutoff) or build a session from item IDs, and request a ranking.
- See the ranked list with, per item: `aid`, rank, score, candidate sources, and the serving provenance (assigned/served strategy, serving generation, snapshot ID, fallback state). Item display labels are the `aid` plus a clearly marked **synthetic display label** (e.g. "Item 12345") — OTTO has no catalog metadata, and no attribute may be presented as if it came from OTTO.
- Compare two strategies side by side on the same session (same candidate set), with rank-agreement and per-item movement shown — raw scores are not compared across strategies (§10.3).
- Submit demo click/cart/order actions against a served impression and immediately see the resulting feedback event, its attribution status, and its `source=demo` label.

**Operator Console (operations surface).** Shows: strategy registry and lineage, serving generations and promotion history, experiment state and cohort metrics, evaluation reports (W2) and final reports (W3, when opened), retrieval snapshot age/freshness, quality and drift metrics, alert list with the action each alert maps to (§10.4), event-persistence and attribution metrics, and incident history. Mutations (promote, ramp, rollback, kill switch) go through the authenticated admin APIs/CLI with role checks and audit (§11); the console itself links to those actions but holds no privileged credentials.

**Acceptance (R11):** The full loop — send session → see ranked results with provenance → submit attributed interaction → view the event and its attribution — is completable in the Playground, and the serving strategy/generation for that request is inspectable in the Console, with no direct database access.

## 7. Storage Model (minimal)

| Entity | Essential columns |
|---|---|
| `ranking_strategies` | `strategy_id PK` (e.g. `rule-v1`, `lgbm-v1`), `strategy_type` (`rule` \| `lightgbm`), `version`, `artifact_uri` (LightGBM) or `config_uri` (rule), `sha256` of artifact or immutable config, `feature_schema_version`, `training_manifest_hash`, `validation_metrics_json`, `status`, `created_at` |
| `traffic_configs` | `config_id`, `experiment_id`, `stable_strategy`, `canary_strategy`, `canary_percent`, `shadow_strategy`, `updated_at` |
| `strategy_assignment_audit` | `request_id`, `cohort_key_hash`, `assigned_strategy`, `config_id`, `created_at` |
| `decision_logs` | `request_id`, `impression_id`, `session_id`, `assigned_strategy`, `served_strategy`, `feature_version`, `fallback_reason`, `latency_ms`, `candidate_count`, `ordered_aids`, `created_at` |
| `impressions` | `impression_id`, `request_id`, `served_aids`, `served_strategy`, `source`, `served_at` |
| `feedback_events` | `event_id PK`, `impression_id`, `aid`, `action`, `source`, `occurred_at`, `ingested_at` |
| `drift_snapshots` | `window_start`, `version`, `feature_name`, `psi`, `missing_rate`, `observed_count`, `alert_status` |
| `serving_generations` | `generation_id PK` (content hash), `strategy_id`, `retrieval_snapshot_id`, `feature_schema_version`, `feature_code_hash`, `evaluation_protocol_version`, `bundle_manifest_uri`, `bundle_sha256`, `status`, `created_at` |
| `experiment_states` | `experiment_id PK`, `state` (draft/offline-approved/shadow/canary/stable/aborted), `generation_id`, `canary_percent`, `guardrail_config`, `updated_by`, `updated_at` |
| `outbox_events` | `event_id PK`, `aggregate_id` (impression/request), `event_type`, `payload_json`, `status` (pending/delivered/dead-letter), `attempts`, `created_at`, `delivered_at` |
| `training_dataset_versions` | `dataset_version PK`, `source_filter`, `window_manifest_hash`, `query_count`, `exclusion_counts_json`, `created_by_run_id`, `created_at` |
| `pipeline_runs` | `run_id PK`, `run_type` (retrain/evaluation/attribution), `input_versions_json`, `output_versions_json`, `status`, `quarantine_counts_json`, `started_at`, `finished_at` |
| `holdout_access_log` | `id PK`, `dataset` (W3), `accessed_by`, `purpose`, `release_candidate`, `accessed_at` |
| `admin_audit_log` | `id PK`, `actor`, `role`, `action`, `target`, `before_json`, `after_json`, `created_at` (append-only) |

The service may serialize candidate scores/features to a compact JSONB log where useful. Cap or sample high-volume logs; provide local retention policy. Do not store raw oversized feature payloads by default.

## 8. Strategy Registry, Release Controls, and Rollback

### 8.1 Ranking strategies (R7)

All rankers — including the rule baseline — are **ranking strategies** under one registry abstraction:

```text
RankingStrategy
  strategy_id            e.g. rule-v1, lgbm-v1, lgbm-v2
  strategy_type          rule | lightgbm
  version
  artifact_hash / immutable configuration reference
  feature_schema_version
  status                 candidate | evaluated | approved | active | retired | rejected
```

The rule baseline is a first-class strategy (`rule-v1`): its "artifact" is its immutable, hashed scoring configuration, registered and versioned exactly like a LightGBM artifact. Changing any rule weight creates a new strategy version; rule weights are never edited in place on a registered version.

Version lifecycle: `candidate -> evaluated -> approved -> active -> retired` (with `rejected` on failed gates). A strategy is immutable after registration; store its SHA-256 (artifact file or config), feature schema identifier, training manifest (LightGBM) or config provenance (rule), dependencies, and evaluation report. Startup and promotion verify integrity and compatibility.

**Fallback ≠ rollback (R7):**
- **Fallback** is *request-scoped and automatic*: on inference error, deadline, missing/corrupt artifact, or feature-schema mismatch for the assigned strategy, that single request is served by the designated healthy rule strategy; the decision log records assigned vs served strategy and the reason. Fallback changes no configuration.
- **Rollback** is a *control-plane operator action*: it atomically restores a previously known-good traffic configuration (stable strategy, canary disabled). It affects subsequent requests only; historical decision logs keep their original strategy attribution.

### 8.2 Deterministic routing (R9c)

`cohort = int(SHA256(experiment_id + "|" + experiment_salt + "|" + anonymous_session_id)) % 10000`, computed over the UTF-8 encoding of that exact string, with `|` as the canonical separator. A session is in the canary cohort when `cohort < canary_percent × 100`. Never use Python's process-randomized built-in `hash()`.

- The `experiment_id` scopes assignment: a new experiment (new model comparison) gets a new `experiment_id`, so cohorts of different experiments are not accidentally coupled. Within one experiment, raising `canary_percent` grows the cohort monotonically (existing members stay members).
- **Stable:** All served recommendations come from the designated stable **strategy** — which may legitimately be `rule-v1` when no ML strategy has cleared the gate (R1).
- **Shadow:** Score the same **frozen candidate set / feature vector** asynchronously or on a bounded side path with a shadow strategy, log differences, **never change served ranking**. Track shadow latency separately; failures must not impact user response.
- **Canary:** A fixed percentage of session IDs are served by the canary strategy. Use the same session assignment across requests within the experiment; expose assignment in operator logs.
- **Rollback:** Per §8.1 — restore the previous known-good configuration atomically and validate that subsequent requests use it.

Promotions and rollbacks require authenticated local admin access (e.g. configured development token), audit record, and reproducible config; never expose mutation endpoints publicly without hardening.

### 8.3 Serving generations (R13/R16)

A **serving generation** is the immutable, content-addressed release bundle that a request is served from. It binds the full lineage chain:

```text
dataset_snapshot → retrieval_snapshot → feature_schema + feature_code_hash
                 → strategy_artifact → evaluation_protocol → serving_generation
```

- **Bundle:** strategy artifact/config, feature schema and a hash of the feature-builder code, the retrieval snapshot, a compatibility manifest (which strategy × schema × snapshot combinations are valid), and checksums for every component. `generation_id` is derived from the bundle's content hash.
- **Promotion protocol:** (1) register the bundle; (2) **preload and validate it on every serving instance** (artifact loads, schema/snapshot compatibility verified, a smoke ranking produced); (3) only when all instances acknowledge readiness, atomically move the generation pointer; (4) instances pick up the new pointer by version check (bounded staleness, recorded) and report the generation they serve. A failed preload on any instance **aborts the promotion** — no instance serves a generation another instance cannot load.
- **Last-known-good:** Every instance keeps its last-known-good generation bundle locally accessible. On startup, an instance serves only its last-known-good or a fully validated current generation; it never serves an incompatible strategy/schema/snapshot combination, and it reports its generation in every response (§6.1).
- **Compatibility:** A request is always scored with the strategy, feature schema, and retrieval snapshot **of one single generation** — mixing components across generations is a defect, tested explicitly.

### 8.4 Experiment state machine (R13)

Every experiment (one candidate generation vs the current stable) moves through audited states:

```text
draft → offline-approved → shadow → canary → stable
   \________ any state ________> aborted (kill switch)
```

- Transitions require the §9 gate evidence for `offline-approved`, an operator action for `canary` and `stable`, and are written to the audit log with actor and reason.
- **Guardrails:** Canary carries configured guardrail thresholds (fallback rate, error rate, latency, log-persistence rate). A breach **pauses the experiment automatically** (canary → 0%) and alerts; resuming requires an operator action.
- **Kill switch:** A single audited admin action aborts the experiment and restores stable-only serving, independent of the normal rollback path.
- **Rollback** (§8.1) is idempotent and *observed*: the operation returns only after instances confirm they serve the restored generation, or reports which instances have not yet confirmed.

### 8.5 Inference execution and timeout honesty (R13)

- **Product Alpha:** ML inference may run in-process under the logical deadline (§9.3), with the limitation documented.
- **Operated Release:** ML inference runs in a **bounded dedicated process pool**. A scoring call that exceeds the deadline, crashes, or hangs has its worker process terminated and recycled, and the request falls back to the rule strategy. Shadow scoring runs on a **separately bounded** executor so shadow load can never starve served traffic; shadow work is shed first under load.
- CPU saturation under combined stable + shadow load is measured in the load report (§12, Operated Release); process isolation is validated by a test that kills/hangs a worker mid-request and verifies the fallback response and pool recovery.

## 9. Offline Replay, Metrics, and Release Gate

### 9.0 Evaluation governance (R15)

Three named artifacts with different permissions — never conflated:

- **Development validation (W2):** May be run repeatedly during design and tuning. Every run records its experiment lineage (data/feature/strategy/config versions) in the evaluation report, so tuning history is auditable.
- **Routine release gate:** Evaluates a candidate on the **W2 protocol** (primary metrics, guardrail slices, uncertainty) plus reliability and compatibility checks. The gate does **not** consume W3.
- **Frozen acceptance test (W3):** Membership and labels are sealed (hashed manifest). W3 is opened **only** when a release candidate has been finalized, to produce that candidate family's final independent report; every access is written to `holdout_access_log` with actor, purpose, and release candidate. A subsequent, different model family either designates a new future holdout or reports its results with an explicit repeated-test caveat.
- **Uncertainty and slices (R15):** Headline metrics ship with bootstrap confidence intervals grouped by session, and with pre-declared cohort slices (cold-start vs warm, short vs long sessions, item-popularity buckets) acting as guardrails — a primary-metric win that badly regresses a guardrail slice is recorded and weighed in the promotion decision, with the reasoning written into the release record.
- **Evaluator regression tests (CI):** The evaluation harness itself is tested — swapped labels, duplicate query IDs, future-statistic leakage, and missing targets must each fail or be handled exactly as specified. An evaluator that cannot detect these is not trusted to gate releases.

### 9.1 Evaluator semantics

1. Load the governed query set for this run (W2 for development/gating; W3 only under §9.0's access rule) containing observed session prefix + next-click target.
2. Rebuild candidate set with permitted historical lookup tables — i.e. the W0 statistics snapshot only (R5); replay must satisfy the same `max(statistics_event_ts) < min(query_cutoff_ts)` invariant as training, and the future-event mutation test must pass against the replay path as well as the training path.
3. Build shared features with a pinned feature version.
4. Rank **the same candidates** with baseline, v1, and v2.
5. Compare **end-to-end** quality over identical query IDs and the same cutoff policy.
6. Produce both JSON and Markdown reports including configuration hashes, counts, exclusions, model hashes, and deltas.

### 9.2 Reported metrics

- Candidate `Recall@20` and `Recall@50` (or retrieval depth actually used).
- **Primary:** end-to-end `HitRate@20` and `MRR@20` using full held-out queries (R1).
- **Secondary diagnostic:** end-to-end `NDCG@20`, and conditional (on target retrieved) ranker-only `MRR@20`, `NDCG@20`.
- Query coverage, cold-start split, session length buckets, item popularity buckets.
- Query accounting (R6): total queries generated per window, eligible training groups, all-negative exclusions with `training_query_exclusion_rate`, `single_positive_rate`, and retrieval coverage — reported next to every metric table so conditional and end-to-end numbers can never be confused.
- Model load time, inference p50/p95/p99 and memory on a fixed benchmark machine.
- Bootstrap confidence intervals on session/query grouping as a desirable Hardening item; make no significance claims without uncertainty estimates.

**Important:** Single-next-click binary-label evaluation produces a useful but narrow NDCG. Do not claim it measures revenue or true cart/order utility.

### 9.3 Proposed release gates (configurable, not guaranteed outcomes)

- Feature schema and artifact checksum match.
- Offline replay and golden parity tests pass; no time leakage tests fail.
- Candidate coverage and the primary metrics (end-to-end HitRate@20, MRR@20) must **not regress** beyond a configured tolerance against the current stable reference (initial default: 1% relative, with small-sample variance reported).
- NDCG@20 (secondary) does not regress materially vs current stable under the frozen validation run; a secondary-only regression is reported and weighed in the promotion record, but the promotion decision is driven by the primary metrics.
- Target API p95 ≤ **100 ms** for requests with ≤100 candidates and a preloaded model on a documented local machine; actual measured results determine pass/fail.
- **Staged latency budget (R9e):** The 100 ms target is for the **end-to-end API path**, not for `predict()` alone. Provisional stage budgets (planning values, not measured results): input validation 5 ms; candidate retrieval 20 ms; feature assembly 25 ms; model scoring 20 ms; response assembly 5 ms; scheduling/contingency 25 ms — total 100 ms. Separately, the **model-scoring deadline** is a distinct, configured value: when scoring exceeds it, the request takes the fallback path (§8.1). As established in §4.4, this is a *logical* deadline — a thread/coroutine timeout does not forcibly stop an already-running native call — Alpha does not introduce process-isolated inference for this point and documents the limitation; Operated Release replaces it with the §8.5 process pool.
- Fault injection must return valid baseline rankings for missing/failed model; no unhandled 5xx for expected model faults.
- Promotion fails closed on missing evaluation artifacts.

**Do not adjust gate thresholds after seeing the frozen test results.** Gate selection uses validation; frozen test is a final independent report.

**Pre-registered gate-failure path (R1):** A strong co-visitation baseline is a known property of this dataset family, so an ML version may legitimately fail to beat the rule baseline on the primary metrics. This outcome is decided in advance to mean the following, and nothing else:

- The failing ML version is **not promoted**; stable keeps serving the rule baseline (or the last version that cleared the gate). The gate result, metrics, and decision are recorded in the evaluation report exactly as measured.
- A blocked promotion is **successful evidence for this project**, not a project failure: it demonstrates the release gate, the replay harness, and the rollback-free "stay on stable" path working as designed. The demo storyboard and interview story may present it as such, with the actual numbers.
- Project completion (§15) does **not** require any ML version to beat the baseline. It requires that baseline, v1, and v2 were all evaluated on the identical frozen query set, that the gate decision followed the pre-registered thresholds, and that the served configuration matches that decision.
- Thresholds, features, or the candidate budget must **not** be changed after seeing validation/test results in order to manufacture a win. Any such change starts a new version with a new frozen configuration and a fresh evaluation, documented as such.

### 9.4 The closed learning loop (R12)

Feedback ingestion alone is not a learning loop. The Beta stage (§12) adds a **versioned, manually triggered pipeline** that turns captured events into a governed candidate strategy:

```text
pipeline run (run_id)
  raw_events → validated_events (+ quarantine counts and reasons)
             → attribution join (impression ↔ actions, window + provenance rules)
             → training_dataset_version (immutable; source filter + window manifest recorded)
             → train candidate strategy (frozen training config)
             → W2 evaluation (§9.0 protocol, vs current stable)
             → release_decision (promote to experiment / reject, with recorded reasoning)
```

- **Lineage:** The `run_id` links every stage's inputs and outputs (`pipeline_runs`, §7); any candidate strategy can be traced back to the exact dataset version and event set that produced it, and any dataset version back to its source filter.
- **Provenance quarantine (hard rules):** Events failing validation, attribution, or provenance checks are quarantined with counts and reasons — never silently dropped and never silently included. `source=demo` events are **excluded from every real-data training snapshot and from all OTTO evaluation**; a snapshot built for a demo rehearsal is labeled `demo-trained` and can never be promoted against W2/W3 as if it were real.
- **Pipeline rehearsal:** With no real users, the loop is demonstrated on time-appropriate OTTO data (a later OTTO slice treated as newly arrived data under the same point-in-time rules) — a genuine rehearsal of the process, explicitly not evidence of live feedback improving a model.
- **Promotion is a decision, not an automation:** The pipeline ends at a recorded release decision by the operator under §8.4/§9.3. Scheduling the pipeline is an optional later extension (§12).

## 10. Reliability and Observability

### 10.0 Event durability contract (R14)

Impression and decision capture is a first-class boundary, implemented as a **transactional outbox** in PostgreSQL:

- Serving a response writes, **in one database transaction**: the impression row, the decision log row, and an outbox event. If that transaction commits, the exposure is durable and the impression is eligible for attributed feedback (`logging_status: persisted`).
- An outbox consumer delivers events to downstream stores (feedback/attribution, monitoring aggregates) **at-least-once**, with idempotent consumers keyed by `event_id`, bounded retries with backoff, and a dead-letter state with operator visibility. Delivery never double-counts: consumer-side deduplication is tested.
- Event ordering is guaranteed **per impression/request**, not globally. Late feedback arrivals are handled by the §6.3 attribution window; events arriving after it are counted as `late_events`, not silently dropped.
- If the write transaction fails (DB unavailable), the ranking response is still served with `logging_status: degraded`; that impression is **not** eligible for attribution, and the loss is counted in `impressions_served` vs `impressions_persisted`. This is the documented degraded mode — the system never claims an exposure it did not persist.
- Required metrics at all times: `impressions_served`, `impressions_persisted`, `decision_log_persistence_rate`, `unattributable_feedback`, `duplicates`, `late_events`, and outbox consumer lag.
- **Recovery test (required, Operated Release):** kill the API and/or make the DB unavailable mid-traffic, restart, and prove: committed outbox events are delivered exactly once in effect, uncommitted impressions are reported as degraded (not phantom-attributed), and no feedback is double-counted.

### 10.1 Failure matrix

| Failure | Expected behavior | Evidence |
|---|---|---|
| Model artifact missing/corrupt | Load rejects candidate, stable/fallback stays live | Startup/promote test |
| Inference exception | Rule baseline returns valid result | Injected exception test |
| Inference deadline exceeded | Bounded fallback path returns; document hard-timeout limitations | Deterministic delay injection |
| Feature schema mismatch | Reject incompatible model, fallback | Version contract test |
| Redis unavailable | Read-through/DB or in-memory static retrieval data; increased latency flagged | Redis outage test |
| DB logging unavailable | Ranking still served with `logging_status: degraded`; impression not eligible for attribution; loss counted (R14 contract, §10.0 — the outbox guarantee covers everything that committed; nothing uncommitted is claimed) | DB fault + recovery test |
| Canary model unhealthy | Elevated fallback/exception alert, operator rollback procedure | Canary incident demo |
| Duplicate feedback | No double count | Idempotency test |

### 10.2 Operator Console metrics

Show: active stable and canary strategies, canary percentage, shadow strategy, requests by strategy, latency p50/p95/p99, fallback count/rate, errors, candidate count, replay metric summary, feedback counts by source, score distribution, feature missing-rate, and PSI alerts.

**Log-durability metrics (R9d, upgraded by R14):** The Operator Console and metrics summary show the §10.0 metric set — `ranking_success_rate`, `impressions_served`, `impressions_persisted`, `decision_log_persistence_rate`, `unattributable_feedback`, `duplicates`, `late_events`, outbox lag and dead-letter count. The impression/decision/outbox write runs under a bounded timeout inside the request transaction so logging latency cannot consume the §9.3 latency budget; downstream delivery is asynchronous and never retried synchronously in the request path.

### 10.3 Drift

- Compare recent scored feature bins to **training/reference** bins, stratified by model/version where meaningful. The initial monitored set is the named features from the v2.1 Hardening scope (session length, candidate co-visitation score, item popularity score) plus score distribution; the set may be extended at Operated Release as recorded configuration under §10.4, which is not a scope change.
- PSI is a **distribution-change heuristic**, not a statistical proof of model degradation. Use a minimum sample count and fixed bin edges.
- Example warn ≥0.1 / alert ≥0.25 **only as configurable starting values**, not universal truth.
- Track missing-rate and score distribution drift separately; label an alert `insufficient_data` when sample minimum not met.
- Demo can inject a controlled shifted feature stream with `source=demo`; never present it as actual post-deployment drift.

### 10.4 Quality, freshness, SLOs, and alert actions (R18)

Beyond latency and PSI, the Operator Console tracks:

- **Freshness:** retrieval snapshot age and watermark, statistics build time, dataset/pipeline run recency.
- **Input quality:** unknown-item rate, feature missingness by named feature, out-of-range feature values.
- **Ranking quality proxies:** candidate count distribution, duplicate rate in results, per-source candidate coverage and overlap, repeated-item and popularity concentration, served-strategy mix.
- **Service SLOs (provisional targets, revised only from measured reports):** successful ranked-response rate, fallback rate, end-to-end p95/p99 against §9.3, event-persistence success rate, promotion/rollback success rate. Error-budget burn is reported per SLO.

**Every alert maps to an action** — an alert with no action is a defect in the monitoring design:

| Signal | Default action |
|---|---|
| Canary guardrail breach (fallback/error/latency) | Auto-pause experiment (§8.4), page operator |
| Feature/score drift alert (min-sample met) | Investigate; block promotion of new generations until reviewed |
| Snapshot age beyond freshness SLO | Rebuild statistics snapshot under R5/R16 rules; do not silently serve ever-older statistics |
| Log-persistence rate below SLO | Investigate DB/outbox; treat affected impressions as attribution-ineligible |
| Unknown-item rate spike | Investigate upstream/session source; check snapshot coverage |
| Rollback failure | Incident: follow release runbook, freeze further promotions |

**Cross-version score caution:** Raw LightGBM scores are not comparable across strategy versions. Version comparisons in the Console use rank agreement (overlap@K, rank correlation over shared candidates), quality metrics, and per-version score distributions — never a raw-score diff.

**Shadow honesty:** Shadow results support service/performance comparison only; they are never presented as counterfactual CTR or lift evidence (§11).

## 11. Security, Privacy, Deployment, and Ethics (R19)

**Access control:**
- Roles: `viewer` (read Console/metrics), `operator` (traffic changes, experiment transitions, rollback), `admin` (strategy registration/promotion approval, role and config management). Admin mutations require authentication and a role check even in local Compose; every mutation lands in the append-only `admin_audit_log`. API docs explicitly distinguish this demo-grade auth from production identity systems.
- The public ranking endpoint enforces request-size limits, rate limits, and strict payload validation (§6.1). The Playground is served with a documented CORS policy limited to its own origin.
- Assignment salt (§8.2) is custody-managed configuration: its value is secret, its `salt_id` is versioned and recorded per experiment; rotating the salt starts a new experiment, never silently reassigns an existing one.

**Privacy and data lifecycle:**
- Anonymous session IDs are pseudonymous data, not automatically non-sensitive: they are stored hashed with the experiment salt where raw IDs are not needed, and raw session payloads follow a configured retention period with a documented deletion procedure for logs, feedback, and derived datasets.
- No names, emails, IPs, or payment data are collected anywhere in this project (§6.3).

**Supply chain and reproducibility:**
- No secrets, raw dataset, or model binaries committed accidentally; `.gitignore`, `.env.example`, hashes and retrieval commands included. Secrets come from environment/secret configuration, never from the repo.
- CI runs dependency and container-image scanning; a short threat model (`docs/threat_model.md`) covers the admin surface, the feedback endpoint, and artifact substitution.

**Deployment and recovery:**
- Docker Compose is the reproducibility baseline. **Operated Release** additionally requires **one reference deployment**: a single managed container environment (default: AWS Fargate in ca-central-1 via CDK, reusing this portfolio's established deploy→smoke→cost-record→teardown pattern), with health/readiness checks, repeatable database migrations, and documented secret handling. Kubernetes is explicitly not required (§2.2).
- **Backup/restore:** A PostgreSQL backup/restore drill (dump → fresh instance → restore → smoke queries against registry, generations, and logs) is executed and recorded before Product Complete; an untested backup is not a backup.

**Ethics and claims:**
- Dataset license attribution and relevant citation in README. Prefer reproducible download instructions over redistributing OTTO raw files.
- Do not present historical offline labels as randomized exposure/propensity ground truth.
- No fabricated claims of conversion lift, user impact, production traffic, or business revenue.
- `source=otto_offline` and `source=demo` separate every chart/report/data export. Never use demo feedback to score held-out OTTO evaluation.

## 12. Development Stages and Acceptance Gates (R20)

**Scheduling (R10):** There is no fixed day limit and no calendar-based stage. Stages run in the order below — foundations and data semantics before infrastructure polish, because data validity is the highest-leverage risk — and a stage is complete only when its exit gate passes with recorded evidence. The project target is **Stage 4 — Product Complete**.

### Stage 0 — Foundations: product contract and data semantics

**Build:** Product contract (personas: Playground reviewer, operator; demo workflows; claims/non-claims, §1/§11); deterministic sampled subset; the R5 window scheme (W0–W3) and manifest; `event_index` and query identity (R21); cutoff/label generation; exact co-visitation build (R21) with R2 bounds; leakage, boundary, and future-event mutation tests; window-exclusion accounting.

**Exit gate:** A data-validation report exists; the query set is deterministic and reproducible from the manifest; replay of a recorded session prefix is leak-free; the UX/API contract for the Playground is written down.

### Stage 1 — Product Alpha: the ranking product, usable end to end

**Build:** Three-source candidate generation (R9b definitions) and candidate coverage; shared feature builder with R21 masks; rule strategy registered as `rule-v1` and initial LightGBM strategy; FastAPI `/v1/recommend` with request-scoped fallback and assigned/served logging; release bundles as serving generations in their initial (single-instance) form; the **Ranking Playground** (§6.4) with side-by-side strategy comparison and demo feedback submission; initial event integration via the outbox (§10.0) in its basic form; Docker Compose one-command deployment; API contract tests.

**Exit gate:** A reviewer can complete the §6.4 loop — session → ranked results with provenance → attributed demo interaction → the event visible — and reproduce the same request via the API with identical output under the same generation.

### Stage 2 — ML Platform Beta: the verifiable ML lifecycle

**Build:** Full lineage binding (R16) across dataset/retrieval/feature/strategy/evaluation/generation; reproducible training for rule/LightGBM strategies including the pointwise comparison experiment (P1-3 of the v2.1 review: controlled, pre-declared model-selection objective — primary HitRate@20/MRR@20, deltas with uncertainty, guardrail slices, tie-breaking, and the no-promotion outcome); governed evaluation (R15: W2 repeatable + gate, W3 sealed); retrieval ablation and recall-vs-latency Pareto (R17) fixing the production retrieval depth; the **closed learning loop** (R12) — a manually triggered pipeline run producing a candidate strategy and a recorded release decision; experiment state machine (R13) with shadow/canary, guardrail auto-pause, kill switch, and idempotent observed rollback; multi-instance generation promotion (§8.3) tested with at least two API instances.

**Exit gate:** The complete pipeline replays end to end from recorded version IDs, and a deliberately degraded candidate is rejected by the gate reproducibly, with the decision and its evidence recorded.

### Stage 3 — Operated Release: reliability, security, and operations

**Build:** Process-pool inference isolation (§8.5) validated under load and fault injection across the §10.1 failure matrix; the full outbox durability contract (§10.0) including the kill/restart recovery test; measured end-to-end performance under representative concurrency against the §9.3 staged budget; quality/freshness/SLO monitoring with alert→action runbooks (R18) and an incident exercise (inject → alert → action → rollback → post-incident record); security contracts (R19): roles, audit integrity, retention/deletion, scanning, threat model; the **reference deployment** (§11) with migrations, health/readiness, and the backup/restore drill.

**Exit gate:** Every documented failure scenario is demonstrably recoverable with evidence, the service runs in the reference deployment (or its recorded deploy→smoke→teardown evidence exists), and service-level limits are stated from measurements, not aspirations.

### Stage 4 — Product Complete: evidence and independent reproducibility

**Build:** Candidate-source and model ablation summaries with accuracy–latency tradeoffs; the final W3 acceptance report for the finalized release candidate (opened once, under §9.0 governance); the complete evidence package — architecture, experiment matrix, model card, data card, release history, load/fault reports, Operator Console, training lineage, demo recording (§14), operational runbooks, and the R3 search-ranking translation note; an explicit statement of whether any real user experiments took place (none are assumed).

**Exit gate:** An external reviewer, using only the repository and recorded version IDs, can reproduce: one model evaluation, one promotion decision, one rollback, one incident recovery, and one subsequent training run.

### Optional later extensions (value-driven; not required for Product Complete, not in frozen scope)

- Cart/order multi-task prediction heads and calibrated multi-objective ranking, after the next-click path is operated and measurable.
- Scheduled retraining with data-quality gates and champion/challenger governance.
- A separately licensed realistic catalog, or a separate query-based search demonstration.
- Advanced retrieval (embeddings/ANN) only if the R17 ablation demonstrates necessity.
- Distributed infrastructure only when load tests or architecture requirements justify it.

## 13. Suggested Repository Structure

```text
rankflow/
  api/
    main.py
    routes/{recommend,feedback,strategies,admin,metrics,playground,console}.py
    schemas.py
  rankflow/
    candidates.py
    features.py
    baseline.py
    ranker.py
    router.py
    registry.py
    logging.py
  training/
    prepare.py
    build_retrieval_tables.py
    make_queries.py
    train.py
    evaluate.py
    checks.py
  pipeline/
    attribution.py
    build_dataset.py
    retrain_run.py
  serving/
    generations.py
    inference_pool.py
    outbox_consumer.py
  monitoring/
    drift.py
    aggregate.py
  tests/
    unit/
    integration/
    fault_injection/
    golden/
  sql/
    001_init.sql
  artifacts/         # ignored; manifest + checksums retained
  configs/
    train_v1.yaml
    train_v2.yaml
    gate.yaml
  scripts/
    fetch_data.sh
    smoke.sh
    replay.sh
    benchmark.sh
    demo_canary.sh
  docs/
    architecture.md
    evaluation_report.md
    load_test_report.md
    release_runbook.md
    search_ranking_translation.md
    threat_model.md
    data_card.md
    model_card.md
  docker-compose.yml
  .env.example
  README.md
```

## 14. Demo Storyboard (3–5 minutes)

1. In the **Playground**, load a real OTTO-derived held-out session prefix; explain the prediction cutoff, `event_index`, and labels.
2. Request a ranking; walk candidates → shared features → strategy ranking, showing serving generation, snapshot ID, and the decision log entry.
3. Trigger an injected inference fault (or kill an inference worker); the response still returns via the rule strategy, with assigned ≠ served strategy and an auditable reason.
4. Show a candidate's **W2 evaluation report** and the gate decision — including, if it happened, a blocked promotion (R1) — then run the experiment: shadow → 10% session-sticky canary → guardrail pause or promotion, in the Operator Console.
5. Submit a demo click in the Playground linked to that impression; verify attribution, provenance labels, and duplicate suppression; show the outbox delivering the event.
6. Run the **learning-loop pipeline** (R12) on a later OTTO slice: show the run lineage from raw events to a new candidate and its recorded release decision; show `source=demo` being quarantined out of the real-data path.
7. Inject a controlled feature shift; show the drift alert and the action it maps to; issue a rollback and verify all instances serve the restored generation.
8. Close with **what the evidence does not prove**: no causal CTR lift, no production users, no randomized impressions.

## 15. Definition of Done — four stages (R20)

Completion is claimed **per stage**, only when that stage's exit gate (§12) passes with recorded, reproducible evidence. **Product Complete** is the project target (R10) and requires all four stages. Per R1, no stage requires an ML strategy to beat the rule strategy or to be the served stable strategy; every stage requires the pre-registered gate decisions (§9) to have been followed and recorded, whichever way they went.

### Stage checklists

**Stage 1 — Product Alpha**
- [ ] Foundations gate passed (Stage 0): data-validation report, deterministic query set, leak-free replay
- [ ] Ranking API with deterministic output, request-scoped fallback, assigned/served strategy logging
- [ ] Ranking Playground: full §6.4 interaction loop with provenance on every result; synthetic display labels marked
- [ ] Serving generations in initial form; `docker compose up --build` reproduces the product locally
- [ ] API contract tests, cold-start cases (R9a), and the R6 golden fixture pass

**Stage 2 — ML Platform Beta**
- [ ] Full lineage (R16): any release traces dataset → retrieval → feature schema/code → strategy → evaluation protocol → generation
- [ ] Governed evaluation (R15): W2 gate protocol with uncertainty and guardrail slices; W3 sealed with access logging
- [ ] Retrieval ablation + recall-vs-latency Pareto (R17); production retrieval depth chosen from it and recorded
- [ ] Learning loop (R12): one complete pipeline run with lineage and a recorded release decision; demo-source quarantine proven by test
- [ ] Experiment state machine (R13) with guardrail auto-pause and kill switch; multi-instance promotion and idempotent rollback tested

**Stage 3 — Operated Release**
- [ ] Process-pool inference isolation (§8.5) validated; §10.1 failure matrix demonstrated, including the outbox kill/restart recovery test (R14)
- [ ] Measured load report against the §9.3 staged budget (p95 target explicitly pass/fail, documented machine/concurrency)
- [ ] Quality/freshness/SLO monitoring with alert→action runbooks (R18); one incident exercise recorded end to end
- [ ] Security contracts (R19): roles and audit, retention/deletion, CI scanning, threat model
- [ ] Reference deployment (§11) demonstrated with migrations and health checks; backup/restore drill executed and recorded

**Stage 4 — Product Complete**
- [ ] Final W3 acceptance report for the finalized release candidate, opened under §9.0 governance, with honest limitations
- [ ] Ablation summaries (retrieval sources, model comparison) with accuracy–latency tradeoffs
- [ ] Complete evidence package: architecture, experiment matrix, model/data cards, release history, load/fault reports, runbooks, R3 translation note, demo recording (§14)
- [ ] Independent reproducibility: an external reviewer reproduces an evaluation, a promotion decision, a rollback, an incident recovery, and a training run from recorded version IDs alone
- [ ] Public claims audit: every claim distinguishes historical offline outcomes, synthetic/local demos, and (absence of) real online-user evidence

No claim of Product Complete may rely on future promises, screenshots alone, or an unverified performance target. Any stage item not built is listed by name with its status; a stage with a silently missing item is not complete.

---

## 16. Decisions Record (frozen with v3.0)

**Resolved in v2.0:** primary/secondary metric ordering and the gate-failure path (R1); co-visitation pruning bound and manifest reporting (R2 — exact `top_n_per_item` / minimum-count values are configuration, confirmed against the sampled subset and recorded); the search-ranking translation note (R3); Hardening tiers (R4 — superseded as a completion concept by R20's stages; retained only as historical context).

**Resolved in v2.1:** point-in-time window scheme and mutation test (R5); all-negative training-group policy (R6); ranking-strategy abstraction, fallback vs rollback, assigned/served logging (R7); two completion levels (R8 — superseded by R20); cold-start, Recall@K definitions, experiment-scoped hashing, log-durability metrics, staged latency budget (R9); no fixed development time limit (R10).

**Resolved in v3.0 (the product decisions, frozen):**

1. **Product identity:** Ranking Playground + Operator Console over the ranking API (R11). Not headless-only, not a storefront.
2. **Task:** Next-click only. Carts/orders are input history and feedback types; multi-task prediction is an optional later extension outside frozen scope.
3. **Completion model:** Four stages — Product Alpha → ML Platform Beta → Operated Release → Product Complete (R20) — each with its §12 exit gate and §15 checklist. Product Complete is the target.
4. **Serving topology:** Single-process development is acceptable for Alpha; the multi-instance generation-promotion contract (§8.3) must be **tested with at least two instances** by Beta and operated by Operated Release.
5. **Event durability:** Transactional outbox semantics (§10.0): committed = durable and attribution-eligible; uncommitted = degraded and counted. No stronger or weaker claim is made anywhere.
6. **Training trigger:** Manually triggered pipeline with complete lineage (R12); a schedule is an optional extension, not frozen scope.
7. **Holdout governance:** W2 for development and routine gating; W3 sealed, access-logged, final-report only; future families need a new holdout or a repeated-test caveat (R15).
8. **Operational SLOs:** The §10.4 provisional targets apply at Operated Release and may be revised **only** from measured reports, with revisions recorded — never silently relaxed to claim a pass.
9. **Deployment:** Docker Compose baseline + one reference deployment (default AWS Fargate, ca-central-1, via CDK, with the portfolio's deploy→smoke→cost-record pattern) at Operated Release (§11).
10. **Catalog presentation:** Item IDs plus clearly marked synthetic display labels only; no attribute may be implied to come from OTTO (R11).

**Configuration, not scope (recorded in manifests as work proceeds):** exact sampled-subset size and window boundaries; `top_n_per_item` and minimum co-occurrence values; retrieval depth after the R17 ablation; gate tolerances set on W2 before any W3 access; model hyperparameters; instance sizes for the reference deployment.

## 17. References

- OTTO official repository and README: https://github.com/otto-de/recsys-dataset
- OTTO data and task details: https://www.kaggle.com/competitions/otto-recommender-system/data
- LightGBM ranking objective configuration: https://github.com/lightgbm-org/LightGBM/blob/main/examples/lambdarank/train.conf

**Status:** **v3.0 — FROZEN (product scope)**, 2026-11-19, by owner decision after incorporation of R11–R21. Scope changes require the owner's explicit unfreeze plus a new review round. No model benchmark, performance result, online uplift, or completed implementation is claimed by this document.
