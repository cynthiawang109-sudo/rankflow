# RankFlow

RankFlow is a production-like, session-based e-commerce recommendation and ranking project. Its next-click task uses the observed prefix of a shopping session to rank product IDs. The product design pairs a Ranking Playground with an Operator Console.

The [product contract](docs/product_contract.md) describes the two product surfaces. The synthetic fixture exercises data semantics and smoke paths. OTTO provides historical interactions with anonymized IDs for the offline evaluations. Offline retrieval coverage describes recovery of the next click in those logs. Exposure, conversion lift, production traffic, user impact, and business revenue require separate evidence.

## Run Stage 0

Use Python 3.11 and uv. Run these commands from the repository root with `RANKFLOW_TEST_DATABASE_URL` set to a disposable PostgreSQL database.

```text
uv sync --locked --python 3.11
uv run --locked python -m unittest discover -s tests -v
uv run --locked python scripts/generate_fixture.py
uv run --locked python -m scripts.stage0 build --output artifacts/fixture --report-dir docs
uv run --locked python -m scripts.stage0 replay --run artifacts/fixture --output artifacts/replayed.jsonl
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
uv run --locked python -m scripts.stage0 build --profile otto --input data/otto/train.jsonl --download-manifest data/otto/download_manifest.json --output artifacts/stage0-otto
```

The OTTO profile uses the full-session training file as its source for its own chronological W0–W3 split. The file hashes identify the exact downloaded release. The committed fixture and reports carry `source=synthetic_fixture`. Actual OTTO runs carry `source=otto_offline`. Future Playground feedback carries `source=demo` and stays in the demo training namespace.

## Stage 1 Product Alpha

Use the signed-off OTTO artifacts in `artifacts/stage0-otto`. The Alpha workflow
uses W0 for statistics, W1 for fitting, and W2-dev for development evaluation.

```sh
uv sync --locked --python 3.11
uv run python -m rankflow.evaluate_retrieval artifacts/stage0-otto artifacts/stage1/retrieval
uv run python -m rankflow.study artifacts/stage0-otto artifacts/stage1/retrieval_ablation --rule
uv run python -m rankflow.train artifacts/stage0-otto artifacts/stage1/training configs/stage1_retrieval.json
uv run python -m rankflow.generation artifacts/stage0-otto artifacts/stage1/training artifacts/stage1/generations
# Set RANKFLOW_POSTGRES_PASSWORD (URL-safe) and RANKFLOW_SESSION_KEY to distinct generated values.
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
uv run python -m unittest discover -s tests -v
```

Local demo attribution uses a 24-hour ingest window. Acknowledgements can confirm
rendering for five minutes. Later confirmations are preserved separately. The
Alpha inference deadline is logical and checked after synchronous model scoring
returns. The rule fallback remains scoped to the current request.

The [Stage 1 exit evidence](docs/stage1_exit_evidence.md) records the test and
browser runs against PostgreSQL.
## Stage 2 ML Platform Beta

The [Stage 1 manifest](docs/stage1_baseline_manifest.md) pins the accepted inputs.
Run the training pipeline from the repository root with a clean tracked tree.

```powershell
.venv/Scripts/python.exe -m rankflow.training_pipeline artifacts/stage0-otto artifacts/stage2/training --reproduce
```

The output directory contains the immutable model, JSON lineage and model card.
Reproduction runs both fits and requires exact equality for model checksums,
canonical lineage, counts and development metrics.

The W2-gate command requires an operator bearer and a separate release signing
key. Use one durable, access-controlled release registry for the epoch. The
exclusive claim survives a failed evaluation. The summary contains the
disposition and registry references.

```powershell
.venv/Scripts/python.exe -m rankflow.release_gate artifacts/stage0-otto <registered-run> artifacts/stage2/releases --operator <operator-id> --summary docs/stage2_release_decision.md
```

For serving, set `RANKFLOW_RESCUE_CONFIG` to a provisioned JSON file with
`stable_generation_id`, set `RANKFLOW_GENERATION_REGISTRY` to the shared bundle
directory, and configure PostgreSQL and a shared `RANKFLOW_SESSION_KEY`.
Set `RANKFLOW_ADMIN_BEARER`, `RANKFLOW_RELEASE_REGISTRY`, and
`RANKFLOW_RELEASE_SIGNING_KEY` for authenticated operator views. Requests to
`/operator` and its API endpoints require the HTTP Authorization bearer header.

Prepare canary configs through `POST /operator/prepare` and inspect instance
preloads at `GET /operator/status` before publishing. Mutations provide
`expected_revision` and a unique `operation_id`. Rollback requests name
`rollback_config_id`. A committed pointer revision is observable separately
from the revisions acknowledged by each leased instance.

Run historical candidate replay on the W2-dev population with
`python -m rankflow.shadow_replay`. Run the demo learning rehearsal with
`python -m rankflow.demo_learning`, a serving bundle, a separate demo registry,
and demo click events attributed to at least two distinct sessions. The
rehearsal retains event IDs, a versioned dataset, model, segment evaluation
and a signed decision. The feedback policy distinguishes confirmed actions
from actions attributed to generated lists with unconfirmed impressions.

The [Stage 2 exit evidence](docs/stage2_exit_evidence.md) links the training
replay, signed release decision, model cards, drills and PostgreSQL run.
`RANKFLOW_CONTROL_DATABASE_URL` optionally isolates control-plane connectivity
from event logging. `RANKFLOW_ROUTING_SALTS` points to a protected JSON mapping
from routing salt IDs to secrets when traffic control is enabled. Every routing
salt must differ from `RANKFLOW_SESSION_KEY`. Start a new experiment when moving
from Stage 2's shared-key routing to Stage 3's independent key configuration.
Viewer and operator bearers are configured separately with
`RANKFLOW_VIEWER_BEARER` and `RANKFLOW_OPERATOR_BEARER`.

## Release and operations evidence

`rule-v1` is the stable serving strategy. The signed W2-gate record rejected
`lgbm-v1`. The public comparison is an offline-trained model replay and demo
feedback is isolated from the governed training and release path.

See the [product contract](docs/product_contract.md), [operations runbooks](docs/runbooks.md),
[Stage 2 release decision](docs/stage2_release_decision.md), and
[Stage 3 operational evidence](docs/stage3_exit_evidence.md).

### Reference deployment

The [CDK app](infra/stage4.cjs) defines the ca-central-1 reference deployment.
Use the [AWS deployment procedure](docs/stage4_deployment.md) to create,
verify, and remove the reference service.
The deployment path creates the base stack, uploads content-addressed bundles
and an immutable ECR image, then enables the HTTPS listener and the Fargate
service. A short-lived certificate imported into ACM secures the ALB probes.
The probes trust the imported certificate explicitly. The ALB checks routability
and exposes liveness and release readiness through the API. RDS stays in
isolated subnets. Task startup downloads S3 artifacts into a local registry and
verifies checksums before serving. AWS Secrets Manager supplies the database
credentials, role bearers, release signing key, and the two independent salts.

### Acceptance and clean-room reproduction

Use a clean checkout, Python 3.11, and the archived Stage 1 OTTO baseline
identified in [the baseline manifest](docs/stage1_baseline_manifest.json).
Place the archived Stage 0 artifacts under `artifacts/stage0-otto`. The
training command verifies the pinned manifests, inputs, snapshot, and feature
code. It uses W1 for fitting and W2-dev for development evaluation. Obtain the
baseline from the governed artifact archive before starting. Training and
generation building consume `data_manifest.json`, `evaluation_epoch.json`,
`sessions.jsonl`, `history.jsonl`, and `covisitation.jsonl`. The repository
ships checksums and a synthetic smoke fixture. The historical raw-OTTO Stage 0
build above computes partition coverage and is outside this holdout-safe replay.

```powershell
uv sync --locked --python 3.11
uv run --locked python -m rankflow.training_pipeline artifacts/stage0-otto artifacts/stage4-training --reproduce
$run = Get-ChildItem artifacts/stage4-training -Directory -Filter '*-verified'
Get-FileHash (Join-Path $run.FullName lgbm-v1.txt) -Algorithm SHA256
uv run --locked python -m rankflow.generation artifacts/stage0-otto $run.FullName artifacts/stage1/generations
```

The training command prints the registered run directory. Compare its model
SHA-256, training counts, and W2-dev evaluation against [Stage 2 lineage](docs/stage2_training_evidence.json).
The run ID includes the current code revision. Use fresh output paths for
each replay. The generation command publishes `alpha.txt` with the new
content-addressed bundle ID and the stable `rule-v1` assignment.

Run the following with a fresh Compose project name and an unused loopback
port. The password and session key are disposable and stay local.

```powershell
$env:RANKFLOW_POSTGRES_PASSWORD = [guid]::NewGuid().ToString('N')
$env:RANKFLOW_SESSION_KEY = [guid]::NewGuid().ToString('N')
$env:RANKFLOW_GENERATIONS_DIR = (Resolve-Path artifacts/stage1/generations).Path
$env:RANKFLOW_PORT = '18080'
docker compose -p rankflow-reproduce up --build --wait
Invoke-RestMethod http://127.0.0.1:18080/health/ready
$request = @{request_id=[guid]::NewGuid().ToString();session_id='reproduce';events=@()} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:18080/v1/recommend -Method Post -ContentType 'application/json' -Body $request
docker compose -p rankflow-reproduce down --volumes
```

Verify `serving_ready`, `served_strategy=rule-v1`, a `serving_generation`
matching `alpha.txt`, and `logging_status=persisted` with an impression ID.
For the full acceptance suite, set `RANKFLOW_TEST_DATABASE_URL` to an empty,
disposable PostgreSQL 16 database and run `uv run --locked python -m unittest
discover -s tests -v`. The suite requires the database-backed tests to run.

See the [Stage 4 evidence index](docs/stage4_evidence_index.md) and the
[recorded demo](docs/stage4_demo.mp4).
