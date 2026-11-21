# RankFlow — §9.3 Instrumentation Alignment (Codex kickoff)

## Authorization

Owner decision, 2026-11-21: **APPROVED — MEASUREMENT CORRECTNESS FIX
ONLY.** This is not a performance optimization and does not reopen one.
The frozen §9.3 layered latency contract
(`docs/spec_section_9_3_amendment_v2.md`) and its thresholds are
unchanged. The previous benchmark attempt is recorded as
**Not Verified — instrumentation mismatch**; that record stands.

This run has two phases with a hard gate between them. **Phase 1 only
is authorized in this run. STOP after Phase 1.** The cloud benchmark
(Phase 2) starts only after independent verification of the new
instrumentation, under a separate launch.

## Phase 1 — Align the instrumentation to the frozen definitions

### Handler latency — required boundary

Frozen definition: **Application Request Entry → Response Completion.**

- The span must cover the complete application processing of the
  request: routing, retrieval, feature construction, scoring,
  synchronous persistence, and **response construction and send**.
- Implement at the ASGI level (middleware that starts the span when
  the request enters the application and ends it when the final
  response body event has been sent). Moving the timer to the first
  line of the route function does not satisfy this boundary.
- The span must be recorded for successful and failed requests alike.

### Persistence latency — required boundary

Frozen definition: **Transaction Entry → Durable Commit
Confirmation.**

- Start the span when the database transaction actually begins —
  after a connection has been acquired from the pool. **Connection
  pool wait is outside the span.**
- Stop the span at durable commit acknowledgement. **Post-commit
  logging and any other post-commit work are outside the span.**
- Determine the exact start/stop points from the actual transaction
  lifecycle of the driver in use (psycopg 3), not by nudging the
  existing timer a few lines. Never end the span before the commit is
  acknowledged, and never move the commit outside the span.

### Prohibited in this run

- No SQL changes. No transaction-behaviour changes. No connection
  pool configuration or behaviour changes. No retry changes.
- No application performance optimization of any kind.
- No changes to frozen thresholds, benchmark protocol, load,
  concurrency, warm-up, or client.
- No redefinition of the measurement contract to match the code.

### Required tests

Add measurement-correctness tests covering:

- the normal path (spans recorded with the new boundaries);
- the error path (handler span still recorded when request handling
  raises);
- the transaction rollback path (persistence span behaviour on
  rollback is defined and asserted — no commit acknowledgement is
  implied by a rolled-back span);
- boundary exclusion proofs where the mechanics allow: e.g. a
  deliberately delayed post-commit logging step must not extend the
  persistence span; a delayed pool acquisition must not extend it
  either.

### Validation and evidence

1. Full test suite against real PostgreSQL
   (`RANKFLOW_TEST_DATABASE_URL`): report passed / failed / skipped
   as three numbers. **Zero skipped is required.**
2. `docs/instrumentation_alignment.md`:
   - the old boundary definitions and the new ones, side by side,
     with code references;
   - an explicit statement of the **Measurement Definition** change:
     Handler and Persistence percentiles measured after this fix are
     a different interval from the Stage 4 / performance-track
     percentiles and must not be presented as performance improvement
     or regression against them; historical results keep their
     original definition label;
   - confirmation, with the diff as evidence, that no SQL,
     transaction, pool, or execution behaviour changed — only
     instrumentation boundaries and tests;
   - confirmation that persistence atomicity and
     commit-before-attribution behaviour are unchanged (the existing
     tests are the evidence).
3. Commit the fix, tests, and evidence document (English message),
   and push to origin.

## STOP

End the run after the Phase 1 commit and push. Do not deploy anything
to AWS. The final message states: the new boundary definitions as
implemented (with code references), the correctness tests added, the
exact full-suite counts, and confirmation that no behaviour changed.
