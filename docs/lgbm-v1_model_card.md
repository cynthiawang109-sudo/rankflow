# lgbm-v1 model card

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1% with 21–100 events, and 4.6% with more than 100 events. Headline metrics describe the retained OTTO population.

Evaluation population is W2-dev.

| Segment | Labeled | Coverage | HitRate@20 | MRR@20 |
|---|---:|---:|---:|---:|
| overall | 54776 | 22.3346% | 19.9357% | 0.142461 |
| prefix/cold | 16434 | 0.5355% | 0.1643% | 0.000892 |
| prefix/warm | 38342 | 31.6781% | 28.4101% | 0.203139 |
| session_length/21_to_100 | 8920 | 20.7175% | 17.4439% | 0.108434 |
| session_length/over_100 | 250 | 8.0000% | 6.4000% | 0.021067 |
| session_length/up_to_20 | 45606 | 22.7295% | 20.4973% | 0.149782 |
| target_popularity/head | 1087 | 77.1849% | 62.9255% | 0.400171 |
| target_popularity/tail | 24629 | 46.2666% | 41.5608% | 0.299178 |
| target_popularity/unseen | 29060 | 0.0000% | 0.0000% | 0.000000 |
