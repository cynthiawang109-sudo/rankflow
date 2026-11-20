# Fault drill results

PostgreSQL-backed run of python -m unittest tests.test_stage3_faults -v.
Nine passed, zero failed, zero skipped.

| Scenario | Expected | Observed |
| --- | --- | --- |
| PostgreSQL connection failure at request time | Rule result, degraded logging, no attribution ID | Result was served without an impression ID and no partial decision. Persistence resumed when the connection fault was removed. |
| Startup control-plane failure | Designated rescue config serves stable with release readiness off | Recommendation identified the designated config. Readiness reported serving ready and release not ready. |
| Kill during decision transaction | No partial impression, decision or outbox record | All three counts were zero. The restarted path committed a complete decision. |
| Outbox consumer kill and redelivery | Roll back the uncommitted delivery and deliver exactly once effectively | Before restart the sink had zero rows and the outbox entry was pending. A duplicate redelivery left one sink row. |
| Missing and corrupt artifact | Neither can activate a cache entry | Missing model file and incorrect checksum were rejected. The complete verified copy subsequently activated. |
| Scorer subprocess hang and crash | Return on rule fallback and report the reason | Both attempts returned in less than the drill's one-second ceiling. The hang reported logical_deadline and the crash reported ml_scoring_error. |
| Publish during ranking | Keep the original request pin | The blocked request returned revision 0 and the next returned revision 1. |
| Clock skew and late acknowledgements | Reject future feedback and preserve closed cohort results | Feedback five minutes ahead was rejected. The duplicate late ack produced one late row and closed counts stayed at 0 of 1. |
| Same-millisecond events | Preserve ordered query identities through delivery | Three equal cutoff times produced three different request identities and impressions, and prefix lengths 1, 2 and 3 reached the sink. |
| Concurrent publication | One CAS winner and a retry at the new revision | Exactly one revision-1 commit. The other publisher refreshed and successfully retried at revision 1. |

The database connection failures use injected psycopg errors. Transaction and
scorer kills run in separate OS processes. All candidate inputs were fixtures.
