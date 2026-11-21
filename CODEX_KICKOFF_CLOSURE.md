# RankFlow — Final Closure Sprint (Codex kickoff)

## Status and mandate

Stage 4 has received **Conditional Acceptance** (owner ruling, 2026-11-21).
The engineering implementation is complete and independently verified
(55 tests passing against real PostgreSQL, AWS deployment and teardown
verified clean, cloud reliability drills passed, reproducibility package
delivered). Three coverage / reproducibility gaps remain open, plus one
performance non-compliance that is **out of scope for this sprint**.

This sprint closes exactly three gaps and prepares the final sign-off
record. Scope is strictly controlled: **no new architecture, no fifth
design round, no SPEC or ADDENDUM changes.** If any work package appears
to require an architecture change, STOP that package and report instead
of improvising.

Explicitly out of scope:

- Section 9.3 latency work of any kind (registered as a separate
  performance track; do not touch the request path).
- Any W3 access (it was opened once for the final report; it stays closed).
- Any W2-gate re-run, training, tuning, or model work. `lgbm-v1` remains
  REJECTED and `rule-v1` remains stable; nothing in this sprint changes
  release disposition.
- Any change to serving semantics, decision persistence, attribution, or
  audit guarantees.
- Cloud deployment: this sprint is local only. Leave no AWS resources
  running; do not create any.

## C1 — T07: incompatible feature-schema isolated replay

The loader currently rejects an incompatible bundle. That is a guard, not
the acceptance test. Prove the full isolation property:

1. Construct (or derive) a model bundle whose feature schema is
   incompatible with the stable generation's feature schema, clearly
   versioned as its own identity.
2. Attempt an isolated replay of historical events against that bundle.
3. Produce evidence that:
   - the attempt is rejected or quarantined and the failure is recorded
     with its reason (audit / evidence trail);
   - stable serving is unaffected before, during, and after the attempt:
     recommendations continue to persist on the stable generation and
     match the pre-attempt behaviour;
   - no inference results and no evaluation results are written under the
     incompatible bundle's identity (verify record counts / identities —
     no pollution of other versions' results);
   - all other versions' artifacts and records are unchanged.
4. Add automated tests covering these isolation properties.
5. Evidence: `docs/closure_t07_evidence.md`, and update the Addendum
   acceptance catalogue entry for T07 from open to closed with a link.

## C2 — Section 14: feature drift detection and alert demo

Prove the monitoring loop end to end, in both directions:

1. **No false positive:** run the drift monitor over normal historical
   feature distributions (the W2-dev distribution the system was
   evaluated on). Record that no drift alert is raised.
2. **Detection:** inject a pre-defined, controlled feature-distribution
   shift. Document exactly which feature(s) shift, how, and by how much,
   before running it.
3. Produce evidence that:
   - the monitor detects the injected shift;
   - a traceable alert is produced (alert identity, timestamps, the
     triggering measurements);
   - the alert is visible in the Operator Console (capture that evidence);
   - the detection and alert are written to the audit trail.
4. **Recovery:** remove the shift, re-run, and record that the alert
   recovers / clears according to the system's stated rule.
5. Automated tests where the mechanics allow, plus a scripted demo record:
   `docs/closure_drift_evidence.md`; update the acceptance catalogue
   entry for the section 14 demo from open to closed with a link.

## C3 — Checksum-pinned artifact archive and independent replay

1. Build an artifact manifest recording SHA-256 (plus size and
   provenance: what produced it, when, from what inputs) for:
   - the OTTO dataset snapshot files actually used;
   - the derived dataset snapshot / window artifacts (W1, W2-dev at
     minimum) or their deterministic regeneration identity;
   - the trained model artifacts (the stable `rule-v1` bundle and the
     archived `lgbm-v1` model);
   - the feature schema;
   - the stable TrafficConfig.
   Record it in `docs/artifact_manifest.md`. The dataset itself stays out
   of git; the manifest is the identity record that lets any holder of
   the same OTTO snapshot verify they have the same bytes.
2. **Independent replay:** from a clean environment (fresh checkout,
   empty database volume), using only the manifest and the archived
   artifacts, replay the W2-dev evaluation and verify the archived
   headline metrics and slice counts reproduce.
3. Evidence: `docs/closure_replay_evidence.md` (environment, commands,
   manifest hashes verified, metrics compared line by line).

## C4 — Final acceptance re-run and sign-off record

1. Run the full test suite against real PostgreSQL
   (`RANKFLOW_TEST_DATABASE_URL`). Report passed / failed / skipped as
   three separate numbers. Skipped does not count as passed.
2. Prepare `docs/final_signoff.md` for the owner's signature, recording
   two independent conclusions:
   - **Functional & Operational Complete** — basis: Stage 0–4 evidence
     plus C1–C3 of this sprint (T07 closed, section 14 demo closed,
     artifact archive and independent replay closed).
   - **Performance SLO Compliant — NOT signed.** Section 9.3 remains
     missed (cloud client p95 265–572 ms vs the 100 ms target;
     PostgreSQL persistence dominates in-handler latency). Recorded as a
     **Performance Exception**, handled by a separate registered track.
     Do not soften this wording.
   - Release disposition line: `rule-v1` stable; the Stage 2 rejection
     of `lgbm-v1` stands. Acceptance of the release system is not a
     model promotion.
3. Update `docs/stage4_exit_evidence.md` with a short addendum pointing
   to the closure evidence and the sign-off record (do not rewrite its
   existing findings).

## Working rules

- Commit per work package (C1, C2, C3, C4), English commit messages.
- Run scripts and logs used to drive this session are removed at the end,
  per repo convention.
- Final message: summarize per package what was proven, the evidence
  file for it, the exact test counts, and anything left open — stated
  plainly, never rounded up.
