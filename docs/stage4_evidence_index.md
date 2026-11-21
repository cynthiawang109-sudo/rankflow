# Stage 4 evidence index

| SPEC section 12 Product Complete criterion | Evidence |
| --- | --- |
| Candidate-source and model ablation, including accuracy and latency tradeoffs | [Retrieval ablation](stage1_retrieval_ablation.md), [strategy comparison](stage1_strategy_report.md), [pointwise comparison](stage2_pointwise_comparison.json), and [reference latency verdict](stage4_latency_verdict.md). |
| Final independently evaluated W3 report | [Final evaluation report](final_evaluation_report.md). |
| Architecture, experiment matrix, cards, release history, load and faults | [Reference deployment](stage4_deployment.md), [architecture](architecture.md), [threat model](threat_model.md), [retrieval study](stage1_retrieval_ablation.md), [model card](lgbm-v1_model_card.md), [OTTO data report](data_validation_report_real.md), [release decision](stage2_release_decision.md), [local load and release evidence](stage3_exit_evidence.md), and [deployed drills](stage4_exit_evidence.md). |
| Operator Console and operational runbooks | [Product contract](product_contract.md), [metrics and denominators](operational_metrics.md), and [runbooks](runbooks.md). |
| Training lineage and subsequent training run | [Frozen baseline](stage1_baseline_manifest.md), [Stage 2 lineage](stage2_training_evidence.json), and [reproduction log](reproduction_log.md). |
| Reproduce a model evaluation | Repeat the W2-dev evaluation in the [reproduction log](reproduction_log.md). |
| Reproduce a promotion decision | Replay the recorded W2-gate disposition from signed historical aggregates using the [reproduction log](reproduction_log.md). |
| Reproduce rollback and incident recovery | Use the [operator runbooks](runbooks.md), [local release drill](../scripts/stage3_release.py), and [local restore drill](stage3_restore_evidence.md). |
| Demo recording and search-ranking translation | [Search-ranking translation](search_ranking_translation.md) and [recorded demo](stage4_demo.mp4). The recording combines a live Playground and feedback sequence with labeled excerpts from earlier fault and release drills. It does not cover a live feature-shift injection. |
| Real-user experiment statement | No real-user experiments took place. [Product contract](product_contract.md). |
| Addendum acceptance replay | [T01–T23 catalogue](stage4_acceptance_catalogue.md) and [final PostgreSQL run](stage4_exit_evidence.md). |
| Reference deployment cleanup | [Resource inventory and cost record](stage4_deployment.md). |

## Experiment matrix

| Experiment | Population or workload | Outcome and record |
| --- | --- | --- |
| Candidate source and depth ablations | W2-dev | Source combinations and top-N settings compared under the frozen candidate cap. [Retrieval ablation](stage1_retrieval_ablation.md) |
| Rule vs. LambdaRank | W1 fit, W2-dev evaluation | Shared candidate sets and features, with end-to-end ranking and retrieval coverage. [Strategy comparison](stage1_strategy_report.md) |
| Pairwise vs. pointwise | W1 fit, W2-dev evaluation | The predeclared criteria retained LambdaRank. [Pointwise comparison](stage2_pointwise_comparison.json) |
| Frozen promotion comparison | W2-gate | A slice guardrail rejected the candidate. [Release decision](stage2_release_decision.md) |
| Independent report | W3 | One recorded opening for `rule-v1` and the rejected candidate. [Final evaluation](final_evaluation_report.md) |
| Reference performance | Stable, peak, synthetic shadow and canary fixture | All measured modes exceeded the client p95 target. [Latency verdict](stage4_latency_verdict.md) |
