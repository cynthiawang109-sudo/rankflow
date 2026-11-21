# P1 persistence evidence

## Baseline before the change

The Windows client ran the Stage 3 loopback benchmark against a fresh
schema on PostgreSQL in Docker Desktop, using the Stage 4 stable bundle
and W2-dev prefix cycle. Each mode had 48 requests at concurrency
4, 12, 4, and 4 respectively. The existing recommendation outcome log
supplied the foreground persistence span. All 192 requests returned
HTTP 200. Local client totals are excluded from the SLO verdict.

The baseline foreground transaction opened one PostgreSQL connection,
issued three inserts and committed. Psycopg sent a separate BEGIN and
COMMIT, for five SQL request/response exchanges, in addition to the
connection handshake. A successful response also triggers a separate
send-state update after the response body is handed off. That update
opens its own connection and uses three exchanges (BEGIN, UPDATE,
COMMIT) outside the measured handler span. Synthetic shadow can also
write a background observation in its own transaction. Outbox draining
uses a separate worker and transaction.

Three sequential isolated runs of the original write statements on the
same PostgreSQL 16.16 instance produced these client-side wall times
(ms). The server had `synchronous_commit` and `fsync` on. The probe used
small JSON payloads to isolate the database exchanges from payload size
and ranking work. Its explicit BEGIN was timed separately and includes
psycopg's implicit BEGIN on the idle connection, so that column includes
an extra exchange compared with the handler.

| Run | Connect | BEGIN | Impression | Decision | Outbox | COMMIT | Close |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 22.485 | 3.008 | 2.675 | 2.639 | 2.516 | 4.888 | 0.198 |
| 2 | 23.441 | 2.628 | 2.803 | 2.311 | 2.110 | 4.297 | 0.166 |
| 3 | 25.226 | 2.862 | 2.114 | 2.550 | 1.816 | 4.034 | 0.428 |

## Change and crash behavior

Each configured API process opens a decision-writing pool with four
initial connections, a maximum of 12, a two-second acquisition timeout,
and at most 40 waiting clients. A warm checkout requires no new
connection. A data-modifying CTE passes the inserted impression ID to
the decision insert and the decision's impression ID to the outbox
insert. The foreground path uses three SQL exchanges (BEGIN, combined
insert, COMMIT) on a warm checkout. The API retains its existing
degraded response on persistence errors. Send-state writes, synthetic
shadow observations, and the outbox consumer retain their separate
transactions.

| Crash or failure point | Durable state and recovery |
| --- | --- |
| Before checkout, including pool exhaustion | The request has written no rows. An acquisition failure returns the existing degraded response without an impression ID. |
| During the combined insert or before COMMIT | PostgreSQL rolls back all three rows when the connection ends. A connection failure gives the caller no impression ID. The pool discards the failed connection. |
| COMMIT in flight and its acknowledgement is lost | PostgreSQL has either committed all three rows or none. The handler returns a degraded response without an impression ID if the commit call fails. It does not retry an ambiguous commit. A committed outbox record remains available for recovery. |
| After COMMIT succeeds and before the response is sent | The impression, decision, and outbox event survive. Send state starts at `send_unknown`. The worker can deliver the event after restart. |
| After the response body is handed off, before send observation commits | The same three rows survive, with send state potentially still `send_unknown`. Client acknowledgement and feedback can resolve the durable decision. |
| After send observation commits | The send-state observation also survives. |
| Before or after a separate shadow observation commits | The decision remains durable. The observation survives once its own transaction commits. |
| During outbox delivery | The sink insert and delivery marker commit together. An interruption before that commit leaves the event eligible for retry. |

## Local segment comparison

The first post-change replay overlapped the Docker image build. The
same P1 build was measured again after the image build finished. Both
post-change replays produced 48 persistence samples per mode, zero
HTTP errors, and zero degraded recommendations. The after-build
replay was also completed before starting the full suite.

| Mode | Concurrency | Pre-change persistence p95 (ms) | During-build pooled p95 (ms) | After-build pooled p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Stable | 4 | 101.707 | 105.663 | 32.164 |
| Peak | 12 | 270.200 | 142.564 | 44.502 |
| Shadow | 4 | 104.318 | 81.234 | 35.548 |
| Canary fixture | 4 | 165.531 | 246.561 | 25.257 |

The two PostgreSQL pool fault tests passed in a targeted run. One
holds the only connection and verifies that the next request degrades
and that a subsequent request persists. The other terminates the
backend after the combined insert and before commit, verifies that
all three table counts remain unchanged, then persists through the
replacement connection. The existing subprocess atomicity checkpoint
now pauses after the combined insert and before commit.

P2 cloud measurement and P3 teardown are tracked separately. The local
comparison does not resolve section 9.3.
