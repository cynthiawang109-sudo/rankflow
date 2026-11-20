# Stage 1 strategy comparison

## Replay protocol

LambdaRank was fit on labeled W1 queries whose target was retrieved. Both strategies scored the same candidate set and shared features on W2-dev. Every labeled query stayed in the end-to-end denominator. No-label queries were counted separately.

- Snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`
- Feature schema `session-features-v1`
- Feature code SHA-256 `cc885ae447b4a1b9b066e082d990db7a070ebb3cee5f8b2674b3e6f514af071d`
- LightGBM artifact SHA-256 `8d06f0f97a3485540addeae9d6604b3fae3c948c2de2862d08d7de79e7cebd6d`
- W1 groups fit 24,770, all-negative exclusions 81,879, no-label 23,977, exclusion rate 76.77%, single-positive rate 23.23%
- W2-dev labeled 54,776, no-label 12,205, retrieved 12,234
- Fit wall time 13.58s and evaluation wall time 155.50s

| Strategy | HitRate@20 | MRR@20 | NDCG@20 |
|---|---:|---:|---:|
| rule-v1 | 19.6309% | 0.1340 | 0.1484 |
| lgbm-v1 | 19.9357% | 0.1425 | 0.1557 |

## R1 decision

`lgbm-v1` led on both primary metrics.

The primary metrics are end-to-end HitRate@20 and MRR@20. The W2-dev development check allows a 1% relative regression on each. NDCG@20 is secondary.

**Decision** ? passes W2-dev primary check; promotion reserved for Stage 2.

The Alpha serves the registered rule strategy and exposes the fitted model in the Playground as a ranker-only comparison. Governed promotion is a Stage 2 decision.

[Run configuration, lineage, and unrounded metrics](stage1_strategy_report.json)
