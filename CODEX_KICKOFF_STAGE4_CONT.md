# RankFlow — Codex Kickoff: Stage 4 Continuation (4.3 + 4.5 + 4.6 + exit evidence)

**Repository:** `C:\PROJECTS\rankflow`
**Context:** Stage 4 packages 4.1 (AWS reference deployment), 4.4 (W3 final report), and 4.2 (latency verdict: SPEC §9.3 missed in all modes; persistence segment is the bottleneck) are complete and committed. The earlier run stopped on an account usage limit — not a code failure. Governing documents: `SPEC.md` (v3.0, FROZEN), `ADDENDUM.md` (v3.0.4), and `CODEX_KICKOFF_STAGE4.md` for the full package definitions — follow its 4.3/4.5/4.6 text exactly.

**Language:** All code, comments, docs, and commit messages in English.

## First step: establish deployment state

Check whether the Stage 4 CDK stack still exists in ca-central-1.

- If it was torn down after the interruption: re-deploy it exactly as in 4.1 (same stack, same tags), re-verify the ALB serves the stable generation, and note the re-deployment in the deployment doc.
- If it is still running: verify its health and proceed; note the idle period in the cost record.

## Remaining work (commit each separately)

### 4.3 Reliability re-check on the deployment (per CODEX_KICKOFF_STAGE4.md §4.3)

Kill one API task mid-traffic, publish + named rollback behind the ALB, restore the database from an RDS snapshot once and verify the restored system serves the stable generation. Record expected vs observed.

### 4.5 Reproducibility and product completeness pack (per §4.5)

Clean-room reproduction from docs alone (training checksum vs Stage 2 lineage, W2-dev evaluation, local deployment serving stable), reproduction log with doc gaps fixed, finalised README / product contract / runbooks / evidence index, remaining ADDENDUM acceptance tests assigned and evidenced.

### 4.6 Teardown and cost record (per §4.6)

Tear down the CDK stack, verify no billable resources remain (list what was checked), record actual AWS cost or resource-hours in `docs/stage4_deployment.md`. Then: full test suite with `RANKFLOW_TEST_DATABASE_URL` against real PostgreSQL (passed / failed / skipped stated explicitly; skipped DB tests = incomplete), `docs/stage4_exit_evidence.md`, and the summary in `codex_stage4_result.txt` including the one-line latency verdict.

## Hard constraints (unchanged)

W3 stays closed (the single opening is recorded; do not re-run W3 evaluation). No gate re-runs, no new candidates, no tuning prompted by the latency verdict or W3 results. Never fabricate numbers. Never leave the stack running at the end of this run.
