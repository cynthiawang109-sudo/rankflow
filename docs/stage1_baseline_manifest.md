# Frozen Stage 1 baseline

The Stage 1 implementation is pinned at commit `3f658ef`. The owner accepted
Stage 1 on 2026-11-20. The [machine-readable manifest](stage1_baseline_manifest.json)
records SHA-256 checksums and the complete accepted test inventory. For the
combined query artifact, it carries forward the existing data-manifest checksum.

| Output | Frozen version and evidence |
|---|---|
| Data, windows, and queries | `stage0-v1`, epoch `stage0-initial`, label policy `nextclick-v1`. The JSON includes the window boundaries, query configuration, and the 50% validation gate split. |
| Retrieval | Recent 10, co-visitation 100, popularity 20, candidate cap 100. Snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`. [Ablation](stage1_retrieval_ablation.md) |
| Shared features | `session-features-v1`. The JSON records the feature order and feature-code hash. |
| Alpha strategy | `rule-v1`. The JSON records the rule configuration and digest, the Alpha generation, and its bundle manifests. |
| Candidate strategy | `lgbm-v1`, LightGBM 4.7.0. The JSON records the training configuration and model checksum. |
| Development evaluation | W2-dev candidate recall@100 22.33%. HitRate@20 and MRR@20 were 19.63% and 0.1340 for `rule-v1`, and 19.94% and 0.1425 for `lgbm-v1`. [Strategy report](stage1_strategy_report.md) |
| Playground and exit evidence | Browser smoke, API replay, and PostgreSQL durability evidence. The independent run passed 24 tests with 0 failures and 0 skips, including 14 Stage 0 tests. [Exit evidence](stage1_exit_evidence.md) |

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1%
of sessions with 21–100 events, and 4.6% of sessions with more than 100 events.
Headline metrics describe the retained OTTO population.

Later variants receive new immutable versions. Preserve this manifest and its
JSON companion as the Stage 1 acceptance record.
