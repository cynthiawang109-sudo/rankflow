# Stage 1 exit evidence

## PostgreSQL and API tests

Ran `python -m unittest discover -v` with `RANKFLOW_TEST_DATABASE_URL`
pointing to a local PostgreSQL 16.15 instance. All 24 tests passed, including
the 14 Stage 0 tests. The PostgreSQL tests isolated their writes in a dedicated
schema and removed it after the run.

| Gate | Observed result |
|---|---|
| T05 | A simulated disconnect while sending the response left the committed decision and outbox entry durable. The impression recorded `send_failed` and had no acknowledgement. |
| T06 | A candidate outside the returned top-K was rejected as `not_in_returned_top_k`. An action on a returned item was attributed as demo feedback and a repeated event ID returned the original result. |
| T13 public boundary | Public prefix reads for W2-gate and W3 returned 404. Public W2-dev responses exposed only prefix data. |
| T15 ack basics | Delayed and duplicate acknowledgements were idempotent. The harness observed `send_completed`, `send_failed`, and `send_unknown` independently of confirmation. A late acknowledgement preserved the expired state. |
| Transaction failure | An injected PostgreSQL outbox failure rolled back the impression and decision. The API served the ranking with `logging_status: degraded` and a null impression ID. |
| Fallback, parity and retrieval | Tests covered persisted assigned and served strategy divergence, logical timeout, deterministic retrieval, cold-start paths, point-in-time features, training and serving parity, and R6 group accounting. |

## Docker Compose and real OTTO review loop

Built and started the API and PostgreSQL with
`docker compose up --build --detach --wait`. Both containers were healthy.
The API reported `serving_ready` and `release_ready`.

The headless Edge smoke run opened `/playground`, loaded a W2-dev prefix,
rendered 20 positions and their provenance, showed the ranker-only comparison,
acknowledged the rendered result, and displayed the attributed demo click.
An independent client posted the copied payload to `/v1/recommend` and
received identical ranked items, scores and source provenance under the
same generation.

- Generation `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65`
- Snapshot `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`
- PostgreSQL contained two durable decisions and two delivered outbox events
  from the Playground ranking and API replay. The Playground produced one
  confirmed acknowledgement and one attributed demo interaction.

The [retrieval study](stage1_retrieval_ablation.md) and
[strategy comparison](stage1_strategy_report.md) record the W2-dev measurements.
