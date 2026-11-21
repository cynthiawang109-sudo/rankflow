# Section 14 feature drift demo

## Protocol fixed before execution

Use the frozen W2-dev covered, labeled queries and the stable generation's
feature builder and retrieval configuration. Assign each session to one of six
groups by its governed session hash modulo six. Group 0 is the reference.
Groups 1–5 are successive, disjoint monitoring windows. Observe every
candidate row in each scored query. The initial group uses unmodified rows.

Add exactly 100 events to the `session_length` feature value of every monitored
candidate row in groups 2 and 3. The demo changes the value fed to the
histogram. Groups 4 and 5 use unmodified values for recovery. The monitored
populations and bin assignment are deterministic. This is a local
`source=demo` exercise for the stable generation.

Use left-inclusive bins with boundaries 2, 5, 10, 20 and 50. Calculate PSI
with a half-count pseudocount in each bin. Each distribution needs at least
1,000 observations. Raise after two consecutive windows at or above PSI 0.25.
Recover after two consecutive windows below 0.25. An insufficient window
resets the streak. Each measurement and alert transition is signed in the
existing operator audit and displayed by the authenticated Console.

## Recorded run

The run used PostgreSQL 16.16 and stable bundle
`gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65`.
The reference bins contained `[23802, 56607, 59103, 8338, 0, 0]` candidate
rows. All observed windows had missing rate 0. Demo ID
`34232ec3fb5c4b5e9850047df494a33c` links the five signed records.

| Window | Phase | Observed bins | PSI | Alert state |
| ---: | --- | --- | ---: | --- |
| 1 | Normal | 24965, 58028, 55137, 8178, 0, 0 | 0.0024008305770577684 | Clear |
| 2 | Shift | 0, 0, 0, 0, 0, 149723 | 24.016019922552882 | First breach |
| 3 | Shift | 0, 0, 0, 0, 0, 136624 | 23.924433722231456 | Raised |
| 4 | Recovery | 23698, 55733, 58526, 8227, 0, 0 | 0.000015808304336260777 | Active |
| 5 | Recovery | 23817, 56739, 53013, 7722, 0, 0 | 0.0028511316237935166 | Recovered |

The normal holdout window raised no alert. Alert
`31bdd95f16864661be1056997351e190` was raised at
`2026-11-21T14:17:25.162796+00:00` in signed audit row
`1d320f8f63b94a3486dda9add9da3a6d`. The same alert recovered at
`2026-11-21T14:17:25.169908+00:00` in signed audit row
`5bd1b46d8a4449879c280bfa84079a2f`.

The authenticated Operator Console returned HTTP 200 with both transitions,
PSI measurements, histograms, audit IDs and the mapped action to investigate
and block new promotions until review. The same request without credentials
returned HTTP 401. The capture contains the records extracted from the
actual HTML response and matched to the signed audit query.
[Operator Console capture](closure_drift_console.json)

## Repeat the demo

Set `RANKFLOW_TEST_DATABASE_URL` to a disposable local PostgreSQL database,
`RANKFLOW_AUDIT_KEY` to a local signing key, and `$stable` to the archived
stable bundle directory. Run:

```powershell
uv run --locked python -m rankflow.drift artifacts/stage0-otto $stable
uv run --locked python -m unittest tests.test_closure_drift -v
```

Open `/operator/drift?demo_id=<demo_id>` on the local Operator Console
using a viewer bearer token. The Console must use the same database and
key through `RANKFLOW_DATABASE_URL` and `RANKFLOW_RELEASE_SIGNING_KEY`.
The focused automated suite passed 2 tests, with 0 failed and 0 skipped.
