# Demo LambdaRank model card

This demo-trained strategy is ineligible for the OTTO release gate.
The metrics describe synthetic operational validation on held-out demo sessions.

The OTTO retrieval snapshot used this sampling policy.

Boundary exclusion retained 62.1% of sessions with at most 20 events, 23.1% with 21–100 events, and 4.6% with more than 100 events. Headline metrics describe the retained OTTO population.

| Demo segment | Labeled | HitRate@20 | MRR@20 |
|---|---:|---:|---:|
| overall | 2 | 1.000000 | 0.093750 |
| prefix/cold | 2 | 1.000000 | 0.093750 |
| target_popularity/head | 2 | 1.000000 | 0.093750 |
