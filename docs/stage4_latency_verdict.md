# Stage 4 latency verdict

**SPEC section 9.3 missed in every measured mode.** The client p95 budget
is 100 ms. The Addendum R29 retrieval, feature and scoring planning
allocations are met in all four modes.

## Protocol

The client was the local Windows host with an Intel Core i7-10510U and
8 logical processors. It called the ca-central-1 HTTPS ALB using the
same Stage 3 W2-dev prefix cycle, 48 requests per mode and concurrency
4 / 12 / 4 / 4. The Stage 3 nearest-rank p95 method was retained, and
nearest-rank p99 equals the sample maximum with 48 requests. There were
zero HTTP or transport errors in all four modes.

The deployed service used two Linux Fargate tasks, each with 0.5 vCPU and
2 GiB memory. Stable and peak used the frozen `rule-v1` bundle. Synthetic
shadow and canary used a labeled rule-only fixture with the same ranking
implementation. The canary fixture received all canary-mode requests, as
in Stage 3. These measurements include the public network, TLS, and ALB
from the Windows client. The Stage 3 run used loopback. The same ALB client
connection pool was shared across modes. Background cloud and repository
work ran during the session.

## Measurements

| Mode | Client p95 (ms) | Client p99 (ms) | Retrieval p95 (ms) | Feature p95 (ms) | Scoring p95 (ms) | Persistence p95 (ms) | Handler p95 (ms) | Outside handler p95 (ms) | 100 ms verdict |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Stable | 326.249 | 618.664 | 0.674 | 0.830 | 0.224 | 119.081 | 121.533 | 300.548 | Missed |
| Peak | 571.853 | 598.163 | 0.465 | 0.920 | 0.239 | 486.645 | 489.067 | 210.655 | Missed |
| Synthetic shadow | 332.881 | 379.918 | 0.846 | 0.845 | 0.238 | 263.530 | 269.365 | 124.720 | Missed |
| Canary fixture | 264.890 | 285.012 | 0.422 | 0.677 | 0.221 | 194.390 | 199.577 | 114.994 | Missed |

The [recorded samples](stage4_latency_evidence.json) include 48 matched
foreground ranking and persistence spans per mode. Persistence measures
the request-time PostgreSQL operation, including connection establishment,
statements and transaction completion. All four persistence p95 values
also exceeded the R29 10 ms planning allocation. Outside-handler time
is calculated for each request from client elapsed time minus the handler's
reported duration. It includes the network and ALB, connection setup when
applicable, middleware, scheduling and response handling. It does not
isolate any one of those costs. Percentiles from different segments describe
different samples.

Stable had the largest outside-handler tail and still exceeded 100 ms
inside the handler at p95. Persistence dominated the measured in-handler
time in every mode, with its largest tail at peak concurrency. It was
also the larger of the two measured boundaries for peak, synthetic shadow,
and the canary fixture. The three ranking stages stayed below 1 ms
at p95 individually. The measured persistence span does not identify the
respective contributions of database connection latency, server work and
commit.

## Task headroom

CloudWatch `AWS/ECS` service Maximum reports the highest observed task
utilization in each 60-second bucket. Stable, peak and synthetic shadow
share the 03:33 UTC bucket. The canary shares its 03:34 bucket with
subsequent rollback and task-loss activity. The short bursts cannot be
resolved independently by these samples. [AWS ECS utilization metrics](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/service_utilization.html)

| Modes in bucket | Max task CPU | CPU headroom | Max task memory | Memory headroom |
| --- | ---: | ---: | ---: | ---: |
| Stable, peak, shadow | 39.35% | 60.65% | 21.17% | 78.83% |
| Canary fixture | 47.97% | 52.03% | 21.19% | 78.81% |
