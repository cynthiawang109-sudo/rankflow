# Stage 0 data-quality sign-off

**Disposition — proceed to Stage 1 with a registered follow-up data-quality investigation.**

The verified OTTO run sampled 200,000 sessions with cap 200,000 and seed `rankflow-stage0-sample-v1`. It retained 108,214 (54.11%), excluded 91,786 for crossing at least one boundary (45.89%), and found zero outside all windows. The run produced 409,839 queries and 1,332,494 co-visitation rows.

## Kept and boundary-excluded sessions

Kept sessions include W0 history as well as W1 through W3. Each boundary-excluded session is counted once. Duration is the last event timestamp minus the first, converted from milliseconds to hours below. Percentiles other than the median use nearest rank. The median averages the two middle values for an even group size.

| Statistic | Kept events per session | Excluded events per session | Kept duration (hours) | Excluded duration (hours) |
|---|---:|---:|---:|---:|
| Minimum | 2 | 2 | 0.000 | 0.035 |
| Mean | 7.73 | 27.41 | 13.629 | 344.494 |
| P25 | 2 | 5 | 0.036 | 199.454 |
| Median | 4 | 11 | 0.192 | 335.290 |
| P75 | 8 | 29 | 7.706 | 488.966 |
| P90 | 17 | 68 | 52.592 | 587.717 |
| P95 | 26 | 108 | 88.310 | 623.652 |
| P99 | 58 | 241 | 132.506 | 654.053 |
| Maximum | 448 | 495 | 167.741 | 671.934 |

| Session length | Kept (of 108,214) | Boundary-excluded (of 91,786) |
|---|---:|---:|
| Short (at most 20 events) | 100,349 (92.73%) | 61,293 (66.78%) |
| Long (more than 20 events) | 7,865 (7.27%) | 30,493 (33.22%) |
| More than 100 events (subset of long) | 249 (0.23%) | 5,136 (5.60%) |

## Behavior mix

Each share uses the total events in its group as the denominator. A repeat-item event has an `aid` already seen earlier in the same session, across all event types, with original list order breaking timestamp ties.

| Event measure | Kept (836,548 events) | Boundary-excluded (2,516,157 events) |
|---|---:|---:|
| Click | 747,599 (89.37%) | 2,266,011 (90.06%) |
| Cart | 68,142 (8.15%) | 192,998 (7.67%) |
| Order | 20,807 (2.49%) | 57,148 (2.27%) |
| Repeat-item event | 288,665 (34.51%) | 991,071 (39.39%) |

## Per-window sufficiency and pinned retrieval baseline

An eligible prefix here is an emitted cutoff under the recorded policy, starting at prefix length one and taking the first ten positions at most per session. Each eligible prefix yields one query. Under `nextclick-v1`, the label is the first click after the cutoff position. With no subsequent click, the query has no label. An all-negative query has a next-click label whose item is absent from the Stage 0 candidates.

| Partition | Retained sessions | Events | Eligible prefixes | Labeled next-click queries | No-label queries | All-negative queries | Retrieved positives | `candidate_recall@100` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| W1 | 26,042 | 193,729 | 130,626 | 106,649 | 23,977 | 94,702 | 11,947 | 11.20% |
| W2-dev | 13,226 | 98,961 | 66,981 | 54,776 | 12,205 | 49,185 | 5,591 | 10.21% |
| W2-gate | 12,967 | 96,615 | 65,765 | 53,717 | 12,048 | 48,232 | 5,485 | 10.21% |
| W3 | 27,925 | 234,470 | 146,467 | 121,459 | 25,008 | 110,411 | 11,048 | 9.10% |

The “~11%” figure is the W1 result, 11,947 divided by 106,649. Under Addendum R28, `candidate_recall@C` is the fraction of labeled queries in a partition whose target appears anywhere in the candidate union at cap C. Stage 0 used prefix co-visitation as its sole source. It walked prefix events newest to oldest, read each item's stored neighbors in table order, and stopped at 100 distinct candidates or when the neighbors ran out. All-negative queries stay in the denominator. No-label queries are excluded. This measures candidate-set membership before ranking.

All four rates use the W0-only snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9` with history watermark `1659909572414` ms. Its configuration pins `candidate_cap=100`, pair definition `canonical-position-v1`, position horizon `H=20`, session event cap 500, at most 100 neighbors per item, and minimum pair count 1. The build used a 1,073,741,824-byte disk budget and an 8,192 KiB SQLite cache target. Comparisons against this baseline should hold the partition's labeled-query population, snapshot, and cap fixed and record the sources used. Addendum R27 reserves W2-gate for promotion comparisons.

## Disposition and registered follow-up

The Stage 0 exit gate in SPEC §12 is met by the [real-run validation report](data_validation_report_real.md), recorded byte-identical query replay, epoch registration with strict snapshot and label checks, and the written [Playground UX/API contract](product_contract.md). The full unit suite passed all 14 tests, including future-event mutation and Addendum Stage 0 tests T09, T17, and T18. SPEC §3.2 and Addendum F05 require whole-session exclusion at boundaries. The frozen Stage 0 exit gate sets no minimum retrieval recall. Each evaluation partition has at least 53,717 labeled queries, with 9.10–11.20% retrieved by the single-source baseline. Each miss leaves the ranker without the target in that candidate set.

The boundary rule removes a group with a 33.22% long-session share and 39.39% repeat-event share, compared with 7.27% and 34.51% among retained sessions. Register a follow-up to measure retention rates across the full sample by session length (at most 20, 21–100, and above 100 events), duration, and repeat-item share. On the fixed W2-dev query population, report session and query counts, label yield (labeled divided by eligible prefixes), and pinned `candidate_recall@100` by those same session characteristics. This will quantify which behaviors are underrepresented after boundary exclusion and whether the retained slices differ in label availability or retrieval coverage. Keep the governed window and label rules for the investigation, and use W2-dev for query-level diagnostics.

## Evidence and recomputation

The [JSON evidence](stage0_data_quality_report.json) records counts, unrounded shares, duration statistics in milliseconds, and the snapshot configuration. The [read-only analysis script](../tools/stage0_data_quality.py) used the existing Stage 0 reader and window assignment rule on the governed `sessions.jsonl` artifact. Recomputing the pooled group distributions, length shares, event mix, and repeat-item shares took **26.754 seconds**, including SHA-256 verification against the real-run report. The raw OTTO files were unnecessary.

Per-window session, event, and query counts come from the published real-run JSON. Labeled counts sum retrieved and unretrieved positives, and recall rates divide retrieved positives by that sum. W3 sufficiency and recall use only those published aggregates. The pooled session comparison reads event records and derives no query labels. The analysis never opens the query artifact.
