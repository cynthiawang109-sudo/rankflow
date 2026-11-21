# RankFlow final sign-off

Prepared for the owner's signature following the Stage 4 Conditional
Acceptance ruling of 2026-11-21.

## Functional & Operational Complete

The functional and operational acceptance basis is the Stage 0–4 evidence
and the closure sprint results below. Signed by the owner on 2026-11-21.

| Basis | Evidence |
| --- | --- |
| Stage 0 data quality and reproducible windows | [Stage 0 data quality report](stage0_data_quality_report.md) |
| Stage 1 stable retrieval, ranking and decision capture | [Stage 1 exit evidence](stage1_exit_evidence.md) |
| Stage 2 release and evaluation governance | [Stage 2 exit evidence](stage2_exit_evidence.md) |
| Stage 3 reliability, security and recovery | [Stage 3 exit evidence](stage3_exit_evidence.md) |
| Stage 4 reference deployment, reliability and teardown | [Stage 4 exit evidence](stage4_exit_evidence.md), [teardown record](stage4_teardown_evidence.json) |
| C1 · T07 closed | [Incompatible replay isolation](closure_t07_evidence.md) |
| C2 · SPEC section 14 demo closed | [Drift detection and recovery](closure_drift_evidence.md) |
| C3 · Artifact archive and independent replay closed | [Artifact manifest](artifact_manifest.md), [independent W2-dev replay](closure_replay_evidence.md) |

### C4 acceptance re-run

The full suite ran with `RANKFLOW_TEST_DATABASE_URL` set to disposable
local PostgreSQL 16.16 from the pinned `postgres:16` image digest
`sha256:23fdb7b8156ad34bc663ed911f360764c5a5e237d6d70d1e379e025f63439a2f`.
The command was `uv run --locked --offline python -m unittest discover -s tests -v`.
The run finished at `2026-11-21T14:20:33.0447815Z` and exited 0.

| Passed | Failed | Skipped |
| ---: | ---: | ---: |
| 58 | 0 | 0 |

**Owner signature (Functional & Operational Complete)** Cynthia

**Date** 2026-11-21

## Performance SLO Compliant — NOT signed.

**Performance Exception.** SPEC section 9.3 remains missed. Cloud client
p95 was **265–572 ms** against the **100 ms** target. PostgreSQL persistence
dominates in-handler latency. A separate registered performance track owns
this exception. [Stage 4 latency verdict](stage4_latency_verdict.md)

## Release disposition

`rule-v1` stable. The Stage 2 rejection of `lgbm-v1` stands.
Acceptance of the release system is not a model promotion.
[Signed Stage 2 release decision](stage2_release_decision.md)

## Addendum — §9.3 amendment v2 performance decision

The formal amendment v2 benchmark recorded **Not Compliant**. This later decision sits alongside the original Performance Exception. [Benchmark report](layered_latency_benchmark_report.md) · [Performance decision](performance_decision.md)
