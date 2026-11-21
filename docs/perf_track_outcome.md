# Performance track outcome

The P1 build improved all four client p95 measurements on the Stage 4
reference deployment. All four still exceed the 100 ms target in SPEC
section 9.3. The Performance Exception remains open for the owner's
decision. The optimization pass ended after this cloud run.
[Cloud verdict and protocol](perf_track_latency_verdict.md)

| Mode | Client p95 improvement (ms) | Client p95 still over budget (ms) | Persistence p95, Stage 4 → P1 (ms) | Outside-handler p95, Stage 4 → P1 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Stable | 149.951 | 76.298 | 119.081 → 77.449 | 300.548 → 101.399 |
| Peak | 243.054 | 228.799 | 486.645 → 173.062 | 210.655 → 202.447 |
| Synthetic shadow | 199.600 | 33.281 | 263.530 → 67.396 | 124.720 → 96.201 |
| Canary fixture | 155.266 | 9.624 | 194.390 → 74.200 | 114.994 → 92.087 |

Persistence dominates the measured handler time and its peak p95
alone exceeds the full client budget. The outside-handler p95 alone
exceeds the budget in stable and peak, and leaves less than 8 ms of
the budget in shadow and canary. That segment includes the client
network and TLS path, ALB, middleware, scheduling, and response
handling. The protocol measures them together. Each percentile is
computed from its own sample distribution, so the columns cannot be
added to reconstruct the client p95 or assign exact causal savings.
The P1 local evidence details the synchronous commit and crash behavior.
[P1 persistence evidence](perf_track_persistence_evidence.md)

## Owner decision

1. Accept the Performance Exception as permanent for this portfolio
   release and record the observed client limits with the release.
2. Commission a formal target-change proposal. Use repeated runs of
   the same Windows-to-ALB protocol to establish a defensible
   client-visible budget and retain separate handler and persistence
   budgets. The measured outside-handler tail is the reason to
   evaluate the client budget separately.
3. Consider a larger redesign as a separate future decision. Its
   scope would need to address both peak persistence latency and the
   outside-handler path, while preserving synchronous durable decision
   and outbox commit before attribution.

## Test and teardown record

The full `uv run --locked python -m unittest discover -s tests -v`
suite ran with `RANKFLOW_TEST_DATABASE_URL` against PostgreSQL 16.16.
**60 passed, 0 failed, 0 skipped.**

CloudFormation marked the `ca-central-1` stack `DELETE_COMPLETE` at
16:19:25 UTC on 2026-11-21. All 48 stack resources reported
`DELETE_COMPLETE`. Service-level checks confirmed the absence of the
ALB, RDS instance, ECS cluster, ECR repository, S3 bundle bucket,
CloudWatch log group, and imported TLS certificate. The teardown
removed all 16 S3 object versions. No stack network interfaces, live
NAT gateways, stage elastic IPs, or retained automated backups
remained. The initial automated snapshot disappeared after stack
deletion. The final RDS follow-up at 16:20:29 UTC returned
`DBSnapshotNotFound` and an empty snapshot inventory for this database.
The task definition was inactive.
[AWS teardown evidence](perf_track_teardown_evidence.json)
