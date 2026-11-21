# RankFlow §9.3 layered latency benchmark

**Decision.** Not Compliant. [Performance decision](performance_decision.md)

**Measurement Definition.** Handler and Persistence percentiles use the amendment v2 boundaries as implemented in `b45393e`. Handler runs from entry to the ASGI middleware through the final response-body send. Persistence runs from psycopg BEGIN dispatch on the acquired connection through COMMIT acknowledgement, excluding pool wait and post-commit logging. Stage 4 and the performance track used different Handler and Persistence timing definitions. Client-visible latency retains the original definition, from request issuance through full response receipt.

## Freeze record

- Amendment v2.0 was approved by Cynthia, project owner on 2026-11-21. The environment and protocol record was captured at `2026-11-21T18:37:51.146979+00:00`. [Frozen amendment](spec_section_9_3_amendment_v2.md) · [Freeze evidence](layered_latency_freeze.json)
- Build `297e1995c352f9fa144811a5eecaa827c41cdaa1` from `main`. SPEC.md SHA-256 `3a12ef37056e5094fb948bf8773e360f87dc35c128a30ce7a394e5482eb728db`. ECR tag `stage4-v1` resolved to `sha256:654c8f6f83d3222169b2b82aceb52388e0d4f25f07a627642b623ed334d8a16e`. Both running tasks reported `sha256:654c8f6f83d3222169b2b82aceb52388e0d4f25f07a627642b623ed334d8a16e`.
- CloudFormation `RankFlowStage4` in `ca-central-1`, with two Linux Fargate API tasks at 0.5 vCPU and 2 GiB each. The freeze record identifies the service, task definition, tasks and availability zones.
- Private, single-AZ RDS `rankflowstage4-databaseb269d8bb-nzwl1fbqqatm`, PostgreSQL 16.13 on `db.t4g.micro` with 20 GiB encrypted gp3 storage (3000 IOPS, 125 MiB/s), one day of backup retention and `default.postgres16`. Parameter-group values or defaults recorded for `fsync=1`, `full_page_writes=1`, `max_connections=LEAST({DBInstanceClassMemory/9531392},5000)`, `shared_buffers={DBInstanceClassMemory/32768}`, `synchronous_commit=on`. The app uses PostgreSQL `sslmode=require`.
- Each task uses a decision pool with 4–12 connections, a 2 s checkout timeout, a 2 s connect timeout and up to 40 queued waiters. The connection options set a 2,000 ms statement timeout and 1,500 ms lock timeout.
- Internet-facing ALB `RankFl-Alb16-FjoHdZtg4frh-206879057.ca-central-1.elb.amazonaws.com` with HTTPS on port 443, `ELBSecurityPolicy-TLS13-1-2-Res-2021-06` and a Stage 4 short-lived imported certificate with the ALB DNS name in its SAN. The Windows client explicitly trusted that certificate. The listener allowed the reference client's public IPv4 /32 and served two healthy targets.
- OTTO offline dataset source SHA-256 `06716132f1ab1d500f1515ba2c16187d7b0e98066ca66d33b95f022f8c3a340d`, retrieval snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`, and 12 ordered W2-dev prefixes. The freeze record includes the manifest, evaluation epoch and prefix checksums.
- Stable generation `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65`. Rule-only synthetic routing fixture `gen-00ec1133225940fe9144b65e66cceed2fe7c021db1a3d5356740c588dc62c02b`.

## Protocol and samples

One invocation of the existing Stage 4 probe with the fixture preload enabled ran on Cynthia's Windows reference machine (Intel Core i7-10510U, 8 logical processors, Python 3.11.18, httpx 0.28.1). The probe reused one HTTP client across all modes with a 15 s request timeout. Readiness and fleet convergence were sampled before timing. The fresh stack started on stable revision 0. All timed attempts were retained, including outliers. Each 48-request batch started at the first W2-dev prefix and cycled in the same order. Stable and Peak used the frozen stable generation. Both tasks preloaded the shadow fixture before publication. Canary routed 100% to the prepared fixture. The probe ended with the named rollback to Stable. Warm-up consisted of readiness and convergence checks.

| Mode | Concurrency | Started (UTC) | Finished (UTC) |
| --- | ---: | --- | --- |
| Stable | 4 | 2026-11-21T18:38:15.176000+00:00 | 2026-11-21T18:38:16.243042+00:00 |
| Peak | 12 | 2026-11-21T18:38:16.247175+00:00 | 2026-11-21T18:38:17.379091+00:00 |
| Shadow | 4 | 2026-11-21T18:38:30.542057+00:00 | 2026-11-21T18:38:31.779417+00:00 |
| Canary | 4 | 2026-11-21T18:38:35.220957+00:00 | 2026-11-21T18:38:36.267000+00:00 |

CloudWatch Handler and Persistence events were joined to each client attempt by request ID. A usable Handler sample requires exactly one completed response span with the matching HTTP status. A usable Persistence sample requires exactly one acknowledged commit span for the matching impression. Client percentiles use successful full responses. Timeout counts are included in transport errors. Percentiles use nearest rank, with 48 samples giving ranks 24, 46 and 48. Threshold tests use unrounded values. [Request-level trace evidence](layered_latency_trace_evidence.json)

| Mode | Attempts | HTTP errors | Transport errors | Timeouts | Foreground fallbacks | Unknown fallback status | Nonpersisted or unknown |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable | 48 | 0 | 0 | 0 | 0 | 0 | 0 |
| Peak | 48 | 0 | 0 | 0 | 0 | 0 | 0 |
| Shadow | 48 | 0 | 0 | 0 | 0 | 0 | 0 |
| Canary | 48 | 0 | 0 | 0 | 0 | 0 | 0 |

Shadow logs contain 18 fixture ranking outcomes, 0 fixture ranking fallbacks and 0 explicit shadow failure or executor-close events. The other 30 Shadow requests had no fixture ranking outcome in the captured logs. All 48 foreground Shadow requests supplied all three required timings.

| Mode | Layer | Samples | p50 (ms) | p95 (ms) | p99 (ms) | p95 limit (ms) | Result |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| Stable | Client-visible | 48 | 81.978 | 131.588 | 189.693 | 250 | Pass |
| Stable | Handler | 48 | 20.170 | 104.334 | 114.072 | 100 | Fail |
| Stable | Persistence | 48 | 8.428 | 64.545 | 80.951 | 50 | Fail |
| Peak | Client-visible | 48 | 224.767 | 489.335 | 502.387 | 400 | Fail |
| Peak | Handler | 48 | 186.761 | 387.078 | 392.119 | 100 | Fail |
| Peak | Persistence | 48 | 17.074 | 98.511 | 171.725 | 50 | Fail |
| Shadow | Client-visible | 48 | 89.971 | 197.080 | 205.112 | 250 | Pass |
| Shadow | Handler | 48 | 18.526 | 171.526 | 185.878 | 100 | Fail |
| Shadow | Persistence | 48 | 9.568 | 94.302 | 96.739 | 50 | Fail |
| Canary | Client-visible | 48 | 92.135 | 115.869 | 186.047 | 250 | Pass |
| Canary | Handler | 48 | 20.323 | 83.416 | 163.960 | 100 | Pass |
| Canary | Persistence | 48 | 7.079 | 69.612 | 78.356 | 50 | Fail |

## PostgreSQL test suite

`RANKFLOW_TEST_DATABASE_URL` pointed to disposable PostgreSQL 16.16 (Debian 16.16-1.pgdg13+1). The command was `uv run --locked python -m unittest discover -s tests -v` and completed at `2026-11-21T18:26:37.8903311Z` with exit code 0.

| Passed | Failed | Skipped |
| ---: | ---: | ---: |
| 63 | 0 | 0 |

## Teardown

AWS verification at `2026-11-21T18:45:20.378549+00:00` recorded stack status `DELETE_COMPLETE` with 48 resources marked `DELETE_COMPLETE`. The cleanup removed 16 S3 object versions. Service API checks recorded `s3_bucket` (404), `rds_instance` (DBInstanceNotFound), `ecr_repository` (RepositoryNotFoundException), `load_balancer` (LoadBalancerNotFound), `log_group` (missing), `ecs_cluster` (missing), `target_group` (TargetGroupNotFound). The final inventory found 0 RDS snapshots and 0 retained automated backups for the deployment. ECS service and cluster checks found zero live tasks and the task definition was `INACTIVE`. The imported certificate was removed. [AWS teardown evidence](layered_latency_teardown_evidence.json)
