# Operational metrics

The authenticated /operator/metrics endpoint returns counters grouped by assigned
generation, cohort and source. Request counters cover ranked results on this
instance since startup, including results whose decisions could not be persisted.
Sum instance counters over a common collection interval with restart detection
for a fleet rate. Durable counters are shared and should be read once per store.

| Metric | Numerator | Denominator or unit |
| --- | --- | --- |
| Request volume | Ranked results | Count per process or delta per elapsed collection time |
| Fallback rate | Ranked results with fallback | All ranked results |
| Degraded logging rate | Ranked results without a committed decision | All ranked results |
| Confirmation rate | Closed committed impressions with an on-time confirmation | All committed impressions whose acknowledgement window has closed |
| Send state rates | Each recorded send state | All committed impressions |
| Outbox lag | Time since creation of oldest pending event | Seconds, null when no event is pending |
| Shadow divergence | Sum of one minus top-k overlap divided by requested k | Comparable persisted shadow observations |
| Gate and experiment | Signed decision outcomes and current experiment state | States |

An empty denominator yields an unknown rate. The guardrail uses the Stage 2
operational rules of two closed one-minute windows, at least 20 durable assigned
canary decisions per window and a fallback breach above 5%. Windows before
activation or below the sample minimum are unknown. Two consecutive unknown
or breached windows trigger the audited auto-pause. Guardrail health and
action status are separate fields.

The PostgreSQL-backed unknown and sustained-fallback drills passed (2 passed, 0 failed, 0 skipped). Both observed an auto_pause audit row and stable-only routing.

## Alert catalogue

| Alert | Action | Repository runbook |
| --- | --- | --- |
| `canary_unknown` | Pause | [Canary telemetry unknown](runbooks.md#canary-telemetry-unknown) |
| `canary_fallback` | Pause | [Canary fallback](runbooks.md#canary-fallback) |
| `canary_pause_failed` | Page | [Pause failed](runbooks.md#pause-failed) |
| `fleet_stale` | Rollback | [Stale fleet](runbooks.md#stale-fleet) |
| `logging_degraded` | Page | [Logging degraded](runbooks.md#logging-degraded) |
| `outbox_retry` | Page | [Outbox retry](runbooks.md#outbox-retry) |
