# pointwise-v1 model card

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1% with 21–100 events, and 4.6% with more than 100 events. Headline metrics describe the retained OTTO population.

This development study compared the binary loss and LambdaRank objectives using
the same frozen W1 training groups, W2-dev evaluation population, retrieval
snapshot and feature builder.

Development preference: `lgbm-v1`. Release decision: no promotion.

| Segment | Labeled | Coverage | HitRate@20 | MRR@20 |
|---|---:|---:|---:|---:|
| overall | 54776 | 22.3346% | 0.198992 | 0.141024 |
| prefix/cold | 16434 | 0.5355% | 0.001765 | 0.000801 |
| prefix/warm | 38342 | 31.6781% | 0.283527 | 0.201126 |
| session_length/21_to_100 | 8920 | 20.7175% | 0.174103 | 0.107834 |
| session_length/over_100 | 250 | 8.0000% | 0.064000 | 0.021297 |
| session_length/up_to_20 | 45606 | 22.7295% | 0.204600 | 0.148172 |
| target_popularity/head | 1087 | 77.1849% | 0.628335 | 0.389524 |
| target_popularity/tail | 24629 | 46.2666% | 0.414836 | 0.296453 |
| target_popularity/unseen | 29060 | 0.0000% | 0.000000 | 0.000000 |

[Paired development comparison and cluster intervals](stage2_pointwise_comparison.json)
