# Final independent evaluation

`rule-v1` is the serving strategy. `lgbm-v1` is reported for the historical
record. The Stage 2 W2-gate rejection remains in effect. W3 is a report-only
holdout. Its results trigger no promotion, tuning, threshold changes, strategy
changes, or follow-up experiments.

## Protocol

The one report opening used the frozen `stage0-initial` epoch, `nextclick-v1`
labels, the Stage 1 retrieval snapshot and 100-candidate cap, and the shared
feature pipeline and evaluation function used by Stage 2. Both strategies
received the same candidate union. R28 candidate recall@100 is the share of
labeled queries whose single target is anywhere in that union. End-to-end
HitRate@20 gives credit for a target in the first 20 ranks. MRR@20 gives
reciprocal-rank credit there. Retrieval misses contribute zero to both
ranking metrics. Queries without a next click are counted separately.

- Stable generation `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65`
- Retrieval snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`
- LightGBM SHA-256 `8d06f0f97a3485540addeae9d6604b3fae3c948c2de2862d08d7de79e7cebd6d`
- Training run `156bb1b48bf3aa4c1d8de6b935a25aa323bc0f5c10a294a69853077f41a94b15`
- Final report opening `2026-11-21T03:24:47.240164+00:00`, recorded before accessing W3 queries. [Holdout access log](stage4_holdout_access.json)

## Results

| Window | Labeled queries | No label | Candidate recall@100 | rule-v1 HitRate@20 | rule-v1 MRR@20 | lgbm-v1 HitRate@20 | lgbm-v1 MRR@20 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| W1 training | 106,649 | 23,977 | 23.2257% | Unmeasured | Unmeasured | Unmeasured | Unmeasured |
| W2-dev | 54,776 | 12,205 | 22.3346% | 19.6309% | 0.133963 | 19.9357% | 0.142461 |
| W2-gate | 53,717 | 12,048 | 21.6821% | 18.9716% | 0.128202 | 19.3644% | 0.135655 |
| W3 | 121,459 | 25,008 | 21.0351% | 18.5412% | 0.128779 | 18.9035% | 0.136535 |

W1 was the fitting window. The Stage 2 lineage recorded 24,770 fit groups
and 81,879 all-negative exclusions. Fit groups are exactly the labeled queries whose targets appeared in the pinned candidate union, giving the in-sample W1 recall above. The Stage 0 report measured 11,947
co-visitation-only hits among the 106,649 labeled W1 queries. That earlier
retrieval population statistic uses a single source. [W1 data report](data_validation_report_real.md)
[W2-dev and training lineage](stage2_training_evidence.json)
[W2-gate decision](stage2_release_decision.md)

The W3 pair shares 25,549 retrieved targets across 27,925 labeled-query
sessions. The accompanying JSON records the unrounded results and the
frozen protocol's slice aggregates. [W3 evidence](stage4_final_evaluation.json)

The evaluation describes retained historical OTTO sessions. Boundary
exclusion disproportionately removes longer sessions. The Stage 2 release
record rejected the model for its registered head-popularity slice
regression. No real-user experiments took place.
