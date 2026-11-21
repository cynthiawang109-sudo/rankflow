# RankFlow — §9.3 Layered Latency Amendment Approval

**Decision:** APPROVED FOR FREEZE  
**Decision date:** 2026-11-21  
**Project:** RankFlow (Project 5)  
**Scope:** Stage 4 performance-governance amendment; authorization to freeze the revised performance contract and run a formal compliance benchmark

## 1. Executive Decision

Approve the proposed three-layer latency contract and its thresholds **without modification**. The original §9.3 end-to-end **100 ms p95 target remains FAILED** in the historical acceptance record. This approval is not a retroactive pass, an SLO waiver, or authorization for another optimization cycle.

The revised thresholds must be versioned, approved, and frozen **before** the formal benchmark is run. All measured failures must be reported accurately, even if client-visible latency passes.

## 2. Approved p95 Acceptance Thresholds

| Measurement boundary | Applicable modes | p95 threshold |
|---|---|---:|
| **Handler latency** | Stable, Peak, Shadow, Canary | **≤ 100 ms** |
| **Persistence latency** | Stable, Peak, Shadow, Canary | **≤ 50 ms** |
| **Client-visible latency** | Stable, Shadow, Canary | **≤ 250 ms** |
| **Client-visible latency** | Peak | **≤ 400 ms** |

### Measurement definitions

- **Client-visible:** Request initiation at the designated reference client through receipt of the complete response, including client/network, TLS, ALB, and application effects. Results apply to the specified client location and protocol, not to every possible internet client.
- **Handler:** Application-side request-processing interval, including any synchronous persistence on the critical path.
- **Persistence:** Durable PostgreSQL transaction interval through successful commit acknowledgement, including required decision, impression, and outbox writes.

Handler and persistence are **nested measurements**, not additive independent budgets. Report p50, p95, and p99 for each layer and each serving mode. Correlate per-request traces where feasible. For outside-handler latency, compute the difference **per request first**, then aggregate its distribution; never subtract aggregate p95 values.

## 3. Existing Evidence and Expected Outcome — Not a Formal Benchmark

The following are measurements already collected during the Stage 4 performance optimization work. They are **not** the result of the formal benchmark authorized by this decision.

### Cloud client-visible p95

| Mode | Before | After | Improvement | Original 100 ms target gap | Proposed client-visible threshold | Expected result |
|---|---:|---:|---:|---:|---:|---|
| Stable | 326 ms | **176 ms** | **46.0%** | +76 ms | 250 ms | Likely PASS |
| Peak | 572 ms | **329 ms** | **42.5%** | +229 ms | 400 ms | Likely PASS |
| Shadow | 333 ms | **133 ms** | **60.1%** | +33 ms | 250 ms | Likely PASS |
| Canary | 265 ms | **110 ms** | **58.5%** | +10 ms (rounded) | 250 ms | Likely PASS |

### Application-side evidence

| Layer | Existing observations | Proposed threshold | Expected result |
|---|---|---|---|
| Handler — Stable/Shadow/Canary | Approximately 81–84 ms p95 | ≤ 100 ms | Likely PASS |
| Handler — Peak | Approximately 198 ms p95 | ≤ 100 ms | Likely FAIL |
| Persistence — all modes | Approximately 67–173 ms p95 | ≤ 50 ms | Likely FAIL |

Local Peak persistence p95 improved from **270 ms to 44.5 ms** after connection pooling and consolidating decision/impression/outbox inserts into one atomic SQL operation. Those local measurements do not override cloud results or the formal benchmark.

Previous reported independent verification: **60 tests passing with real PostgreSQL**, main at **`52a7535`**, and cloud resources removed after testing. These are historical reported observations rather than assertions about a newly inspected repository.

## 4. Mandatory Benchmark Controls

Before the benchmark, document and freeze:

1. Amendment version, approval date and approver, Git commit, and specification hash.
2. AWS deployment architecture and instance/task sizing, database parameters, and ALB/TLS configuration.
3. Reference client location, client implementation, connection reuse settings, and network test conditions.
4. Stable, Peak, Shadow, and Canary request mixes, load/concurrency levels, duration, sample-size minimums, and warm-up policy.
5. Start/end boundaries for each latency layer, timing instrumentation, request correlation and percentile methodology.
6. Per-mode p50/p95/p99 reporting; explicit missing data, outliers, errors, fallback events, and sample counts.
7. Artifact and environment identifiers that allow an independent rerun.

Do not choose or adjust thresholds based on the already observed values. Freeze the agreement before collecting official acceptance measurements.

## 5. Governance and Safety Conditions

- **Preserve original result:** The original §9.3 100 ms end-to-end target remains **FAILED**, permanently and without retroactive reinterpretation.
- **No unauthorized optimization:** This decision authorizes specification freeze and an independent benchmark only; it does **not** authorize additional performance engineering.
- **Preserve correctness:** Atomic durable decision/impression/outbox writes, commit-before-attribution semantics, and related crash/recovery guarantees must remain intact.
- **No aggregate masking:** Passing client-visible latency cannot compensate for failing handler or persistence latency.
- **No percentile arithmetic shortcut:** Do not subtract p95 statistics to infer outside-handler p95. The existing per-request subtraction followed by percentile aggregation is acceptable.
- **Previously closed items remain closed:** T07 incompatible-feature-schema isolation replay, SPEC §14 controlled drift-and-alert demonstration, and independently reproducible OTTO artifact archive were completed and signed off in the Closure Sprint. Their existing closure evidence is sufficient; this amendment does not reopen them.
- **Model release governance remains unchanged:** `rule-v1` remains the stable strategy; `lgbm-v1` remains rejected by W2-gate, and this latency amendment does not confer model promotion approval.

## 6. Compliance and Sign-off Rules

| Formal benchmark finding | Status |
|---|---|
| All four modes meet all applicable client-visible, handler, and persistence p95 thresholds | **Performance SLO Compliant** |
| Client-visible passes, but any handler or persistence threshold fails | **Performance SLO Partially Compliant**; list every failed layer/mode |
| Other failures | **Not Compliant** for the affected requirements; report granular results |
| Missing, incomparable, or insufficient benchmark evidence | **Not Verified**; do not claim PASS |

The benchmark report must distinguish historic evidence, preregistered criteria, and independently observed official results.

## 7. Authorization and Next Steps

**APPROVED:** Freeze the versioned §9.3 layered-latency amendment with the thresholds in §2, then execute the formal benchmark under the predefined measurement protocol.

**NOT APPROVED:** Retroactively marking the original target as passed; relaxing thresholds based on measured values; silently revising the benchmark protocol after results are seen; or starting another optimization cycle under this approval.

**Current compliance status:** **PENDING INDEPENDENT BENCHMARK.**

The evidence suggests that the client-visible thresholds may pass, while Peak handler and all-mode persistence thresholds may fail. This is an **expectation**, not an acceptance result. Record whatever the formal benchmark demonstrates.
