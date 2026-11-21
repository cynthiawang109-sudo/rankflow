# RankFlow — Codex Kickoff: Stage 3 Continuation (3.5 + 3.6 + exit evidence only)

**Repository:** `C:\PROJECTS\rankflow`
**Context:** Stage 3 packages 3.1–3.4 are complete and committed (telemetry/alerts, three-instance convergence, inference isolation, fault drills). The earlier run stopped on an account usage limit — not a code failure. This continuation covers ONLY the remaining work below. Governing documents: `SPEC.md` (v3.0, FROZEN), `ADDENDUM.md` (v3.0.4), and `CODEX_KICKOFF_STAGE3.md` for the full package definitions — follow its 3.5/3.6 text exactly.

**Language:** All code, comments, docs, and commit messages in English.

## Remaining work (commit each separately)

### 3.5 Security and privacy pass (per CODEX_KICKOFF_STAGE3.md §3.5)

Role-boundary tests on every route (public/viewer/operator/admin, incl. W2-gate/W3 surfaces rejected-and-counted), CSRF on cookie-authenticated mutations, admin bearer handling, rate/size limits, pseudonymisation key separation, retention/deletion drill for pseudonymous records, secret/dependency hygiene scan evidence.

### 3.6 Backup and restore (per CODEX_KICKOFF_STAGE3.md §3.6)

PostgreSQL backup of control-plane state, restore into a clean environment, verify the restored system serves the stable generation and audit signatures verify; record measured RPO/RTO.

### Final acceptance run + exit evidence

- Run the FULL test suite (Stages 0–3) with `RANKFLOW_TEST_DATABASE_URL` configured against a real PostgreSQL. The summary in the result file must state passed / failed / skipped counts explicitly; skipped DB tests count as incomplete.
- Write `docs/stage3_exit_evidence.md`: every drill from 3.1–3.6 with expected vs observed outcomes, the measured multi-instance config-convergence bound, the latency/resource report from 3.3, and the Stage 3 test mapping (T01, T16, T19, T20, T21, T22, T23) with where each is evidenced.
- Write the concise summary to `codex_stage3_result.txt` in the repo root.

## Hard constraints (unchanged)

No W2-gate re-runs, no new model candidates, W3 sealed, no Kafka/Kubernetes/MLflow/LLM. Never fabricate metrics; every number from a recorded run or drill.
