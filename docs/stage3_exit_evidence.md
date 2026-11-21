# Stage 3 exit evidence

This continuation covers the local Operated Release drills. The rejected W2-gate decision was preserved and W3 remained sealed. The release probes used a labeled rule-strategy fixture.

## Final acceptance run

`python -m unittest discover -s tests -v` ran the entire Stages 0–3 suite with
`RANKFLOW_TEST_DATABASE_URL` connected to PostgreSQL 16.10. The result was
**49 passed, 0 failed, 0 skipped** in **71.539 s**. The earlier runs exposed
subprocess startup timeouts on the Windows host. The final run used a
lightweight scorer fixture, a longer bounded wait for the transaction worker
to reach its checkpoint, and one thread per numerical library. The fault
assertions and production deadlines stayed at their original values.

## 3.1 Telemetry and operator actions

| Drill | Expected | Observed |
| --- | --- | --- |
| Request telemetry | Ranking, persistence and delivery events correlate by request ID. Metrics retain their generation, cohort and source dimensions. | Recommendation traces and outbox records carried the same request ID. The operator metrics endpoint exposes the denominators and the confirmation and send metrics documented in [operational metrics](operational_metrics.md). |
| Missing canary telemetry | Health becomes unknown and sustained unknown pauses progression. | `test_unknown_canary_telemetry_auto_pauses` observed the `canary_unknown` pause at revision 2. |
| Elevated fallback | Sustained canary fallback pauses progression. | `test_sustained_canary_fallback_pauses` observed a synthetic-operational pause at revision 2. |
| Alert action and runbook binding | Each alert specifies an operator action with a runbook anchor. | The catalogue binds unknown and fallback to pause, stale fleet to rollback, and pause failure, logging degradation and outbox retry to page. The console renders the associated runbook sections. |

## 3.2 Three-instance release

The [recorded probes](stage3_release_evidence.json) sampled each instance directly using a 0.25 s configured poll interval and a 0.05 s probe-loop sleep. Times below are the first serving-ready observation at the target revision, measured in seconds from each phase start.

| Drill | Expected | Observed |
| --- | --- | --- |
| Stable startup | Initial fleet serves revision 0. | Nodes 0 and 1 reached it at 16.203 s and 16.094 s. |
| Shadowing publication | Initial fleet converges on revision 1. | Nodes 0 and 1 reached it at 0.312 s and 0.203 s. |
| Canary activation and unprepared node | Prepared nodes serve revision 2. The late unprepared node is live with both readiness signals down and is excluded from canary routing. | Nodes 0 and 1 reached it at 0.359 s and 0.422 s. Routing targeted only those nodes. After staging the missing artifact, all three served revision 2 within 25.734 s of the catch-up probe phase. |
| Named rollback | All three serve the named stable-only snapshot and the rollback is audited. | Revision 3 converged in 0.390 s. The audit preserves the exact target config ID. |
| Kill switch | All three converge on stable serving and record the kill. | Revision 4 converged in 0.531 s with a matching kill audit row. |
| Stale fleet | Report the stale instance and enter rescue if rollback itself fails to converge. | `test_failed_rollback_convergence_activates_rescue_and_freezes_release` emitted `fleet_stale` with the missing instance and named rollback target, selected rescue and froze releases. |

The maximum observed publication convergence bound was **0.531 s** for the active fleets in the shadowing, canary, rollback and kill phases. The separate late-node catch-up took **25.734 s** from the start of probing after staging the artifact.

## 3.3 Isolation and latency

| Drill | Expected | Observed |
| --- | --- | --- |
| Hung or crashing scorer | An isolated failure yields a rule result with the original strategy assignment and a recorded fallback reason. | The fault tests returned rule rankings with `logical_deadline` and `ml_scoring_error` within the drill's one-second ceiling. |
| Artifact activation | Verify the checksums before atomically activating a local content-addressed copy. | A missing model and a corrupt model were rejected. The complete verified copy activated. |
| Shadow saturation | Shed shadow work at capacity and keep foreground ranking available. | 19 of 48 attempts completed and 29 were shed. The foreground run recorded zero HTTP errors. |

The [recorded Alpha benchmark](stage3_latency_evidence.json) ran 48 requests per mode with zero HTTP errors per mode. It captured these p95 values and peak API-process resident memory.

| Mode | Concurrency | Client p95 (ms) | Retrieval p95 (ms) | Feature p95 (ms) | Scoring p95 (ms) | Peak RSS (bytes) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stable | 4 | 145.230 | 1.163 | 1.216 | 0.529 | 424,099,840 |
| Peak | 12 | 270.446 | 1.366 | 0.971 | 0.343 | 426,749,952 |
| Synthetic shadow | 4 | 143.924 | 0.510 | 1.134 | 0.470 | 426,278,912 |
| Canary fixture | 4 | 91.985 | 0.912 | 1.515 | 0.279 | 426,328,064 |

Shadow minus stable measured −1.306 ms in client p95 and +2,179,072 bytes in peak RSS. With 29 shadow tasks shed, this measures the bounded shadow configuration in the recorded run. The cold verified cache took 8,245.515 ms. The artifact sizes ranged from 655 bytes for the evaluation epoch JSON to 97,005,269 bytes for covisitation, with the 92,970-byte model and remaining file sizes listed in the benchmark. Against the SPEC §9.3 100 ms client p95 target, stable, peak and shadow missed the target and the canary fixture was below it. The archived benchmark does not identify the hardware.

## 3.4 Fault injection

The [fault drill record](stage3_fault_evidence.md) lists expected and observed outcomes for event-DB failure and recovery, startup control-DB failure, transaction and outbox crashes, duplicate redelivery, corrupt and partial artifacts, scorer hang and crash, in-flight publication, clock skew and late acknowledgement, same-millisecond events, and concurrent publication.

## 3.5 and 3.6 evidence

- [Security and privacy](stage3_security_evidence.md) records role and route enforcement, rejection counts on sealed surfaces, CSRF, bearer handling, throttling and size limits, key separation, signed operations, retention, and hygiene scans.
- [Backup and restore](stage3_restore_evidence.md) records the source checkpoint, verified restored state, signed audit and stable recommendation probe, and measured RPO and RTO.

## Stage 3 kickoff test mapping

The kickoff and Addendum v3.0.4 assign different scenarios to some of the same IDs. This table follows the requested kickoff scenarios. See [open questions](open_questions.md) for the reconciliation.

| Kickoff ID | Scenario | Evidence |
| --- | --- | --- |
| T01 | Kill/restart during a decision and crash/redelivery of outbox | `test_kill_mid_write_then_outbox_crash_and_redelivery` checks zero partial rows and one effective delivery. |
| T16 | Named rollback and kill switch | 3.2 probes and audit rows for revisions 3 and 4. |
| T19 | Corrupt and partial artifacts | `test_partial_and_corrupt_artifact_never_activate`. |
| T20 | Publication during an in-flight request | `test_http_request_keeps_pin_during_publish` checks revisions 0 and 1. |
| T21 | Same-millisecond query identity | `test_same_millisecond_query_identity_survives_delivery` checks three distinct identities and ordered prefix lengths. |
| T22 | Late acknowledgement preserves a finalized cohort | `test_clock_skew_and_late_ack_leave_closed_metrics_unchanged` checks deduplication and unchanged closed counts. |
| T23 | Concurrent CAS publishers | `test_concurrent_publish_loser_retries_at_winning_revision` checks a single CAS winner and the loser's successful retry. |

The local continuation does not close the reference-deployment discrepancy recorded in open questions. The latency miss remains an open SPEC exit item.
