# Stage 0 real OTTO data validation

Data provenance `otto_offline`.

OTTO download verified against the fetch manifest.

## Sample and run measurements

The sampler selected **200,000 sessions** with cap 200,000 and seed `rankflow-stage0-sample-v1`. Of these, 108,214 were assigned to windows, 91,786 crossed one or more boundaries, and 0 were outside all windows.

The fetch took 269.790 seconds, including extraction and hashing. The Stage 0 CLI took 1611.183 seconds, including invariant tests and query replay.

Files in `data/otto` total 14,185,811,936 bytes. The real run files total 647,990,378 bytes. The entire `artifacts` directory totals 648,360,260 bytes, for a combined 14,834,172,196 bytes with `data/otto`. These totals sum file lengths.

SHA-256 matched the fetch manifest independently for the archive and both extracted files. The JSON evidence records all three verified digests.

## Windows

| Partition | Range in Unix milliseconds [start, end) | Sessions | Events |
|---|---|---:|---:|
| W0 | [1659304800000, 1659909600000) | 28054 | 212773 |
| W1 | [1659909600000, 1660514400000) | 26042 | 193729 |
| W2-dev | [1660514400000, 1661119200000) | 13226 | 98961 |
| W2-gate | [1660514400000, 1661119200000) | 12967 | 96615 |
| W3 | [1661119200000, 1661724000000) | 27925 | 234470 |

### Boundary exclusions

| Session length | Excluded sessions | Excluded events |
|---|---:|---:|
| short | 61293 | 475678 |
| long | 30493 | 2040479 |

Short sessions have at most 20 events.
| Boundary in Unix milliseconds | Crossing sessions |
|---|---:|
| 1659304800000 | 0 |
| 1659909600000 | 55049 |
| 1660514400000 | 68343 |
| 1661119200000 | 54817 |
| 1661724000000 | 0 |

A session can contribute to several boundary rows. The exclusion totals by session length count each excluded session once.
Outside all windows, there were 0 sessions and 0 events.

## Query and label coverage

W0 supplies co-visitation history and generates zero queries.

Stage 0 co-visitation candidates from the recorded prefix. No-label rows have no subsequent click and are excluded from primary next-click metrics.

| Partition | Queries | Retrieved positive | Unretrieved positive | No label |
|---|---:|---:|---:|---:|
| W1 | 130626 | 11947 | 94702 | 23977 |
| W2-dev | 66981 | 5591 | 49185 | 12205 |
| W2-gate | 65765 | 5485 | 48232 | 12048 |
| W3 | 146467 | 11048 | 110411 | 25008 |

## Co-visitation

The scan used a 20-position horizon and a 500-event session cap under `canonical-position-v1`.
680785 canonical pairs over 90126 history items produced 1332494 directed rows with at most 100 neighbours per item and minimum count 1.
The table uses 97005269 bytes. SQLite staging used 19968000 bytes under a combined build budget of 1073741824 bytes and a 8192 KiB cache target.
Build time was 17.374049 seconds on Windows-10-10.0.26300-SP0. Process peak resident memory observed at build completion was 100184064 bytes.

## Invariants

| Run check | Result |
|---|---|
| epoch registration, including strict snapshot and label predicates | PASS |
| byte-identical query replay from manifest and configuration | PASS |

| Fixture test | Result |
|---|---|
| test_determinism_and_replay | PASS |
| test_disk_budget_aborts_without_partial_table | PASS |
| test_extracts_kaggle_filenames | PASS |
| test_failed_download_does_not_publish | PASS |
| test_fetch_command_and_hashes | PASS |
| test_fixture_cannot_be_used_as_otto | PASS |
| test_future_mutation | PASS |
| test_leakage_and_crossing_accounting | PASS |
| test_rejects_multiple_matches | PASS |
| test_sampler_and_ingestion_order | PASS |
| test_t09_tied_cutoffs_and_order | PASS |
| test_t17_rejects_invalid_registration | PASS |
| test_t18_exact_pairs | PASS |
| test_top_n_and_minimum_count | PASS |

## Reproducibility

- Source SHA-256 `06716132f1ab1d500f1515ba2c16187d7b0e98066ca66d33b95f022f8c3a340d`
- Query SHA-256 `0101abfbc038bf4c36a1dc7e59a7307c77cc79311d75a15209537cff445fb670`
- Co-visitation SHA-256 `2505618567cf2d8d5c9c73c1b44343efa25e005f529655145e6d15dc6ca088a0`
- Snapshot ID `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`
