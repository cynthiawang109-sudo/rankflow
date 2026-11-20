# Stage 0 data validation

Data provenance `synthetic_fixture`.

Full OTTO download deferred. No OTTO run was performed.

## Windows

| Partition | Range in Unix milliseconds [start, end) | Sessions | Events |
|---|---|---:|---:|
| W0 | [100, 200) | 4 | 530 |
| W1 | [200, 300) | 1 | 4 |
| W2-dev | [300, 400) | 9 | 36 |
| W2-gate | [300, 400) | 7 | 28 |
| W3 | [400, 500) | 1 | 2 |

### Boundary exclusions

| Session length | Excluded sessions | Excluded events |
|---|---:|---:|
| short | 2 | 5 |
| long | 1 | 22 |

Short sessions have at most 20 events.
Crossing counts by boundary (Unix milliseconds): 200 (1), 300 (1), 400 (1).
Outside all windows: 0 sessions and 0 events.

## Query and label coverage

Stage 0 co-visitation candidates from the recorded prefix. No-label rows have no subsequent click and are excluded from primary next-click metrics.

| Partition | Queries | Retrieved positive | Unretrieved positive | No label |
|---|---:|---:|---:|---:|
| W1 | 4 | 2 | 1 | 1 |
| W2-dev | 36 | 13 | 14 | 9 |
| W2-gate | 28 | 13 | 8 | 7 |
| W3 | 2 | 0 | 0 | 2 |

## Co-visitation

The scan used a 20-position horizon and a 500-event session cap under `canonical-position-v1`.
8 canonical pairs over 9 history items produced 16 directed rows with at most 100 neighbours per item and minimum count 1.
The table uses 1072 bytes. SQLite staging used 16384 bytes under a combined build budget of 1073741824 bytes and a 8192 KiB cache target.
Build time was 0.029987 seconds on Windows-10-10.0.26300-SP0. Process peak resident memory observed at build completion was 33845248 bytes.

## Invariants

| Run check | Result |
|---|---|
| epoch registration, including strict snapshot and label predicates | PASS |
| byte-identical query replay from manifest and configuration | PASS |

| Fixture test | Result |
|---|---|
| test_determinism_and_replay | PASS |
| test_disk_budget_aborts_without_partial_table | PASS |
| test_failed_download_does_not_publish | PASS |
| test_fetch_command_and_hashes | PASS |
| test_fixture_cannot_be_used_as_otto | PASS |
| test_future_mutation | PASS |
| test_leakage_and_crossing_accounting | PASS |
| test_sampler_and_ingestion_order | PASS |
| test_t09_tied_cutoffs_and_order | PASS |
| test_t17_rejects_invalid_registration | PASS |
| test_t18_exact_pairs | PASS |
| test_top_n_and_minimum_count | PASS |

## Reproducibility

- Source SHA-256 `0ddfce929a6ea3ccb8284013e311e06f7c3c410f47a901a3f8a31c75170c063e`
- Query SHA-256 `25eae4d2b43e7fce0a0a6f0448c1a05635f04fe3272a3a6ddf8a44a1c77654ea`
- Co-visitation SHA-256 `ae8654d0c04a878e97f54caa0430004864400579e70d58f595f28f10c60724a5`
- Snapshot ID `d5da006323ec4f69a8ea37d80c1cd917db6fb92a9a768aa9b8056adde45b361c`
