# lgbm-otto-rehearsal-v1 model card

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1% with 21–100 events, and 4.6% with more than 100 events. Headline metrics describe the retained OTTO population.

The sampling note describes the pinned Stage 0 baseline. This rehearsal uses verified later OTTO session prefixes and reports development evidence for its own epoch.

| Segment | Labeled | Coverage | HitRate@20 | MRR@20 |
|---|---:|---:|---:|---:|
| overall | 3854 | 4.6186% | 0.045407 | 0.035290 |
| prefix/cold | 3090 | 0.1294% | 0.000324 | 0.000029 |
| prefix/warm | 764 | 22.7749% | 0.227749 | 0.177903 |
| session_length/21_to_100 | 450 | 6.2222% | 0.062222 | 0.050539 |
| session_length/over_100 | 10 | 30.0000% | 0.300000 | 0.300000 |
| session_length/up_to_20 | 3394 | 4.3312% | 0.042428 | 0.032489 |
| target_popularity/head | 22 | 81.8182% | 0.681818 | 0.454307 |
| target_popularity/tail | 324 | 49.3827% | 0.493827 | 0.388932 |
| target_popularity/unseen | 3508 | 0.0000% | 0.000000 | 0.000000 |
