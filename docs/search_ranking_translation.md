# Search-ranking translation

RankFlow uses a two-stage retrieve-and-rank pipeline. In search, the retrieval
stage can combine lexical, embedding, and business-rule candidate sources.
A search ranker can reuse candidate provenance, cutoff-aware feature assembly,
feature parity, isolated scoring, and decision attribution. Its inputs would
include the query and query-document features. RankFlow's public API ranks
items from session events.

The offline denominator remains every labeled query, including retrieval
misses. Search requires its own relevance labels, graded metrics where
supported, and a workload reflecting query mix and traffic. The historical
OTTO labels provide next-click relevance for this recommender. Conversion,
exposure, and causal lift require independent search evidence.
