# RankFlow §9.3 performance decision

**Not Compliant** under the owner-approved §9.3 amendment v2. This is a separate, later record under amendment v2. The original §9.3 client-visible p95 target of 100 ms remains **FAILED** in the historical record. [Stage 4 verdict](stage4_latency_verdict.md) · [Performance-track verdict](perf_track_latency_verdict.md)

**Measurement Definition.** Handler and Persistence percentiles use the amendment v2 boundaries as implemented in `b45393e`. Handler runs from entry to the ASGI middleware through the final response-body send. Persistence runs from psycopg BEGIN dispatch on the acquired connection through COMMIT acknowledgement, excluding pool wait and post-commit logging. Stage 4 and the performance track used different Handler and Persistence timing definitions. Client-visible latency retains the original definition, from request issuance through full response receipt.

| Mode | Client-visible | Handler | Persistence |
| --- | --- | --- | --- |
| Stable | Pass | Fail | Fail |
| Peak | Fail | Fail | Fail |
| Shadow | Pass | Fail | Fail |
| Canary | Pass | Pass | Fail |

The following layer and mode thresholds failed.

- Stable Handler p95 was 104.334 ms against a 100 ms limit.
- Stable Persistence p95 was 64.545 ms against a 50 ms limit.
- Peak Client-visible p95 was 489.335 ms against a 400 ms limit.
- Peak Handler p95 was 387.078 ms against a 100 ms limit.
- Peak Persistence p95 was 98.511 ms against a 50 ms limit.
- Shadow Handler p95 was 171.526 ms against a 100 ms limit.
- Shadow Persistence p95 was 94.302 ms against a 50 ms limit.
- Canary Persistence p95 was 69.612 ms against a 50 ms limit.

[Benchmark report](layered_latency_benchmark_report.md)
