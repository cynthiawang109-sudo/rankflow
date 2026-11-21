# Performance track cloud latency verdict

**SPEC section 9.3 missed in all four modes.** Client p95 fell by
149.951 ms in stable, 243.054 ms in peak, 199.600 ms in shadow, and
155.266 ms in canary compared with the Stage 4 verdict.

## Protocol

The run used the Stage 4 Windows host with an Intel Core i7-10510U
and eight logical processors. The `ca-central-1` deployment used
an HTTPS ALB, a private PostgreSQL 16.13 RDS `db.t4g.micro`, and two
Linux Fargate tasks with 0.5 vCPU and 2 GiB per task. Both tasks ran
P1 commit `5dc6617` through image digest
`sha256:dbb16a4d94375f48895cd1ab8c7dc3d80644b56f4144623b8d3575e807de1dd9`.

One HTTP client was reused across the complete run. Each mode cycled
the same W2-dev prefixes for 48 requests at concurrency 4, 12, 4,
and 4 respectively. Stable and peak used the frozen serving bundle.
Synthetic shadow and 100% canary used the Stage 4 routing fixture.
All 192 foreground recommendations used `rule-v1` and persisted
successfully. There were zero HTTP or transport errors and 48 matched
foreground ranking and persistence spans per mode.

The first attempt measured stable at 155.933 ms p95 and peak at
401.124 ms p95. The fleet automatically rolled back the initial
shadow publication before both tasks acknowledged it, so that attempt
produced no shadow or canary latency sample. The full retry started
from the converged stable rollback revision. After rerunning stable
and peak, it used the documented Stage 4 fixture preload before
publishing shadow. The same build, four timed request batches, and
percentile method were used. [Stage 4 deployment and continuation](stage4_deployment.md)

The probe's latency-only option ends after the named rollback.
It preserves the Stage 4 latency measurement sequence and omits the
subsequent task-loss drill.

## Measurements

| Mode | Stage 4 client p95 (ms) | P1 client p95 (ms) | P1 client p99 (ms) | Over 100 ms by | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| Stable | 326.249 | 176.298 | 196.868 | 76.298 ms | Missed |
| Peak | 571.853 | 328.799 | 395.497 | 228.799 ms | Missed |
| Synthetic shadow | 332.881 | 133.281 | 186.465 | 33.281 ms | Missed |
| Canary fixture | 264.890 | 109.624 | 161.954 | 9.624 ms | Missed |

| Mode | Retrieval p95 (ms) | Feature p95 (ms) | Scoring p95 (ms) | Persistence p95 (ms) | Handler p95 (ms) | Outside-handler p95 (ms) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable | 0.625 | 0.836 | 0.211 | 77.449 | 82.840 | 101.399 |
| Peak | 0.517 | 0.842 | 0.194 | 173.062 | 197.639 | 202.447 |
| Synthetic shadow | 0.510 | 0.841 | 0.246 | 67.396 | 81.151 | 96.201 |
| Canary fixture | 0.539 | 0.680 | 0.213 | 74.200 | 83.491 | 92.087 |

Client, handler, and segment percentiles use nearest rank. With 48
requests, p99 is the sample maximum. Outside-handler p95 comes from
subtracting handler time from client time for each request before
calculating the percentile. It includes the network, TLS when
applicable, ALB, middleware, scheduling, and response handling.
The percentiles in different columns can represent different requests.
[Performance track samples](perf_track_latency_evidence.json)
