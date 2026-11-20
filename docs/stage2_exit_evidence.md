# Stage 2 exit evidence

## Training and release decision

The [Stage 1 artifact manifest](stage1_baseline_manifest.md) pins the input
population, retrieval snapshot, candidate configuration, features and accepted
artifacts. The [Stage 2 training record](stage2_training_evidence.json) records
two complete W1 fits. Both produced the frozen model checksum, identical
canonical lineage and numerically identical W2-dev counts and segment metrics.
The absolute metric tolerance was zero. Wall-clock durations were excluded
from that comparison. [LambdaRank model card](lgbm-v1_model_card.md)

The operator registry recorded one W2-gate promotion comparison. A registered
slice exceeded the configured non-regression tolerance, resulting in
`rejected`. The gate used the kickoff's absolute 0.5 percentage-point
tolerance for both primary metrics and treated a slice regression beyond that
tolerance as blocking. `rule-v1` remains stable. The local signed registry
entry is available through the authenticated release history. The pinned
Stage 0 W3 population was never evaluated in this stage.
[Signed decision reference](stage2_release_decision.md)

The pointwise comparison used W1 for fitting and W2-dev for evaluation.
The predeclared rule retained LambdaRank. The later OTTO rehearsal registered
a separate epoch from the checksum-verified subsequent download partition and
recorded a development-only decision. The fixture test verified unchanged
ranking responses across epoch registration. The historical real-bundle replay
reproduced its aggregate before and after the later epoch registration.
[Pointwise report](stage2_pointwise_comparison.json) ·
[Later OTTO run](stage2_later_otto_evidence.json) ·
[Later OTTO model card](lgbm-otto-rehearsal-v1_model_card.md)

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1%
with 21–100 events, and 4.6% with more than 100 events. Headline metrics
describe the retained OTTO population.

## Serving and learning drills

Two API application instances shared a PostgreSQL control plane. Both
preloaded the registered candidate generation and agreed on the same
generation and returned ranking for each of 16 synthetic sessions. The
cohort split was 9 canary and 7 stable. Live shadow completed 36 comparisons.
Historical shadow replay used 1,000 W2-dev prefixes. Both instances observed
the kill operation at revision 3 and served stable-only responses afterwards.
The drill ran locally with two ASGI application instances. An external load
balancer's removal and propagation timing was outside this run.
[Serving event and traffic audit evidence](stage2_serving_evidence.json)

The demo rehearsal used four attributed synthetic clicks to create a versioned
demo dataset, fit a model and evaluate held-out demo sessions. Its signed
decision records demo provenance ineligibility for the OTTO gate.
[Demo model card](demo_lgbm_model_card.md)

## PostgreSQL-backed acceptance run

Ran `python -m unittest discover -v` at `a781776` with
`RANKFLOW_TEST_DATABASE_URL` pointing to a dedicated PostgreSQL 16.16
container. The complete suite returned **35 passed, 0 failed, 0 skipped**.
This includes all 24 accepted Stage 0 and Stage 1 tests.

| Kickoff scenario | Evidence |
|---|---|
| Weakened candidate denied | The fixture candidate used reversed rule scores. The paired gate decision rejected it. |
| T03 and T11 | Two leased instances preloaded both bundles. Concurrent publishes at one expected revision produced one commit. An in-flight snapshot and cohort assignments stayed consistent. |
| T04 and T10 | Live shadow preserved served output. The kill switch, named rollback, rescue freeze and incident resolution were checked with the database active. |
| T07 and T08 | Demo promotion failed before the real evaluator opened its input. Out-of-list feedback was absent from the rehearsal dataset. |
| T12 | Replaying outbox records resulted in one effective delivery per event. |
| T14 | Overlapping epochs were rejected and an older ranking replay stayed identical. |
| Read isolation and acknowledgements | Public W2-gate reads were denied. The operator route accepted the bearer and verified signatures. A duplicate late confirmation produced one late record and preserved the original confirmation status. |
| Operational guardrails | Unknown telemetry auto-paused the synthetic canary. The operator's reason and bounded override were persisted and expiry returned traffic to stable. |
