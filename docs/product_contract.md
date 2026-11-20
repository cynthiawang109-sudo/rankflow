# RankFlow Stage 0 product contract draft

RankFlow is a production-like ML ranking platform operating on a real historical interaction dataset, with a synthetic/local consumer environment. This draft describes the product surfaces and the API they depend on. SPEC.md and ADDENDUM.md govern the contract.

## Ranking Playground

The reviewer can replay a W1 or W2-dev prefix, labeled with its window and cutoff, or build an unlabeled session from item IDs. The default replay uses W2-dev. Every public read surface enforces manifest membership and withholds governed labels. Public W2-gate enumeration and reads are rejected and counted. W3 stays sealed, with operator-only access through the holdout audit process. W2-gate evaluation runs through the audited operator endpoint, with its labels restricted to gate reports.

1. Send the observed session prefix for next-click ranking.
2. See each aid, rank, relative score, and candidate sources, along with the assigned and served strategies, serving generation, snapshot, and fallback state. Display names such as “Item 12345” are marked synthetic.
3. Compare two strategies side by side on the same candidate set for that prefix. Show rank agreement and per-item movements. Scores are interpreted within a strategy.
4. Submit a demo click, cart, or order against a persisted impression. Show the event, attribution status and reason, and `source=demo` immediately.
5. Inspect the request's served strategy and generation in the Operator Console. The loop requires no direct database access.

## Operator Console

The operator inspects the strategy registry and lineage, pinned snapshots and freshness, serving generations and promotion history, experiments and cohort metrics, W2 evaluations, opened W3 reports, quality and drift, persistence and attribution, alerts with their associated actions, and incident history.

Viewer access permits read-only Console and metrics access within the data boundaries above. Operators manage traffic, experiment transitions, and rollback. Admins register strategies, approve promotions, and manage roles and configuration. Promote, ramp, rollback, and kill switch actions go through authenticated APIs or the CLI with role checks and append-only audit. The Console links to these workflows without holding privileged credentials. Rollback restores the designated known-good `config_id`.

Monitoring shows numerator and denominator by generation, cohort, and source. Stale or insufficient canary telemetry yields `unknown`. Sustained `unknown` triggers the configured fail-safe. Demo-only operational telemetry is explicitly labeled synthetic-operational.

## API draft

| Route | Contract |
|---|---|
| `POST /v1/recommend` | Accept `request_id`, pseudonymous `session_id`, an ordered list of `aid`, `ts`, and event type, and bounded `top_k`. Enforce payload, size, rate, and event-count limits. The server selects the assigned strategy. |
| `POST /v1/feedback` | Accept `event_id`, `impression_id`, `aid`, `action`, `occurred_at`, and demo source. Return attribution status or a specific error reason. Retry idempotently by `event_id`. Preserve event and ingest times within a configured attribution window. |
| Idempotent acknowledgement POST | Record the first Playground render confirmation keyed by `impression_id`. Keep send observation and client confirmation as separate states. |
| `GET /v1/strategies`, `GET /v1/traffic`, `GET /v1/metrics/summary` | Read eligible strategy/version and validation metadata, active traffic configuration, and windowed operational summaries with the appropriate access checks. |
| `POST /v1/admin/traffic`, `POST /v1/admin/rollback` | Role-checked, audited traffic mutations. |
| `GET /health/live`, `GET /health/ready` | Report process liveness and readiness. Distinguish `serving_ready` for routing from `release_ready` for release decisions. |
| `GET /playground`, `GET /console` | Serve the two product surfaces and enforce their corresponding data and role boundaries. |

Recommendations return request ID, impression ID when committed, assigned and served strategy, assignment, generation, retrieval snapshot, feature version, logging status, fallback flag, ranked items, and latency. In fallback the healthy rule strategy serves the request and the reason is logged. Scores express relative ordering within the producing strategy. Server-side tracing uses the request ID.

Under the generated-list policy, attribution requires a persisted decision and an aid within the returned top-K. It returns `not_in_returned_top_k` when item membership fails. A degraded response has no usable impression ID and the associated feedback fails with `logging_degraded_no_decision`. Keep confirmed and unconfirmed attribution separate. A persisted recommendation is a ranking decision. Only a client render acknowledgement confirms exposure in the local demo, regardless of the server's send observation. Late confirmations are retained idempotently and leave finalized cohort reports intact.

The Playground and Console use same-site cookies and CSRF protection on mutations. Admin bearer tokens travel in HTTPS headers. Session pseudonymisation uses a versioned HMAC key separate from the routing salt. Follow configured retention and deletion for pseudonymous records. The product collects no names, emails, IP addresses, or payment details.

## Claims and evidence

OTTO supplies historical click, cart, and order events. Historical next-click targets are offline relevance labels. Retrieved non-targets are retrieval negatives. The data contains no randomized exposure or propensity ground truth and provides no product catalog for display. Demo events remain in the demo namespace and are ineligible for real-data gates and promotion. W2-gate supports promotion comparisons, with holdout independence reserved for the registered W3 epoch and candidate family. The committed Stage 0 fixture report measures synthetic data semantics. Conversion lift, real-user impact, production traffic, and revenue require independent evidence.
