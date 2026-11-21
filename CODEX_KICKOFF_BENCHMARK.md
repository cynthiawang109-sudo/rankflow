# RankFlow — Formal §9.3 Layered Latency Benchmark (Codex kickoff)

## Mandate

The owner approved the §9.3 layered latency amendment (Option b) on
2026-11-21 and froze it as `docs/spec_section_9_3_amendment_v2.md`.
Execute **one formal compliance benchmark** under that frozen contract
and record the performance decision. This authorization covers
measurement and verification only.

**Not authorized:** any optimization or request-path code change; any
threshold or protocol adjustment after results are seen; any model,
gate, or W3 work. If a defect blocks measurement, STOP and report.

## Frozen contract (summary — the amendment file governs)

- Handler p95 <= 100 ms — Stable, Peak, Shadow, Canary.
- Persistence p95 <= 50 ms — Stable, Peak, Shadow, Canary.
- Client-visible p95 <= 250 ms — Stable, Shadow, Canary;
  <= 400 ms — Peak.
- Report p50 / p95 / p99 per layer per mode from per-request traces.
  Outside-handler, if reported, is computed per request first, then
  aggregated. Never subtract aggregate percentiles.
- Compliance taxonomy: all thresholds met → Performance SLO
  Compliant; client-visible passes but any handler/persistence
  threshold fails → Performance SLO Partially Compliant (list every
  failed layer/mode); other failures → Not Compliant for the affected
  requirements; insufficient evidence → Not Verified.

## B1 — Deploy the reference environment

Redeploy the reference stack exactly as in the performance-track run
(Fargate 0.5 vCPU / 2 GiB, two API tasks, HTTPS ALB, RDS PostgreSQL
`db.t4g.micro`, ca-central-1), running the current `main` build.
Record the freeze record in the benchmark report: amendment version,
approval date and approver, the Git commit being benchmarked, the
SPEC.md SHA-256 from the amendment, image digest, task sizing,
database parameters, ALB/TLS configuration, connection-pool settings,
serving generation, and dataset identity.

## B2 — Run the frozen protocol

Identical to the performance-track protocol, which is the Stage 4
protocol: reference client on the owner's Windows machine, one reused
HTTP client, the same W2-dev prefixes cycled per mode, 48 requests per
mode at concurrency 4 (Stable), 12 (Peak), 4 (Shadow), 4 (Canary);
shadow publication uses the documented Stage 4 fixture preload
procedure (part of the frozen protocol, as in the Stage 4 continuation
and the performance-track rerun). Record per-request traces with
client, handler, and persistence timings; count errors, timeouts, and
fallback events explicitly. Zero-error is a finding to verify, not an
assumption.

## B3 — Report and record the decision

1. `docs/layered_latency_benchmark_report.md`: the freeze record, the
   protocol as run, per-mode per-layer p50/p95/p99 tables with sample
   counts, errors/timeouts/fallbacks, and the threshold comparison
   for every layer/mode — passes and failures alike.
2. `docs/performance_decision.md`: the compliance status per the
   taxonomy, naming every failed layer/mode if any. State explicitly
   that the original §9.3 client-visible 100 ms result remains FAILED
   in the historical record and that this decision is a separate,
   later record under amendment v2.
3. Add a short addendum to `docs/final_signoff.md` pointing to the
   benchmark report and the performance decision. Do not alter the
   signed Functional & Operational section or the original
   Performance Exception wording; the addendum records the new
   decision alongside them.
4. Full test suite against real PostgreSQL
   (`RANKFLOW_TEST_DATABASE_URL`): report passed / failed / skipped
   as three numbers.
5. **Teardown the cloud stack completely** and verify the empty
   state (stack, RDS and snapshots, ECS, ALB, S3, ECR), as in prior
   runs. Record the teardown evidence in the benchmark report.
6. Commit per phase (B1+B2 evidence, B3 records), English messages,
   and push to origin.

## Final message

The compliance status, the per-layer/per-mode pass-fail table, exact
test counts, teardown confirmation, and anything left open — stated
plainly.
