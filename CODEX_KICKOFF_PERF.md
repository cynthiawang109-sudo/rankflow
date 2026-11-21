# RankFlow — Performance Track: section 9.3 investigation (Codex kickoff)

## Mandate

Registered performance track from the Stage 4 Conditional Acceptance
(2026-11-21). Functional & Operational Complete is signed; the
**Performance SLO is not**. This track owns the section 9.3 exception:

- Target: client p95 <= 100 ms (SPEC section 9.3), measured under the
  Stage 4 latency protocol (client on the owner's Windows machine,
  AWS ca-central-1 reference deployment, four modes: stable, peak,
  shadow, canary).
- Current verdict (`docs/stage4_latency_verdict.md`): p95 stable 326,
  peak 572, shadow 333, canary 265 ms. Retrieval / features / scoring
  segments are each < 1 ms. The bottleneck is request-time PostgreSQL
  persistence (p95 119–487 ms, including per-request connection
  establishment), plus 115–300 ms of client network / TLS path outside
  the handler.

## Frozen constraint (non-negotiable)

Decision persistence semantics are part of the product contract: a
recommendation decision and its outbox record are committed durably
before the result is attributable. No change may:

- return a result whose decision record exists only in memory or in a
  volatile queue;
- weaken attribution, audit, or recovery guarantees;
- trade correctness for the latency number.

For every change to the request path, state — in the evidence document —
what survives a crash at each point of the path. A design that cannot
answer that is rejected on that ground alone.

## Scope: one optimization pass, then measure

### P1 — Local diagnosis and fix

1. Profile the persistence path of one recommendation request: count
   connections opened, statements, and round trips; record where the
   milliseconds go, using the in-handler segment timings the system
   already emits. Evidence before changes, not after.
2. Implement the fix candidates that respect the frozen constraint.
   Expected prime suspect: per-request connection establishment —
   introduce application-level connection pooling. Also evaluate
   round-trip consolidation inside the same transactions. Writes that
   are genuinely outside the decision/attribution contract (pure
   telemetry) may move behind the existing durable outbox; the decision
   record itself stays synchronous and durable.
3. Prove semantics intact: the existing atomicity / outbox / recovery
   tests stay green; add tests for pool behaviour under failure (pool
   exhaustion, connection drop mid-request) where the mechanics allow.
4. Measure locally with the same segment protocol and report the
   persistence segment before vs after. Local client totals on this
   machine are not the verdict (Stage 3/4 records show local process
   overhead pollutes them); the segment numbers are the signal.
5. Commit P1 separately.

### P2 — Representative cloud verification

1. Redeploy the reference stack exactly as in Stage 4 (Fargate
   0.5 vCPU / 2 GiB, >= 2 API tasks, ALB, RDS, ca-central-1), with the
   P1 build.
2. Re-run the Stage 4 latency protocol unchanged: same client, same
   four modes, same measurement separation (client total vs in-handler
   segments).
3. Record the verdict in `docs/perf_track_latency_verdict.md`:
   per-mode p95 vs the 100 ms target, segment table, protocol
   conditions. Honest numbers only — a miss is recorded as a miss.
4. Commit P2 separately.

### P3 — Close-out

- If section 9.3 is met: prepare an addendum to
  `docs/final_signoff.md` recording **Performance SLO Compliant** as
  ready for the owner's signature (basis: P1 evidence + P2 verdict).
  Do not sign it yourself.
- If it is still missed: STOP. Do not start a second tuning loop.
  Write `docs/perf_track_outcome.md` with the measured improvement,
  the remaining gap decomposed (persistence segment vs client network
  path), and the options for the owner's decision: (a) accept the
  Performance Exception as permanent for this portfolio release,
  (b) a formal target-change proposal with reasoning, or (c) a larger
  redesign as a separate future decision.
- **Teardown: delete the cloud stack completely at the end of this
  run, whatever the outcome** (the owner does not leave stacks billing
  idle). Verify and record the empty state, as in Stage 4.
- Full test suite against real PostgreSQL
  (`RANKFLOW_TEST_DATABASE_URL`): report passed / failed / skipped as
  three numbers.

## Hard boundaries

- No model, training, gate, or W3 work. `rule-v1` stays stable;
  `lgbm-v1` stays rejected.
- No SPEC or ADDENDUM edits. A target change is a proposal document
  for the owner, never an edit.
- No serving-semantics changes beyond the persistence-path work above.
- Commit per phase (P1, P2, P3) so partial progress survives an
  interruption; if the session is cut off, the evidence written so
  far must state plainly what is done and what is not.
- Final message: per-phase results, the verdict numbers, the exact
  test counts, teardown confirmation, and anything left open.
