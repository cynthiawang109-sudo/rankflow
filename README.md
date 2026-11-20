# RankFlow

RankFlow is a production-like, session-based e-commerce recommendation and ranking project. Its next-click task uses the observed prefix of a shopping session to rank product IDs. The product design pairs a Ranking Playground with an Operator Console.

Stage 0 establishes the data semantics and the [draft product contract](docs/product_contract.md). Current evidence comes from a deterministic synthetic fixture. OTTO provides historical interactions with anonymized IDs. Offline retrieval coverage describes recovery of the next click in those logs. Exposure, conversion lift, production traffic, user impact, and business revenue require separate evidence.

## Run Stage 0

Use Python 3.11 or later and uv. Run these commands from the repository root.

```text
uv sync --locked
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/generate_fixture.py
uv run --locked python scripts/stage0.py build --output artifacts/fixture --report-dir docs
uv run --locked python scripts/stage0.py replay --run artifacts/fixture --output artifacts/replayed.jsonl
```

Use a fresh run directory and replay output path for each invocation. Build validates the epoch, checks byte-identical replay, and writes Markdown and JSON reports. Omitting `--report-dir` keeps the reports inside the run directory. See the committed [fixture report](docs/data_validation_report.md).

The Stage 0 portion of the spec's `training/` layout lives in `rankflow/data/`. The CLI scripts run ingestion, exact retrieval aggregation, epoch validation, and report generation. All frozen Stage 0 settings live in `configs/stage0.yaml`. Window ranges are half-open and consecutive. W2-dev and W2-gate share W2's time range and have disjoint hashed session memberships. Sampling keeps the lowest seeded SHA-256 keys up to the configured cap. Cutoff selection takes the first eligible event positions up to its cap and preserves no-label rows for accounting.

Each run writes the indexed sampled sessions, W0 history, query rows, and pruned co-visitation table. The retrieval manifest records the snapshot identity, provenance, pruning, disk budget, and measured build resources. The data manifest hashes the data artifacts and records configuration and memberships. The epoch record then pins the data manifest and query file by hash. Snapshot identity depends on W0 content, retrieval configuration, and the table so the same history remains pinned when future events change. Build timing and process memory are observational fields and may vary across runs.

The report measures positive coverage from the co-visitation snapshot alone. Stage 1 owns full three-source retrieval and feature generation. SQLite caps build pages and enforces a combined staging and export budget. A budget abort publishes an error report in the requested run directory.

## OTTO data

The dataset is the **OTTO Recommender Systems Dataset** by OTTO, distributed under **CC BY 4.0**. Dataset citation: Philipp Normann, Sophie Baumeister, and Timo Wilm (2023), Kaggle, DOI 10.34740/KAGGLE/DSV/4991874. See the [official source and citation](https://github.com/otto-de/recsys-dataset) and [CC BY 4.0 license](https://creativecommons.org/licenses/by/4.0/).

Install and configure the Kaggle CLI as described by the official source. Run the following to fetch the official distribution and hash its compressed archive and extracted JSONL files. Keep the download and generated OTTO artifacts in the ignored directories.

```text
uv run --locked python scripts/fetch_data --output data/otto
uv run --locked python scripts/stage0.py build --profile otto --input data/otto/train.jsonl --download-manifest data/otto/download_manifest.json --output artifacts/otto
```

The OTTO profile uses the full-session training file as its source for its own chronological W0–W3 split. The file hashes identify the exact downloaded release. The committed fixture and reports carry `source=synthetic_fixture`. Actual OTTO runs carry `source=otto_offline`. Future Playground feedback carries `source=demo` and stays in the demo training namespace.

## Stage 1 Product Alpha

Use the signed-off OTTO artifacts in `artifacts/stage0-otto`. The Alpha workflow
uses W0 for statistics, W1 for fitting, and W2-dev for development evaluation.

```sh
uv sync --locked
uv run python -m rankflow.evaluate_retrieval artifacts/stage0-otto artifacts/stage1/retrieval
uv run python -m rankflow.study artifacts/stage0-otto artifacts/stage1/retrieval_ablation --rule
uv run python -m rankflow.train artifacts/stage0-otto artifacts/stage1/training configs/stage1_retrieval.json
uv run python -m rankflow.generation artifacts/stage0-otto artifacts/stage1/training artifacts/stage1/generations
docker compose up --build
```

Open [Ranking Playground](http://localhost:8000/playground). Choose a W2-dev
prefix, rank it, and submit a demo action for a returned item. The feedback panel
shows the event ID, action, attribution result, and demo provenance. Copy the API
replay payload from the disclosure below the ranking and POST it as JSON to
`/v1/recommend`. The same generation and payload reproduce ranked items, scores,
and candidate provenance. Each request has its own impression and timing.

The generation command verifies the model and feature lineage and stores a
content-addressed bundle. The API reads the Alpha generation at startup. The
public prefix catalog includes only manifest-verified W1 and W2-dev records and
contains cutoff data and observed events. Docker Compose mounts the generation
registry read-only.

The rule and model share `session-features-v1`. Missing age, event type,
co-visitation and popularity values use zero with a corresponding mask or
presence flag. A known item without a neighbour row has a separate indicator.
Source ranks are one-based, with zero reserved for absence in the numeric
matrix. Recency uses the last observed event timestamp as the replay clock.

Review the [retrieval ablation](docs/stage1_retrieval_ablation.md) and the
[strategy comparison](docs/stage1_strategy_report.md). Use the test PostgreSQL
DSN for the durability and acknowledgement cases. The gate tests create and
remove an isolated schema in that database. Use a PostgreSQL instance you
can reach locally and adjust the credentials and port for that instance.

```powershell
$env:RANKFLOW_TEST_DATABASE_URL = 'postgresql://rankflow@127.0.0.1:55431/postgres'
uv run python -m unittest discover -v
```

Local demo attribution uses a 24-hour ingest window. Acknowledgements can confirm
rendering for five minutes. Later confirmations are preserved separately. The
Alpha inference deadline is logical and checked after synchronous model scoring
returns. The rule fallback remains scoped to the current request.

The [Stage 1 exit evidence](docs/stage1_exit_evidence.md) records the test and
browser runs against PostgreSQL.
