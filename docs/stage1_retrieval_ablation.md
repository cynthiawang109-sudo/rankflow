# Retrieval evaluation

## Protocol

- **report_version** — retrieval-v1
- **window** — W2-dev
- **label_policy** — nextclick-v1
- **snapshot_id** — cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9
- **watermark** — 1659909572414
- **epoch** — stage0-initial
- **caps** — [50, 100, 200, 300]
- **ordering** — rule-v1
- **denominator** — Labeled queries, including retrieval misses. No-label queries counted separately.
- **recall_definition** — Target membership anywhere in the capped candidate union.
- **pre_rank_definition** — Target membership within ordered candidate depth. Retrieval misses receive zero credit without invoking the scorer.
- **wall_definition** — Variant wall time includes retrieval, metric aggregation and scoring retrieved positives. Retrieval wall time sums the candidate-generation calls.
- **memory_definition** — Maximum process resident memory sampled within each variant, including shared data. Sampling interval is 10 ms plus scheduler delay.
- **platform** — Windows-10-10.0.26300-SP0
- **command** — python -m rankflow.study artifacts\stage0-otto docs\stage1_retrieval_ablation --rule

Population includes 54,776 labeled queries and 12,205 no-label queries.

| Variant | Cap | Candidate recall | Pre-rank hit rate@20 | Pre-rank hit rate@50 | Variant seconds | Mean retrieval ms | Peak RSS bytes |
|---|---:|---:|---:|---:|---:|---:|---:|
| recent | 100 | 15.3480% | 15.3480% | 15.3480% | 1.032 | 0.0103 | 309,096,448 |
| covisitation | 100 | 10.2070% | 7.9414% | 9.4768% | 6.901 | 0.0692 | 309,194,752 |
| popularity | 100 | 1.9844% | 1.4587% | 1.7179% | 19.279 | 0.2599 | 309,243,904 |
| recent+covisitation | 100 | 22.3200% | 19.5578% | 21.3415% | 27.063 | 0.2314 | 309,264,384 |
| recent+popularity | 100 | 16.5364% | 15.9833% | 16.2699% | 32.670 | 0.3464 | 309,202,944 |
| covisitation+popularity | 100 | 9.5535% | 7.7224% | 9.1975% | 17.048 | 0.2042 | 309,338,112 |
| recent+covisitation+popularity | 100 | 21.8709% | 19.5816% | 21.3013% | 20.272 | 0.2037 | 308,576,256 |
| A:repeat | 100 | 21.8709% | 19.5816% | 21.3013% | 19.561 | 0.1959 | 291,749,888 |
| A:event_type | 100 | 21.8709% | 19.5816% | 21.3013% | 23.202 | 0.2333 | 288,653,312 |
| C:50 | 50 | 20.2899% | 19.3424% | 20.2899% | 12.433 | 0.1298 | 287,895,552 |
| C:200 | 200 | 23.2657% | 19.5943% | 21.5514% | 42.624 | 0.4116 | 287,854,592 |
| C:300 | 300 | 23.9302% | 19.5980% | 21.5697% | 54.551 | 0.5208 | 286,531,584 |
| quota:10/100/20 | 100 | 22.3346% | 19.6309% | 21.4729% | 14.248 | 0.1414 | 267,628,544 |

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

Reproduced the pinned baseline with 5,591 hits across 54,776 labeled queries (10.2070%). Slice computation took 0.878s.

The Stage 0 sign-off documents the wider boundary-excluded population. The table measures label yield and retrieval coverage within retained W2-dev sessions.

## Alpha retrieval budget

Use plain recency with a 100-candidate cap, 10 recent items, up to 100 co-visitation candidates and 20 popularity candidates. The popularity backstop can fill the cap when prefix items have no neighbours. This budget delivered 22.3346% recall versus 21.8709% with full popularity depth and 22.3200% for recent plus co-visitation. It preserves the three-source design and the initial request budget. Experiment A changes recent ordering within the short prefixes. Experiment C varies the union cap and truncates individual source lists at that depth. The formal recall/latency trade-off is reserved for Stage 2.

The deepest measured configuration changed recall by +1.60 percentage points and used 3.68 times the Alpha budget's mean retrieval latency.

## Rule-strategy ablation

| Variant | End-to-end rule-v1 HitRate@20 |
|---|---:|
| recent | 15.3480% |
| covisitation | 7.9414% |
| popularity | 1.4587% |
| recent+covisitation | 19.5578% |
| recent+popularity | 15.9833% |
| covisitation+popularity | 7.7224% |
| recent+covisitation+popularity | 19.5816% |
| A:repeat | 19.5816% |
| A:event_type | 19.5816% |
| C:50 | 19.3424% |
| C:200 | 19.5943% |
| C:300 | 19.5980% |
| quota:10/100/20 | 19.6309% |
