# Retrieval evaluation

## Protocol

- **report_version** — retrieval-v1
- **window** — W2-dev
- **label_policy** — nextclick-v1
- **snapshot_id** — cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9
- **watermark** — 1659909572414
- **epoch** — {'candidate_family': ['LightGBM-LambdaRank', 1, 'nextclick-v1'], 'dataset_manifest_hash': 'b4ce68b9761b403f895acf3c77d7748a8634034abcf12fa701e5d44a05a86b00', 'epoch_id': 'stage0-initial', 'final_test_window': [1661119200000, 1661724000000], 'history_statistics_watermark': 1659909572414, 'query_manifest_hash': '0101abfbc038bf4c36a1dc7e59a7307c77cc79311d75a15209537cff445fb670', 'retrieval_snapshot_id': 'cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9', 'source': 'otto_offline', 'training_data_watermark': 1660514395857, 'validation_window': [1660514400000, 1661119200000]}
- **caps** — (50, 100, 200, 300)
- **ordering** — deterministic retrieval order (interim)
- **denominator** — Labeled queries, including retrieval misses. No-label queries counted separately.
- **recall_definition** — Target membership anywhere in the capped candidate union.
- **pre_rank_definition** — Target membership within ordered candidate depth.
- **memory_definition** — Cumulative process peak RSS at each variant completion. Includes shared snapshot and population.
- **platform** — Windows-10-10.0.26300-SP0
- **command** — python -m rankflow.study artifacts\stage0-otto docs\stage1_retrieval_ablation

| Variant | Cap | Candidate recall | Pre-rank hit rate@20 | Pre-rank hit rate@50 | Seconds | Peak RSS bytes |
|---|---:|---:|---:|---:|---:|---:|
| recent | 100 | 15.3480% | 15.3480% | 15.3480% | 0.952 | 317,636,608 |
| covisitation | 100 | 10.2070% | 5.9606% | 8.5822% | 6.084 | 317,636,608 |
| popularity | 100 | 1.9844% | 0.4199% | 1.1374% | 18.281 | 317,636,608 |
| recent+covisitation | 100 | 22.3200% | 19.4227% | 21.2611% | 10.471 | 317,636,608 |
| recent+popularity | 100 | 16.5364% | 15.5999% | 16.0070% | 24.193 | 317,636,608 |
| covisitation+popularity | 100 | 9.5535% | 4.5549% | 7.0049% | 23.888 | 317,636,608 |
| recent+covisitation+popularity | 100 | 21.8709% | 18.5264% | 20.2899% | 25.685 | 317,636,608 |
| A:repeat | 100 | 21.8709% | 18.5264% | 20.2899% | 23.385 | 317,636,608 |
| A:event_type | 100 | 21.8709% | 18.5264% | 20.2899% | 27.237 | 317,636,608 |
| C:50 | 50 | 20.2899% | 18.5264% | 20.2899% | 14.681 | 317,636,608 |
| C:200 | 200 | 23.2657% | 18.5264% | 20.2899% | 69.751 | 317,636,608 |
| C:300 | 300 | 23.9302% | 18.5264% | 20.2899% | 87.147 | 317,636,608 |
| quota:10/100/20 | 100 | 22.3346% | 18.5264% | 20.4688% | 17.188 | 317,636,608 |

[Full metric breakdown](stage1_retrieval_ablation.json)

## W2-dev boundary-exclusion follow-up

Slices use the full retained session for diagnosis. Ranking uses only the prefix. The pinned Stage 0 co-visitation path supplies recall for this table.

| Slice | Sessions | Queries | Labeled | Label yield | Pinned candidate_recall@100 |
|---|---:|---:|---:|---:|---:|
| Duration 1–24h | 2,330 | 14,192 | 12,370 | 87.16% | 10.08% |
| Duration <1h | 8,774 | 39,538 | 30,701 | 77.65% | 10.12% |
| Duration ≥24h | 2,122 | 13,251 | 11,705 | 88.33% | 10.57% |
| Length 21–100 | 892 | 8,920 | 8,920 | 100.00% | 12.40% |
| Length >100 | 25 | 250 | 250 | 100.00% | 6.40% |
| Length ≤20 | 12,309 | 57,811 | 45,606 | 78.89% | 9.80% |
| Repeat share (0, 50%) | 4,665 | 32,272 | 28,659 | 88.80% | 11.05% |
| Repeat share 0 | 4,943 | 15,429 | 10,560 | 68.44% | 8.19% |
| Repeat share ≥50% | 3,618 | 19,280 | 15,557 | 80.69% | 10.01% |

Reproduced the pinned baseline with 5,591 hits across 54,776 labeled queries (10.2070%). Slice computation took 1.029s.

The Stage 0 sign-off documents the wider boundary-excluded population. The table measures label yield and retrieval coverage within retained W2-dev sessions.
