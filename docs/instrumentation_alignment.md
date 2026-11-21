# §9.3 instrumentation alignment

Phase 1 implements the measurement boundaries in the [frozen §9.3 amendment](spec_section_9_3_amendment_v2.md). The previous benchmark finding remains **Not Verified — instrumentation mismatch**.

| Layer | Previous boundary at `fd4ba3e` | Aligned boundary |
| --- | --- | --- |
| Handler | The route clock started after CSRF and stopped while constructing the returned result, before response construction and send. Stage 4 read the response's `latency_ms` as `api_ms`. [Old route](https://github.com/cynthiawang109-sudo/rankflow/blob/fd4ba3ed1596a486305644e27cba3a82e9de792c/rankflow/api.py#L363-L471) | `HandlerLatency` starts at HTTP ASGI middleware entry, before routing and request processing, and stops after the awaited send of the final body event. `RankFlowApp.build_middleware_stack` places it outside Starlette's server-error middleware, so a generated 500 is timed through send too. A request that exits before a final send emits a single incomplete span through middleware exit. [ASGI instrumentation](../rankflow/api.py#L152-L190) |
| Persistence | The route started the clock before `store.persist` and stopped in its `finally` block, including pool wait, preparation, and post-commit work. [Old caller](https://github.com/cynthiawang109-sudo/rankflow/blob/fd4ba3ed1596a486305644e27cba3a82e9de792c/rankflow/api.py#L444-L467) | `PersistenceConnection._exec_command` timestamps dispatch of the implicit BEGIN on the acquired connection and the PostgreSQL COMMIT acknowledgement carrying the COMMIT command tag. Pool acquisition and return, connection close, and post-commit logging are outside the elapsed interval. [Driver instrumentation](../rankflow/store.py#L69-L103) |

**Measurement Definition.** Handler and Persistence percentiles measured after this fix describe different intervals from the Stage 4 and performance-track percentiles. They must not be presented as performance improvement or regression against those historical values. Historical results retain their original definition labels. Use the structured `handler_latency.handler_ms` and committed `persistence_latency.persistence_ms` events for the aligned measurements. The existing response `latency_ms` retains its route-local definition for compatibility. The new handler and persistence events share the recommendation request ID once the route receives a validated ID. A confirmed rollback emits `transaction_outcome=rolled_back` and diagnostic `elapsed_ms`, with a null commit sample. An attempt without a terminal acknowledgement emits `transaction_outcome=unconfirmed` and null durations.

## Behaviour evidence

The installed and locked psycopg 3.3.9 driver starts the implicit transaction through `_start_query` on the first statement. Both the direct connection context and the pool's connection context use psycopg's existing connection exit to commit or roll back. The connection subclass delegates the commands and uses the returned server command tag, so a COMMIT command answered with a ROLLBACK tag cannot count as a successful commit. The pool still acquires and returns the connection through the same context manager with the same settings.

Review the production diff with `git diff fd4ba3e HEAD -- rankflow/api.py rankflow/store.py`. It shows the same decision SQL and parameters, implicit transaction and commit/rollback ownership, pool settings and checkout/return path, retries, and request execution order. Production changes are instrumentation only. The frozen contract, thresholds, benchmark protocol, and client are untouched.

Persistence remains atomic and commits before attribution. The existing `test_atomic_degraded_response_and_persisted_fallback` and `test_dead_decision_connection_rolls_back_and_is_replaced` cover atomic visibility and failed writes. `test_disconnect_after_commit_t05` checks durable decision and outbox records even when send fails. `test_feedback_top_k_t06_and_review_loop` checks attribution against the committed decision. [Existing PostgreSQL tests](../tests/test_stage1.py)

## Validation

Full suite with `RANKFLOW_TEST_DATABASE_URL` set to a disposable PostgreSQL 16.16 instance and `python -m unittest discover -s tests -v` run from the project environment. **63 passed / 0 failed / 0 skipped.**

The new handler test checks streaming response construction, intermediate and final sends, post-response work, and a route exception that produces a 500. The new PostgreSQL tests inject deterministic clock advances around real BEGIN and COMMIT commands, pool checkout and return, and post-commit logging. They also force a rollback after the write and check that no commit sample or durable decision exists. [Boundary tests](../tests/test_stage1.py)
