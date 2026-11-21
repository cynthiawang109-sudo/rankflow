# RankFlow — Layered Latency Budget Governance Decision

**Project:** RankFlow (Project 5)  
**Decision:** Approve Option (b) — Layered Latency Budget  
**Status:** Performance-governance amendment approved for definition; compliance not yet verified  
**Decision date:** 2026-11-21  
**Scope:** SPEC §9.3 and Stage 4 performance acceptance

## 1. Executive Decision

**Approve Option (b): replace the ambiguous single latency measurement with a versioned, layered latency contract.**

This decision is **not** a waiver, a retroactive pass, or permission to lower thresholds to match current measurements. The original **100 ms client-visible p95 target remains FAILED**. New acceptance thresholds must be justified, documented, and frozen **before** a formal independent benchmark.

The performance optimization work itself is **ACCEPTED**, subject to the independently reported evidence and preservation of durability and attribution guarantees.

## 2. Evidence from the Completed Performance Work

### 2.1 Changes implemented

- Introduced connection pooling.
- Consolidated impression, decision, and outbox inserts into **one SQL statement**, committed atomically.
- Preserved the contract that an impression/decision is attributable only after durable commit.
- Recorded crash-point survival analysis.
- Local peak-mode persistence p95 improved from **270 ms to 44.5 ms**.

### 2.2 Cloud benchmark — same protocol, client-visible p95

| Mode | Before (ms) | After (ms) | Relative reduction | Remaining gap to 100 ms |
|---|---:|---:|---:|---:|
| Stable | 326 | 176 | 46.0% | +76 ms |
| Peak | 572 | 329 | 42.5% | +229 ms |
| Shadow | 333 | 133 | 60.1% | +33 ms |
| Canary | 265 | 110 | 58.5% | Approximately +10 ms |

All four modes improved, but **none met the original 100 ms client-visible p95 target**.

### 2.3 Observed latency structure

- For Stable and Peak, measured **handler-external p95** alone exceeded 100 ms over the home-client → network/TLS → ALB path. Under that particular client-location and network protocol, the original 100 ms client-visible target is not attainable solely through server-handler optimization.
- PostgreSQL persistence remains the main **within-handler** latency contributor (reported approximately **67–173 ms**, with Peak particularly affected).
- The conclusion above is limited to the tested client location and deployment configuration; it is not proof that a 100 ms end-to-end target is universally impossible.
- **Do not subtract independently reported p95 values** and label the difference “network p95.” Percentiles from different distributions are not additive. Measure instrumented segments or use correlated per-request traces.

### 2.4 Verification and operational hygiene

- **60 tests passed** against real PostgreSQL, independently rerun, with no skips.
- Cloud infrastructure was dismantled, and AWS resource checks found no remaining resources from the exercise.
- Three commits were pushed to GitHub; reported `main` head: `52a7535`.
- These are reported acceptance facts; this decision document is not a substitute for the underlying run logs or audit artifacts.

## 3. Revised §9.3: Three Latency Measurement Layers

| Layer | Measurement boundary | Purpose |
|---|---|---|
| **Client-visible latency** | From a specified benchmark client issuing a request until the full response is received, including network, TLS, and load-balancer path | Customer-experience and end-to-end assessment |
| **Handler latency** | From application request entry to application response completion, with the boundary instrumented and explicitly documented | Application-owned request-path performance |
| **Persistence latency** | From the start of the required PostgreSQL persistence transaction until successful commit acknowledgement | Durable write cost, bottleneck tracking, and correctness-sensitive performance |

For **Stable, Peak, Shadow, and Canary**, report **p50, p95, and p99** at each layer. Preserve the full distributions and enough per-request correlation to identify which stages dominate the request path. Define explicitly whether queueing, middleware, serialization, and shadow work are inside the handler boundary.

### Required benchmark controls

Before choosing or approving numerical targets, document:

1. Client region/location and network characteristics, including whether the client is inside or outside AWS.
2. Cloud region, load-balancer and TLS configuration, service/task sizing, database instance class, and connection-pool settings.
3. Dataset and serving generation, request mix, concurrency, arrival rate, duration, warm-up period, and sample count.
4. Stable/Peak/Shadow/Canary traffic behavior and whether background work is included.
5. Timestamp and trace instrumentation, time synchronization, percentiles methodology, missing samples, and error/timeout treatment.
6. Separate budget ownership: client path vs application processing vs durable database work.

**Do not define new pass thresholds by rounding above the measurements in this report.** Set defensible targets based on the product's experience and reliability objectives and a representative, preregistered benchmark protocol. Freeze the revised contract before the next acceptance run.

## 4. Non-Negotiable Correctness and Governance Rules

- Preserve the **atomic impression / decision / outbox persistence** contract.
- Preserve **commit-before-attribution** semantics and crash/retry correctness.
- Do not shift required durable records into an unacknowledged in-memory queue merely to lower response latency.
- Keep the original §9.3 benchmark and its **FAILED** result in historical acceptance records.
- Version the revised §9.3 contract, documenting the rationale and effective date.
- Do not infer segment percentiles by subtracting aggregate percentiles.
- Do not conduct an additional performance-tuning cycle under this decision; it authorizes **measurement governance and independent verification**, not indefinite optimization.
- A new SLO can be marked **PASS** only after the frozen protocol and thresholds are tested and independently accepted.

## 5. Acceptance Status

| Item | Decision |
|---|---|
| Performance optimization P1/P2 | **ACCEPTED** |
| Original SPEC §9.3 client-visible p95 ≤100 ms | **FAILED** |
| Atomic persistence and attribution contract | **PRESERVED / VERIFIED in reported tests** |
| Layered §9.3 measurement model | **APPROVED FOR DEFINITION** |
| Revised numerical thresholds | **NOT YET DEFINED OR FROZEN** |
| Compliance with revised performance contract | **NOT YET VERIFIED** |
| Unconditional Product Complete sign-off | **NOT AUTHORIZED BY THIS DECISION** |

The broader Product Complete exit status must additionally account for the previously reported T07 incompatible-feature-schema replay, §14 controlled drift/alert demonstration, and independently reproducible checksum-pinned OTTO artifact archive until each has separate closure evidence.

## 6. Authorized Next Steps

1. Draft a versioned amendment to SPEC §9.3 with the exact three layer boundaries, benchmark controls, ownership, and reporting rules.
2. Propose numerical acceptance thresholds independently of observed post-optimization measurements; justify each threshold and secure sign-off **before** running the next formal benchmark.
3. Collect correlated client, ALB, handler, and persistence measurements in a representative environment under the frozen protocol.
4. Independently verify Stable/Peak/Shadow/Canary p50/p95/p99, errors, timeout rates, and durability behavior.
5. Record a new performance decision (PASS/FAIL), without rewriting the original failure.
6. Track unrelated Product Complete exit gaps separately; do not mark them complete merely because the performance contract changes.

## 7. Instruction to Codex

> **APPROVE Option (b) — Layered Latency Budget.** Retain the original SPEC §9.3 100 ms client-visible p95 failure. Introduce a versioned, three-layer performance contract for client-visible, handler, and PostgreSQL persistence latency, reported as p50/p95/p99 for Stable, Peak, Shadow, and Canary. Specify client location, load profiles, infrastructure, sample sizes, warm-up, exact timing boundaries, and trace correlation. Do not derive network percentiles by subtraction. Propose and freeze justified numerical acceptance thresholds **before** conducting a new independent benchmark. Preserve atomic decision/impression/outbox durability and commit-before-attribution semantics. This authorization does not permit another optimization cycle or a retroactive SLO pass. Maintain the original evidence and document the revised compliance decision separately.

## 8. Product and Portfolio Implication

This decision establishes an auditable distinction between **a successful engineering optimization** and **satisfying a stated performance SLO**. It makes clear which parts of response latency belong to the client/network path, the application handler, and the durable database commit without weakening correctness guarantees.

Separately, `lgbm-v1` remains **REJECTED** by W2-gate; `rule-v1` remains **Stable**. A future new model candidate may pursue its own governed assessment. Improving latency or completing platform engineering does not confer model-promotion approval.

---

**Final decision:** **Option (b) approved.** Historical §9.3 result remains **FAILED**. The performance optimization work is **ACCEPTED**. Revised layered-SLO compliance remains **OPEN until independent verification**.
