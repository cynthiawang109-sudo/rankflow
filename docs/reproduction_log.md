# Stage 4 clean-room reproduction log

The continuation started from detached checkout `71e2241` in the repository's
ignored workspace and installed the lockfile into a new Python 3.11
virtual environment. The working input was a copy of the archived Stage 0
OTTO baseline pinned by the Stage 1 manifest. The replay uses W1 and W2-dev.
Stage 0's raw data rebuild computes coverage for sealed partitions, so the
continuation used the archived inputs for the frozen training and development
evaluation. The archive is a prerequisite for this OTTO replay, and the
repository's synthetic fixture supports the smoke path.

| Gap found | Correction |
| --- | --- |
| Running the Stage 0 entry point by script path omitted the checkout from Python's import search path on the fresh environment. | The README uses `python -m scripts.stage0`. |
| The README's Stage 0 data-build path ran acceptance tests before setting the database DSN. | The PostgreSQL prerequisite now precedes the data rebuild command. |
| The first locked sync selected Python 3.12. | The instructions pin the reproduction environment to Python 3.11, matching the reference image's interpreter series. |
| The artifact corruption test required an ignored serving bundle before Stage 0 could generate any artifacts. | The test builds an isolated synthetic bundle and checks missing, corrupted, and restored model files in the temporary registry. |
| Stage 2 pins the archived Stage 0 manifest, whose artifact checksums include nondeterministic telemetry. | The baseline reconstruction command checks the rebuilt data and snapshot, restores the archived retrieval telemetry from the committed Stage 0 report, and checks the reconstructed manifest and epoch hashes against Stage 1. |
| The OTTO download example generated a directory other than the Stage 1 input in the next section. | The clean-room commands use `artifacts/stage0-otto` throughout. |
| The historical data build calculates per-window target coverage, including W3. | The holdout-safe instructions start from the checksum-pinned archive. |
| The generation step needs a specific registered run directory and a new Compose project to create an empty PostgreSQL volume. | The README identifies the verified run, builds the bundle, sets the mount and credentials, and gives the exact readiness and persistence probes. |

## Training and W2-dev evaluation

Both fits produced the Stage 2 model SHA-256
`8d06f0f97a3485540addeae9d6604b3fae3c948c2de2862d08d7de79e7cebd6d`.
The registered replay is
`1033fe51c4e3a44a94843b8b38ac5dbf91e7822eae0876c30a6e1264455fcc30`.
Its training counts and every W2-dev slice count and metric exactly matched
the Stage 2 record. The W2-dev population had 54,776 labeled queries, of which
12,234 retrieved the target. Another 12,205 queries had no next-click label.

| Strategy | HitRate@20 | MRR@20 | NDCG@20 |
| --- | ---: | ---: | ---: |
| `rule-v1` | 0.1963086023 | 0.1339625237 | 0.1484113796 |
| `lgbm-v1` | 0.1993573828 | 0.1424608041 | 0.1556729200 |

[Stage 2 lineage](stage2_training_evidence.json) · [Replay and serving evidence](stage4_reproduction_evidence.json)

## Local serving

The generation builder used the fresh registered run. Compose created a new
PostgreSQL 16.16 volume and mounted the new generation registry. On
2026-11-21 at 12:34:59 UTC, readiness reported both serving and release ready.
The API returned `rule-v1` from
`gen-9466a9a8cfb172b3ba4e8ceb3feb24a09810c677087f5c3e3bd985527a152497`
with persisted impression `6a393135-07bd-4bb1-a5f5-5468a3138276`.
The new generation ID reflects the reproduced run and bundle metadata.
Compose removed both containers and the disposable volume after verification.

## Historical promotion decision

The recorded W2-gate decision is
`466d0bb2fb3075a22266ed42a0fb9bff4887a411130621db9c7d35d503a9d684`.
The replay verified the signed record and reran the fixed `disposition`
function over its archived aggregates. The primary deltas were +0.003927993
HitRate@20 and +0.007453743 MRR@20. The head-popularity slice's HitRate@20
delta was -0.006076389 against the 0.005 absolute non-regression tolerance.
The disposition was rejected and the stable strategy remains `rule-v1`.
The W2-gate queries and labels remained closed.

To repeat, resolve the recorded ID in the original restricted release registry,
verify its HMAC-SHA256 using the release signing key, and pass the archived
record's `evaluation`, `lgbm-v1`, and `policy` to
`rankflow.release_gate.disposition`. The published decision and decisive
slice delta are sufficient to reproduce the rejection logic from the rules
in [the frozen policy](../configs/stage2_gate.json).

## Rollback and recovery

The Stage 3 three-process release drill exercises named rollback with an
isolated PostgreSQL schema. The Stage 3 restore drill exercises durable
recovery and checks the restored decision and audit rows. Both are repository
entry points for an independent replay. See the [release probes](../scripts/stage3_release.py)
and [restore commands](stage3_restore_evidence.md).
