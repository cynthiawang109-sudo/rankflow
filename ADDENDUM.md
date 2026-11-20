# RankFlow — Technical Contract Addendum to Spec v3.0 (Frozen)

**Document type:** Technical contract clarification addendum (implementation design record)
**Version:** 3.0.4 — Implementation baseline, for owner sign-off (supersedes the v3.0.3 draft; incorporates final sign-off errata C01–C05)
**Date:** 2026-11-19
**Parent document:** `PROJECT5_RANKFLOW_PLAN.md` v3.0 — **FROZEN (product scope)**
**Source:** Independent technical review of v3.0 (Conditional GO), change requests R22–R30, acceptance tests T01–T12; the approval review of the v3.0.1 draft (Conditional Approve; findings F01–F08, tests T13–T20), the sign-off review of v3.0.2 (Conditional Approval; blocking finding B01, clarifications B02–B03, tests T21–T23), and the final sign-off review of v3.0.3 (**Approve with editorial/implementation clarifications**; errata C01–C05, no new tests)

> **Scope statement:** This addendum changes **no** product scope. Product identity, the four completion stages and their gates, the ML lifecycle, and the non-goals of v3.0 are untouched. It clarifies *technical contracts* where v3.0's subsystems were individually sound but mutually inconsistent, exactly as the review recommended.
>
> **Precedence:** Where a clause below explicitly says "amends §X wording", the addendum's wording governs implementation and the corresponding v3.0 phrase is read as replaced. Everywhere else, v3.0 governs. This addendum becomes binding when the owner approves it; approving it is **not** an unfreeze and authorises no scope change.

---

## R22 (P0) — Evaluation epochs and pinned snapshots

**Problem (verified in v3.0):** §3.2/R16 allow later retrieval snapshots, but §9.1 still says replay rebuilds from "the W0 statistics snapshot only". A retraining run on a later OTTO slice (§9.4) has no defined relationship to the sealed W2/W3 windows.

**Contract — the evaluation epoch.** Every evaluation, training run, and generation belongs to exactly one **evaluation epoch**:

```text
EvaluationEpoch
  epoch_id
  history_statistics_watermark   (upper bound of events in the retrieval snapshot)
  training_data_watermark        (upper bound of events usable for training)
  validation_window              (W2 range for this epoch)
  final_test_window              (W3 range for this epoch)
  retrieval_snapshot_id
  dataset_manifest_hash
  query_manifest_hash
  candidate_family               (the model family this epoch's W3 is sealed for)
```

Rules:

1. For every query in the epoch, its pinned snapshot satisfies `max(snapshot_event_ts) < query_cutoff_ts` (the R5 invariant, generalised from "W0" to "the epoch's snapshot").
2. **Amends §9.1 wording:** "the W0 statistics snapshot only" is replaced by "the retrieval snapshot pinned to this evaluation epoch / serving generation". The initial epoch's snapshot is the W0 snapshot; later epochs pin later snapshots. An evaluator must never silently substitute a different snapshot than the one recorded for the run.
3. A historical generation replays under **its own epoch's** snapshot forever; registering a newer snapshot never changes an older generation's candidates or scores (test T01).
4. **Holdout rollover:** If a proposed training dataset overlaps the sealed W3 window of epoch N, the pipeline **refuses** the run for epoch N. Training may proceed only after a new epoch N+1 is registered whose validation and final-test windows lie strictly after the new training watermark and are disjoint from all training data in that epoch. Epoch N's W3 remains sealed for its registered candidate family, and its final report remains epoch N's report (test T02).
5. Snapshot refresh (§3.2 R16) therefore always creates or joins an explicit epoch; there is no "refresh in place".
6. **Epoch validity inequalities (F05):** An epoch registration is valid only if all of these hold, and registration must **reject** any epoch violating them (test T17):
   - `snapshot_watermark < min(cutoff_ts)` over all W2 and W3 queries in the epoch;
   - every training query's **label event time** is strictly before the W2 window start, and every W1 training label satisfies the label rule itself: the label is the first click at an `event_index` strictly after the query's cutoff position (R26), with `label_event_ts` consistent with that ordering under tied timestamps;
   - the W2-dev, W2-gate, and W3 windows are pairwise disjoint and ordered W2 before W3;
   - **window-crossing sessions** (events on both sides of a window boundary) are excluded from both adjacent governed windows and counted in the exclusion accounting (§3.2/R21) — a session is never split across governed windows.
7. **Recycling and family definition (F05):** Data that served as epoch N's W3 may be used as training data **only inside a newly registered epoch**; epoch N's results then stand as historical, and no independence claim carries over. `candidate_family` is the stable tuple *(model class, feature-schema major version, label-policy version)*; repeated W3 inspections are access-logged and never create a "new" holdout for the same family.

## R23 (P0) — Generation promotion: atomic pointer, bounded convergence

**Problem (verified in v3.0):** §8.3 says "atomically move the generation pointer" while also allowing bounded staleness in how instances pick it up. Those are two different guarantees conflated into one word.

**Contract:**

1. **Vocabulary (amends §8.3):** The pointer update is an **atomic control-plane write**. Data-plane rollout is **bounded, observed convergence**. The word "atomic" must never be used in this project to describe the rollout as a whole.
2. **Pointer semantics (replaced by B01):** The CAS-managed pointer does **not** identify a single generation — a canary experiment serves two generations concurrently, so one generation pointer cannot express the release state. The pointer identifies an immutable **traffic configuration snapshot**:

```text
TrafficConfigSnapshot (immutable, content-addressed)
  config_id / content_hash
  experiment_id
  stable_generation_id
  canary_generation_id | null
  canary_percent
  shadow_generation_id | null
  shadow_mode                 (R25)
  routing_salt_id
  guardrail_policy_version
  revision / created_at

ActiveTrafficPointer
  config_id
  revision                    # CAS-controlled
```

   The atomic control-plane mutation is a **CAS update of `ActiveTrafficPointer`** (`UPDATE ... WHERE revision = :expected`). A failed CAS aborts the operation; there is no blind overwrite. A model/strategy version is not a traffic configuration, and the two are never conflated in records or reports.
3. **Request pinning (replaced by B01):** At request start the request pins **one traffic config snapshot** (via the local snapshot of R23.10/B02), derives its sticky cohort from the config's `experiment_id` + `routing_salt_id`, selects exactly one **served generation** (stable or canary), and pins that generation's whole feature + retrieval + strategy bundle for the request. A mid-flight config change never alters an in-flight request's pin. Shadow work is scheduled independently from the same pinned config, with its own pinned challenger generation, and never affects the served response. Every decision record carries `config_id`, cohort assignment, `assigned_generation_id`, `served_generation_id`, and any fallback taken; every response reports its pinned `config_id` and served generation (§6.1).
4. **Membership and readiness:** Serving instances hold a **readiness lease** (heartbeat at a configured interval; lease expiry removes the instance from the ready set). Only leased, ready instances count toward promotion acknowledgement.
4a. **Readiness controls routing (F02):** There is exactly **one authoritative readiness signal** per instance — the instance's readiness endpoint/state — and the traffic-routing layer (load balancer / router of the deployment in use) must consume it. **Release readiness** (see the three-signal model in R23.11/C02) is `false` when any of these holds: the lease has expired; a generation bundle referenced by the active config is incompatible or unavailable on the instance; or the instance's **active configuration revision** has not converged by the deadline (R23.7). Serving the stable generation under a current config is valid and is never, by itself, staleness. The routing layer's health-check interval and the resulting propagation delay are configured and recorded; in-flight requests already pinned to an older generation **complete under their original pin** (connection draining), while, **after the recorded load-balancer deregistration/propagation delay has elapsed, zero new requests are routed to a not-ready instance**; requests arriving inside the propagation window are counted separately as `propagation_window_requests` and are not silently folded into either guarantee (test T14).
5. **Promotion protocol (config-level, per B01):** Register the new config and its bundles in the artifact store (R29) → each ready instance preloads and validates **every generation the config can route to** (stable *and* canary; shadow readiness follows its isolation policy and is reported separately) → each acknowledges `{instance_id, config_id, revision, bundle_checksums}` within a configured deadline → CAS the pointer → instances converge by config polling (configured interval) → the promotion is reported **"converged" only when every ready instance acknowledges the config revision and readiness of all referenced served bundles**; otherwise it is reported "partially converged" with per-instance status. A promotion is never reported as successful at a stronger level than was observed (tests T03, T21).
6. **Scale-out and restart during promotion:** A new or restarting instance loads the **current traffic configuration snapshot** and validates **all referenced served generations** before reporting ready. If it cannot load the current config, it may serve only under the designated rescue config (R23.9/C03) and is not release-ready.
7. **Stale instances:** An instance is **stale** when its active configuration revision has not converged by the deadline — not because it serves stable rather than canary under a current config. A stale instance is removed from the ready set **and from routing eligibility (R23.4a)** until it converges or is rolled back with the fleet. The promotion is then reported `partially_converged` (states: `pointer_committed` → `partially_converged` → `converged`) and an operator alert fires. **Fleet-capacity safeguard:** if excluding stale instances would drop the ready fleet below the configured minimum serving capacity, the promotion is instead **aborted and the pointer rolled back to the previous known-good `config_id`**, and an incident alert is raised — the fleet is never silently drained to unavailability in the name of convergence. Tests T03/T14/T21 must verify that a correctly pinned stable-cohort request is never mistaken for a stale instance while a canary is active.
8. **Rollback (amends §8.4; retargeted by B01):** Rollback names an **explicit target `config_id`** — a known-good traffic configuration and its constituent generations — is CAS-guarded and idempotent under an operation ID, and returns a per-instance acknowledgement report, including an honest timeout/non-convergence result for instances that did not confirm (test T04). "Rollback issued" and "rollback converged" are distinct reported states.
9. **Emergency path and the rescue-config invariant (C03):** If a rollback itself fails to converge within its deadline, all instances fall back to a **globally designated, immutable, stable-only rescue config** — a versioned `config_id` registered in the artifact store, identical for every instance, which every instance must be able to load. A per-instance last-known-good cache is a *recovery source* for obtaining that bundle, never an independently chosen traffic policy: instances never pick divergent local configs as an emergency policy. An instance that cannot access the designated rescue bundle reports not-ready (`serving_ready = false`, R23.11) and that fact is surfaced. The incident is alerted, and all further promotions are frozen until an operator resolves the state and records the resolution. Tests T04/T22 assert that all surviving instances select the **same** designated rescue config, or explicitly report partial convergence / removal from routing.
11. **Three readiness signals (C02 — binding policy decision):** Readiness is not one boolean. Each instance exposes:
   - `live` — the process is up;
   - `serving_ready` — the instance can serve a safe response under the current config **or the designated rescue config** (this includes stable-only degraded serving during a control-plane outage);
   - `release_ready` — the instance is eligible to acknowledge new configs and serve canary assignments (requires a fresh local config within the staleness limit and a valid lease).
   **The load balancer consumes `serving_ready` only.** A control-DB outage that outlasts the staleness limit therefore sets `release_ready = false` while `serving_ready` stays `true` on instances that can serve the rescue/stable config — degraded capacity is never removed from routing by a readiness technicality, and the R23.7 fleet-capacity safeguard is evaluated against `serving_ready`. Degraded-mode traffic is attributed and metered as degraded in the Console. Test T22 includes a drill in which control-DB loss outlasts the staleness limit and asserts routing and availability, not only version counters.
10. **Local config snapshot and control-plane outage (B02):** Requests never read the control database directly. Each instance maintains an **atomically replaceable, locally validated copy of the active traffic config**, refreshed by polling (configured interval) or notification; a request pins the local snapshot in a single thread-safe read. The database remains authoritative only for control-plane CAS. The local snapshot carries an age: while age ≤ the configured maximum, serving proceeds from it (staleness is metered); beyond the maximum, the instance serves **stable-only from its last-known-good config**, marks responses degraded, and reports not-ready for canary-bearing configs — it never invents a new canary assignment from stale state. Losing the **control** database (this clause) is a different failure from losing the **event-log** database (R14 degraded logging), even when both are hosted on the same PostgreSQL instance, and the two are reported as distinct incidents (test T22).

## R24 (P0) — A persisted decision is not a confirmed exposure

**Problem (verified in v3.0):** §10.0 calls the committed impression an "exposure", but the client may disconnect or never render after the commit. The outbox guarantees the *decision event's* durability, not that anyone saw the list.

**Contract — three distinct events:**

| Event | Meaning | Who creates it |
|---|---|---|
| `recommendation_generated` | The server produced a ranking and committed impression + decision + outbox in one transaction (§10.0) | Server, synchronous |
| `server_response_send_completed` | The server observed its response write complete without a server-side error. **Server-observed only — not proof the client received or rendered anything** (F03) | Server |
| `client_impression_confirmed` | The client actually rendered the list and acknowledged it | Playground client only, idempotent POST; duplicates are no-ops |

Rules:

1. **Vocabulary (amends §10.0/§6):** The persisted record is a **ranking decision**, not an exposure. The word "exposure" is reserved for `client_impression_confirmed`, and even that is a *local demo client* confirmation, never evidence about real users (§11 claims rules unchanged).
2. **Attribution policy (named):** Feedback attribution follows the **generated-list policy**: an action may be attributed to a persisted `recommendation_generated` list. This is a stated policy choice, not a claim of viewing. Metrics and reports distinguish attributed actions on confirmed vs unconfirmed impressions.
3. **What is persisted:** The impression record stores the **ranked items with positions** and the serving generation (not merely a set of aids), so attribution can validate position and generation.
4. **Attribution validation:** A feedback action is attributable only if its `aid` is within the **returned top-K** of that impression (rank ≤ served K); otherwise attribution fails with the explicit reason `not_in_returned_top_k` (test T06). A simulated disconnect after commit produces a durable decision and **no** confirmed impression (test T05); double acknowledgement is idempotent.
5. **Send-state and confirmation lifecycle (F03, made orthogonal by B03):** Send observation and client confirmation are **two orthogonal state fields**, never one state machine:
   - `send_state`: `send_completed` | `send_failed` | `send_unknown` (the process crashed or the observation was lost between the DB commit and the send; this state must exist and is never silently folded into either of the others).
   - `client_confirmation_state`: `pending` | `confirmed` | `expired_unconfirmed`, driven by a separate idempotent acknowledgement endpoint keyed by the persisted `impression_id` (server-side deduplication key = `impression_id`; first acknowledgement wins, later ones are no-ops).
   A client can validly confirm a response whose send observation is `send_unknown` (it rendered; the server crashed before recording send completion) — that confirmation **counts in full** and suppresses nothing. Reporting is by **impression creation cohort** over a configured, finalized acknowledgement window, with two clearly separated metrics:
   - **Primary cohort metric:** `confirmed / persisted_recommendations` — every persisted impression in the cohort is in the denominator, regardless of send state.
   - **Diagnostic only:** `confirmed / observed_send_completed` — labeled a diagnostic wherever shown; neither metric may be called an authoritative (real-user) exposure rate.
   An acknowledgement arriving **after** its window has closed is preserved as a `late_confirmation` record with its timestamp; it does not rewrite the finalized rate. Late acknowledgements are idempotent under a uniqueness constraint on `(impression_id, acknowledgement_kind)`: a repeated late ack is a no-op and never inflates late-confirmation counts (asserted in T23). Recomputation, if ever performed, produces a new versioned report and retains the original (test T23).
6. **Degraded-response feedback rule:** An `impression_id` is usable for feedback/acknowledgement only when its decision record exists. A response served with `logging_status: degraded` (no committed decision) carries no usable impression ID, and the feedback endpoint rejects submissions against it with the explicit reason `logging_degraded_no_decision`. Delayed feedback and delayed outbox delivery must still join coherently against decision records that do exist (test in §10.0 recovery suite).

## R25 (P0) — Two shadow modes

**Problem (verified in v3.0):** §8.2 says shadow scores "the same frozen candidate set / feature vector", but a challenger *generation* (R13/R16) may carry different feature code, schema, and snapshot, for which the same vector may not even be valid.

**Contract — comparison modes, always labeled:**

| Mode | Candidate set | Features | Valid when | Reports |
|---|---|---|---|---|
| **Ranker-only shadow** | Identical to served (pinned generation) | Identical feature vector | Challenger strategy's feature schema is declared compatible in the compatibility manifest | Rank agreement + score-distribution comparison on the shared set |
| **Full-generation shadow** | Built independently by the challenger generation | Built by the challenger generation's own feature code | Always (isolation permitting) | Candidate-set overlap, rank agreement **on the intersection only**, per-generation distributions — never raw-score diffs |

Rules:

1. **Amends §8.2 wording:** "Score the same frozen candidate set / feature vector with a shadow model" applies to ranker-only mode only. The mode is recorded on every shadow log line and every comparison report.
2. The compatibility manifest (§8.3) must reject a ranker-only comparison between incompatible schemas/snapshots; the operator is offered full-generation mode instead (test T07). **Compatibility is semantic, not nominal (F07):** ranker-only mode requires an identical `feature_code_hash`, or an explicit, audited **equivalence assertion** by an operator (with reason) stating the two feature implementations are transform-, normalisation-, and fill-value-equivalent. Identical field names alone never suffice (test T19).
2a. **Full-generation comparison semantics (F07):** Rank agreement is computed on the **intersection of shared item IDs** with top-K taken at the served K for both lists, and the report always carries `intersection_size` and `overlap@K`; when the intersection is below a configured minimum, the comparison result is **`insufficient_overlap`** — a valid outcome that is never rendered as a zero-quality score; score distributions are displayed per generation and are **never subtracted or otherwise combined across versions**. Shadow execution is fully accounted per (mode, generation): `attempted / succeeded / shed / skipped / timed_out / errored`, each with its denominator, in the Console.
3. Full-generation shadow runs on the separately bounded shadow executor (§8.5), never alters the served response, and is shed first under load (test T12).
4. Playground side-by-side (§6.4) labels its mode: same generation, different strategy → ranker-only; different generations → full-generation.


## R26 (P0) — Versioned label policy and the demo/OTTO boundary

**Problem (verified in v3.0):** §9.4 specifies the learning-loop pipeline mechanically but never defines how events become training labels — the exact gap that would let a mechanically complete pipeline train the wrong task.

**Contract — `label_policy_version` (initial: `nextclick-v1`):**

1. **The only real-data pathway:** From OTTO sessions ordered by `event_index`, for each eligible cutoff position (minimum prefix length and maximum cutoffs per session are frozen configuration), emit one query record:

```text
{ query_id (session_id, cutoff_event_index), session_id_hash, cutoff_event_index,
  cutoff_ts, prefix_events, retrieval_snapshot_id (epoch-pinned),
  positive_aid | none }
```

   The positive is the **first click after the cutoff** (§4.2). Other retrieved candidates are **retrieval negatives** — items the retrieval stage surfaced and the user did not click next in the historical log. They must never be described, in code, reports, or interviews, as "exposed non-clicks": OTTO has no exposure log (§3.3).
2. Every generated training row records its `source`, cutoff, epoch, and `label_policy_version`. A change to any label rule creates a new label-policy version and new dataset versions; old datasets are never silently regenerated under a new policy.
3. **Demo pathway, sealed:** Playground feedback events may be transformed into queries **only** inside the demo namespace. Any dataset, strategy, evaluation, or report derived from them is stamped `demo-trained` / `data_provenance: demo` end to end; the registry **blocks** a `demo-trained` strategy from the real-data gate and from promotion in a real experiment (test T08). Every metric table in every report carries its `data_provenance` (`otto_offline` | `demo`).
4. R6's all-negative rule is part of this policy: groups whose positive was not retrieved are excluded from LambdaRank fitting and retained in end-to-end evaluation, under the same label-policy version.

## R27 (P1) — W2 overfitting protection

W3 staying sealed (R15) does not make repeatedly reused W2 independent. Amendments:

1. W2 is split by a recorded, deterministic session-hash partition into **W2-dev** (unlimited tuning runs) and **W2-gate** (promotion comparisons only). The split and its seed are in the epoch manifest.
2. Gate comparisons must use the **identical W2-gate query population and the epoch-pinned snapshot** for every compared strategy; the protocol (metrics, slices, tolerances) is versioned (`evaluation_protocol_version`, already in the lineage chain) and any change to it creates a new version, recorded in the release record.
3. Reports carry session-clustered confidence intervals and material slice regressions (§9.0). **Amends §9.2 wording:** bootstrap confidence intervals are *required* at Stage 2 and later, not a "desirable Hardening item".
4. No text anywhere may claim statistical independence for W2-gate results; independence claims attach to W3 only, and even there only for its registered candidate family and epoch.

## R28 (P1) — Retrieval depth and co-visitation pair budgets

1. **Candidate cap is configuration (amends §4.3):** `candidate_cap` is a versioned parameter of the retrieval snapshot/generation, initial value **100**, investigated within recorded bounds (50–300) by the R17 ablation. It is not a global constant of the system.
2. **Metric naming (amends §4.3/§9.2):** The ordered pre-rank coverage previously called `Recall@20/50` is labeled **pre-rank hit rate@20/50**. Add **`candidate_recall@C`**: the fraction of held-out queries whose target is anywhere in the unordered candidate union at cap C. Both are reported; neither is conflated with end-to-end HitRate (§4.2).
3. **Co-visitation pair definition (completes R21; made exact by F06):** For event positions `i < j` in a session with `0 < j − i ≤ H` (H is frozen configuration; initial default 20) and `aid_i ≠ aid_j`, form the canonical unordered pair `(min(aid_i, aid_j), max(aid_i, aid_j))`. A canonical pair **qualifies if any** occurrence pair satisfies the horizon; per session, each canonical pair is deduplicated and increments the global count by **exactly one**. The definition is symmetric by construction; any directional/time-ordered variant is a separate, explicitly labeled ablation, never an implicit assumption of this table. Sessions are truncated for pair generation at a configured maximum event count (initial default 500), recorded in the manifest. Two distinct bounds apply (C04): **occurrence comparisons** during the scan are at most `O(min(n·H, n(n−1)/2))` for a session of `n` events, while **distinct emitted pairs** after deduplication are at most that comparison count and at most `n(n−1)/2`. The build enforces a configured **disk budget**: exceeding it aborts the build with a report, never a silent partial table. Exactness (R21) is claimed relative to this declared pair definition. Every retrieval-snapshot manifest records: `H`, the session-event cap, the pair-definition version, the disk abort budget, and the source data hash.

## R29 (P1) — Latency accounting, artifact distribution, recovery objectives

1. **Staged budget, revised (amends §9.3):** The end-to-end p95 100 ms budget is re-allocated to name the costs v3.0 added: validation 5 ms; candidate retrieval 15 ms; feature assembly 20 ms; model scoring 20 ms; **DB commit (impression + decision + outbox) 10 ms**; **inference-pool IPC/queue 5 ms**; response assembly 5 ms; contingency 20 ms. Still provisional planning values, reported pass/fail from measurements at the **client boundary**. The benchmark suite runs each mode independently — stable-only, canary active, shadow active, degraded logging, cold cache, and peak concurrency — because an end-to-end p95 is measured, never derived by summing stage budgets.
2. **Overload behaviour:** All queues are bounded. When the inference pool queue is full, the request takes the rule fallback immediately rather than queueing past its deadline; shadow work is shed before any served work (§8.5).
3. **Artifact distribution (completes §8.3 for the reference deployment):** Release bundles live in a **durable artifact store** — for the reference deployment, immutable S3 object prefixes — and instances keep a **checksum-verified local cache**. The local directory of §5.1 is the development form of the same manifest format. On a cache miss at startup, an instance downloads and verifies the bundle, or serves its last-known-good generation and reports not-ready for the new one. Retention keeps every generation referenced by a stable/canary configuration plus the last N generations; rollback targets (R23) must remain downloadable.
4. **Recovery objectives and the limits of the durability guarantee (completes §11; scoped by F04):** For the reference deployment, target **RPO ≤ 24 h** (from the scheduled backup) and **RTO ≤ 4 h**, both *measured and reported in the backup/restore drill*, which must restore: generation pointers, experiment states, unreconciled outbox events, and artifact references — not only registry rows. If the drill misses the targets, the report says so; targets are not silently relaxed (§16 SLO rule).
   - **Guarantee scoping (binding wording):** The §10.0 outbox at-least-once guarantee covers failures **without permanent loss of committed primary storage** — process crashes, instance loss, DB restarts with storage intact. A **catastrophic restore from backup may lose up to the measured RPO worth of previously acknowledged decisions/events**; those records are unrecoverable without another authoritative durable source, and no report may claim no-loss or exactly-once recovery for the catastrophic path.
   - The two recovery classes are tested separately: ordinary crash recovery (T11 and the §10.0 recovery suite) versus catastrophic DB restore (T16), whose DR report must enumerate the lost/unrecoverable event IDs or a verifiable count of them.
5. **Reproducibility pack:** The repository ships data-fetch instructions with source checksums, a small **synthetic deterministic fixture** in OTTO format (clearly synthetic, permitted to redistribute) for smoke tests, and environment lockfiles (Python lockfile and pinned container digests). An external reviewer must be able to run the smoke path without access to the raw OTTO download.

## R30 (P1) — Privacy keys, CSRF, Playground data boundary, alert denominators

1. **Separate keys:** The cohort/routing salt (§8.2) and the session **pseudonymisation key** are different secrets with different purposes. Pseudonymisation uses a keyed hash (HMAC) with a recorded `key_id` per record; rotating the pseudonymisation key starts a new key version and retains the old key for verification of historical records only. Neither key is ever derived from the other.
2. **CSRF and tokens:** Playground/Console use cookie sessions with `SameSite=Lax` (or stricter) plus a CSRF token on every mutating request. Admin bearer tokens travel only in headers over HTTPS, never in URLs, and are short-lived in the reference deployment.
3. **Playground and API data boundary (amends §6.4/§14; tightened by F01):** Access is split by manifest membership, and the split is enforced by **every** read API, not only the Playground UI:
   - **Public Playground:** W1 prefixes and **W2-dev** prefixes only, plus unlabeled custom sessions. No governed-window **labels** are ever returned on the public surface (a replay shows the ranking, not the target).
   - **W2-gate:** Never exposed through public Playground browsing, examples, session search, or comparison exports. Gate runs execute only through the **audited evaluation endpoint** (operator role); W2-gate labels are visible only inside gate evaluation reports (operator role).
   - **W3:** Sealed as before (R15/R30); prefixes and labels are never served to the Playground; a W3 example requires an operator role and is written to the holdout access log (test T10).
   The §14 demo storyboard defaults to a **W2-dev** prefix. Attempting to enumerate or read a W2-gate prefix or label through any public API is rejected and counted (test T13).
4. **Monitoring denominators and guardrail fail-safe (completes §10.4; hardened by F08):** Every rate — fallback, error, persistence, candidate miss, latency percentiles — is computed **per (serving_generation, cohort, source)** with explicit numerator/denominator, never as an all-traffic aggregate alone. Auto-pause and alerts require a minimum sample count and a hysteresis rule (breach sustained over consecutive windows) so a 5% canary is neither drowned by stable traffic nor paused by noise. Score drift is evaluated per strategy/feature version (§10.4's cross-version caution applies to alerting too).
   - **Unknown is not healthy:** If a canary's eligible-request count is below the configured minimum, or its telemetry is missing/stale beyond the configured freshness window, canary health is reported as **`unknown`** — never as healthy and never as a statistically supported result. **Persistent `unknown` beyond a configured duration auto-pauses the canary** (fail-safe) and alerts; demo and fault-injection traffic (`source=demo`, injected-fault runs) are excluded from real-traffic guardrail denominators. A manual override of an auto-pause requires the operator role, a recorded reason, and is time-boxed; the override and its expiry are audited (test T20). **Synthetic-operational mode:** a demo-only deployment has no real-traffic guardrail denominator; in that case guardrails run in a separately labeled **synthetic-operational mode** whose sole purpose is demonstrating the alert/auto-pause mechanics. Its outputs are never presented as statistical evidence about real-user health.

---

## Acceptance tests added by this addendum (T01–T12)

| ID | Scenario | Pass criterion | Clause |
|---|---|---|---|
| T01 | Register a new retrieval snapshot | A historical generation's replay is ordering-identical under its pinned epoch/snapshot | R22 |
| T02 | Retraining data overlaps sealed W3 | Pipeline refuses for that epoch, or a new epoch with future windows is registered first | R22 |
| T03 | Promotion while one instance is paused and a new one starts | Every response pins one compatible generation; convergence reported honestly, per instance | R23 |
| T04 | Rollback with an unavailable instance | Idempotent result with per-instance acknowledgement and honest timeout state | R23 |
| T05 | Client disconnects after the commit transaction | Durable decision exists; no confirmed impression is recorded | R24 |
| T06 | Feedback references an aid outside the returned top-K | Attribution fails with reason `not_in_returned_top_k` | R24 |
| T07 | Stable and shadow with incompatible feature schemas | Ranker-only comparison is rejected; full-generation mode runs isolated and labeled | R25 |
| T08 | Mixed OTTO + demo input to the training pipeline | Demo data is quarantined to the demo namespace; `demo-trained` is blocked from the real gate/promotion | R26 |
| T09 | New session with same-millisecond events | `event_index` query IDs are unique; replay order preserved | v3.0 R21 |
| T10 | W3 prefix requested from the public Playground | Refused/logged per the data boundary; W3 stays sealed | R30 |
| T11 | DB outage during a response | Ranking may succeed with `logging_status: degraded`; loss metrics and attribution behaviour are correct | v3.0 R14 |
| T12 | Inference hang plus shadow saturation | Foreground deadline and fallback hold; shadow is shed; pool recovers without starvation | R25/§8.5 |
| T13 | Enumerate/read a W2-gate prefix or label via every public Playground/API surface | All rejected and counted; W2-dev access still works | F01 (R27/R30) |
| T14 | Promotion with one instance prevented from converging | After the deadline the instance gets **no new** routed requests; in-flight pinned requests complete consistently; report distinguishes `pointer_committed` / `partially_converged` / `converged` | F02 (R23) |
| T15 | Delayed/duplicate acknowledgements; disconnect before/after send; crash between DB commit and send | No false `client_impression_confirmed`; explicit `send_unknown` state; confirmation rate stable and correctly denominated after the ack window closes | F03 (R24) |
| T16 | Outbox events committed after the last backup, then destructive DB restore | DR report enumerates lost/unrecoverable IDs or a verifiable count; no no-loss or exactly-once claim for the catastrophic path | F04 (R29) |
| T17 | Register an epoch whose W2/W3 intersects a training label horizon, or whose snapshot is newer than a query cutoff | Epoch registration rejects it | F05 (R22) |
| T18 | Session fixture with repeated items, reversed order, tied timestamps, horizon-boundary occurrences | Pair counts match the exactly specified R28/F06 fixture | F06 (R28) |
| T19 | Two generations with identical field names but incompatible feature transforms | Ranker-only shadow rejected absent a recorded equivalence assertion | F07 (R25) |
| T20 | Canary telemetry removed, then delayed recovery and synthetic failures injected | Health reports `unknown`, persistent `unknown` auto-pauses, and no healthy/statistically-supported result is ever fabricated | F08 (R30) |
| T21 | 10% canary: sessions from both cohorts repeatedly hit different instances; config updated mid-flight | Each session stickily receives its cohort's pinned generation bundle on every instance; the in-flight update produces no mixed components; rollback restores stable-only assignments | B01 (R23) |
| T22 | Control DB outage during a config transition, lasting beyond the staleness limit | Requests never mix generations; `release_ready` drops while `serving_ready` (stable/rescue) keeps routing; all surviving instances select the same designated rescue config or report removal; recovery converges to the current config | B02/C02/C03 (R23.9–11) |
| T23 | Decision committed and rendered at the client; server crashes before recording send completion; acknowledgement arrives (then repeated after window expiry) | Confirmation persists as `confirmed` with `send_state = send_unknown`; both R24 metrics count per their documented denominators; the late acknowledgement is stored as `late_confirmation` without rewriting the finalized rate, and a repeated late ack does not inflate its count | B03/C05 (R24) |

## Test-to-stage mapping (T01–T23)

Every test is owned by the stage whose gate it protects; the full suite is re-run as Product Complete evidence (Stage 4).

| Stage | Tests |
|---|---|
| Stage 0 — Foundations | T09, T17, T18 |
| Stage 1 — Product Alpha | T05, T06, T13 (public-boundary part), T15 (ack lifecycle basics) |
| Stage 2 — ML Platform Beta | T01, T02, T07, T08, T13 (gate-endpoint part), T19, T21 |
| Stage 3 — Operated Release | T03, T04, T11, T12, T14, T15 (crash/send states), T16, T20, T22, T23 |
| Stage 4 — Product Complete | Full T01–T23 suite executed and archived as evidence |

## Cross-cutting notes adopted from the approval review

- **Latency honesty:** Per-stage p95 budgets (R29) are planning allocations; they do **not** sum into a proof of end-to-end p95. The end-to-end figure is measured directly at the client boundary under concurrency, including timeout/error tails, the DB transaction, and process-pool wait.
- **Artifact retention pinning:** Retention (R29.3) pins every **rollback-eligible** generation together with **all** its dependencies — strategy artifact, feature code, schema, and retrieval snapshot — not only model binaries.
- **Precedence matrix:** Where clauses overlap, precedence is: (1) this addendum's F-numbered corrections over its own R-numbered clauses; (2) this addendum over v3.0 wording it explicitly amends (per the amendments table); (3) v3.0 over all earlier versions. For §8 specifically: R23/F02 (promotion & routing) governs release mechanics, R25/F07 governs comparisons, R24/F03 governs event semantics wherever §§8–10 mention impressions or shadow.

## Changelog

- **v3.0.1 (draft):** R22–R30 contracts and T01–T12, from the v3.0 technical review.
- **v3.0.4 (this draft):** Final sign-off errata — C01 stale "generation pointer" wording removed (staleness is defined on config revision; rollback targets a known-good `config_id`; the duplicated fragment in R23.3 deleted); C02 three-signal readiness (`live` / `serving_ready` / `release_ready`, LB consumes `serving_ready`); C03 globally designated immutable rescue config invariant; C04 pair-work bound split into occurrence comparisons vs distinct emitted pairs; C05 late-acknowledgement uniqueness constraint. No new tests, no scope change.
- **v3.0.3:** Sign-off-review corrections — **B01 (blocking):** the CAS pointer now identifies an immutable **traffic config snapshot** (stable/canary/shadow/salt/guardrail policy), not a single generation; requests pin the config, derive their cohort, and pin exactly one served generation; canary enablement requires fleet readiness for *both* served generations; rollback targets an explicit `config_id`, with an emergency last-known-good path if rollback itself cannot converge (T21). **B02:** requests pin a locally validated config snapshot — no per-request control-DB read — with bounded-staleness and stable-only degradation, and control-DB vs event-log-DB outages distinguished (T22). **B03:** send observation and client confirmation are orthogonal states; the primary metric is `confirmed / persisted_recommendations`, the send-based ratio is a labeled diagnostic, and late acknowledgements are preserved as `late_confirmation` without rewriting finalized rates (T23). Minor wording: measurable LB propagation guarantee, W1 label-horizon validation, `insufficient_overlap` comparison state, synthetic-operational guardrail mode, snapshot-manifest fields, per-mode latency benchmarks. No product-scope change.
- **v3.0.2:** Approval-review corrections — F01 W2-gate isolation across all read APIs (T13); F02 readiness signal coupled to routing eligibility, draining, and the fleet-capacity safeguard (T14); F03 honest send-state model (`send_completed` / `send_failed` / `send_unknown`) and cohort-based confirmation accounting (T15); F04 durability guarantee scoped against catastrophic RPO loss (T16); F05 epoch validity inequalities, window-crossing rule, recycling and family definition (T17); F06 exact canonical pair definition (T18); F07 semantic feature compatibility and full-generation comparison semantics (T19); F08 guardrail `unknown` fail-safe and override auditing (T20). No product-scope change.

## Wording amendments adopted from the review (summary)

| v3.0 location | Amendment |
|---|---|
| §9.1 | Evaluator loads the epoch-pinned snapshot, not "W0 only" (R22) |
| §8.3 | "Atomic pointer update; bounded observed convergence" (R23) |
| §8.2 | Shadow split into ranker-only / full-generation modes (R25) |
| §10.0 | Persisted ranking decision ≠ client-confirmed impression (R24) |
| §4.3 | `candidate_cap` is versioned configuration, initial 100 (R28) |
| §9.2 | Confidence intervals required from Stage 2, not "desirable" (R27) |
| §6.4 / §14 | Playground defaults to W1/W2-dev prefixes; W2-gate is evaluation-endpoint-only and W3 is access-controlled (R30, tightened by F01) |
| §15 preamble | Stage 0/1 require their data/API gates; *release*-gate language applies from Stage 2 (R27) |

**Status:** Addendum **v3.0.4 — implementation baseline**. The final sign-off review **approved** v3.0.3 subject to errata C01–C05, all integrated here; B01–B03 and F01–F08 are closed on paper. This addendum takes effect on the owner's sign-off and is then versioned with the spec in the project repository. Per the final review, the next action is **Stage 0 implementation** with measured test evidence — not another architecture round. Note, as the review states: this document defines contracts and planned tests; it does not prove any test has passed. Product scope of v3.0 is unchanged and remains frozen.
