# SPEC §9.3 Amendment v2 — Layered Latency Contract (FROZEN)

**Amendment version:** 2.0
**Status:** FROZEN — approved by the owner on 2026-11-21, before any
benchmark governed by this amendment was run.
**Approver:** Project owner (Cynthia), via the §9.3 Layered Latency
Amendment Approval of 2026-11-21, following the Layered Latency Budget
Governance Decision (Option b) of the same date.
**Base specification:** SPEC.md, SHA-256
`3a12ef37056e5094fb948bf8773e360f87dc35c128a30ce7a394e5482eb728db`.
**Supersedes:** nothing. The original §9.3 target (client-visible
p95 <= 100 ms) and its FAILED results in the Stage 4 verdict and the
performance-track verdict remain in the historical record, unchanged
and without retroactive reinterpretation.
**Preserved without exception:** atomic impression / decision / outbox
persistence; commit-before-attribution; no required durable record may
be moved to an unacknowledged in-memory queue to improve latency.

## 1. Measurement layers

| Layer | Boundary (start → stop) | Notes |
| --- | --- | --- |
| Client-visible | Designated reference client issues the request → full response received at that client. Includes network, TLS, and load-balancer path. | Results apply to the specified client location and protocol, not to every possible internet client. |
| Handler | Application request entry → application response completion, including any synchronous persistence on the critical path. | Nested with persistence; not an additive independent budget. |
| Persistence | Start of the required PostgreSQL persistence transaction → durable commit acknowledgement, including decision, impression, and outbox writes. | Nested inside handler. |

## 2. Approved p95 acceptance thresholds

| Layer | Modes | p95 threshold |
| --- | --- | ---: |
| Handler | Stable, Peak, Shadow, Canary | <= 100 ms |
| Persistence | Stable, Peak, Shadow, Canary | <= 50 ms |
| Client-visible | Stable, Shadow, Canary | <= 250 ms |
| Client-visible | Peak | <= 400 ms |

## 3. Reporting and benchmark controls

- Report p50, p95, and p99 for each layer and each mode, from
  instrumented per-request traces with correlation where feasible.
- Outside-handler latency, when reported, is computed per request
  first, then aggregated. **Never subtract aggregate percentiles.**
- Before the benchmark, document and freeze: amendment version,
  approval date and approver, Git commit, and specification hash;
  AWS architecture and task/instance sizing; database parameters;
  ALB/TLS configuration; reference client location, implementation,
  and connection-reuse settings; per-mode request mixes, concurrency,
  duration, sample-size minimums, and warm-up policy; layer timing
  boundaries and percentile methodology; treatment of missing data,
  outliers, errors, timeouts, and fallback events; artifact and
  environment identifiers sufficient for an independent rerun.
- Thresholds are not chosen or adjusted based on observed values, and
  the protocol is not revised after results are seen.

## 4. Compliance taxonomy

| Formal benchmark finding | Status |
| --- | --- |
| All modes meet all applicable client-visible, handler, and persistence p95 thresholds | **Performance SLO Compliant** |
| Client-visible passes, but any handler or persistence threshold fails | **Performance SLO Partially Compliant** — every failed layer/mode listed |
| Other failures | **Not Compliant** for the affected requirements, reported granularly |
| Missing, incomparable, or insufficient evidence | **Not Verified** — no PASS may be claimed |

Passing client-visible latency cannot compensate for failing handler
or persistence latency.

## 5. Authorization scope

This amendment authorizes the specification freeze and one formal
compliance benchmark under the frozen protocol. It does not authorize
another optimization cycle. Correctness guarantees in the header are
conditions of any measurement run: a run that weakens them is invalid.

**Frozen by:** owner approval, 2026-11-21.
**Freeze commit:** the commit that introduces this file.
