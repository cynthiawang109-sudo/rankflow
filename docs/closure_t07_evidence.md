# T07 incompatible-schema replay isolation

The local PostgreSQL 16.16 drill used the archived Stage 4 stable bundle
`gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65`
and its first governed W2-dev prefix. A temporary copy declared schema
`session-features-incompatible-t07-v1`, added `t07_extra_column` to
the ordered feature names, and supplied an incompatible transform digest.
The member files and checksums were copied unchanged. Recomputing the
manifest identity produced
`gen-8b41f8adbfdaa949b42b13ee5d3d22736344be6dc12522c52d0de99ee0ff3b00`.

The drill invoked the same `replay_bundles` entry point as the offline CLI.
It paused at candidate admission to synchronize a concurrent recommendation.
The real candidate loader rejected the manifest before the historical
ranking or evaluation function was called. The CLI wrote a separate
`.rejected.json` evidence record at `2026-11-21T14:18:19.990759+00:00`
with both identities, mode `candidate_offline_replay`, population
`W2-dev`, status `rejected`, and reason
`Serving feature compatibility mismatch`.

| Request | Persisted impression | Served results, in rank order |
| --- | --- | --- |
| Before admission attempt | `2018541b-f2d3-4136-9bed-082c58c8a2db` | 152547 (1.0), 670006 (0.5) |
| While candidate admission was paused | `3dca1c2c-10e9-497a-acee-c30e62809470` | 152547 (1.0), 670006 (0.5) |
| After rejection | `65126033-f1a8-4a53-bb7a-0e0fd829aed0` | 152547 (1.0), 670006 (0.5) |

All three responses had identical items, scores and source provenance,
with `rule-v1`, the stable generation, and no fallback. PostgreSQL held
three stable impressions, three decisions and three outbox rows. The
test joined decision and outbox identities to the exact three impressions
and verified the assigned and served strategies. The incompatible
generation had zero impressions, decisions and outbox rows. Shadow
observations and candidate evaluation files both numbered zero.

The pre-attempt stable impression and decision retained their original
row values. File SHA-256 values matched before and after for the
stable bundle, the incompatible bundle, the two neighboring generation
bundles, the archived W2-dev evaluation record and the pre-existing
evaluation fixture. The temporary results directory contained that original
fixture and the rejection evidence. Earlier [Stage 2 evidence](stage2_exit_evidence.md)
records a successful labeled full-generation replay for compatible inputs.

Re-run with `RANKFLOW_TEST_DATABASE_URL` pointing at disposable PostgreSQL
and `RANKFLOW_T07_STABLE` set to the archived stable bundle directory:

```powershell
uv run --locked python -m unittest tests.test_closure_t07 -v
```

The archived-bundle drill passed 1 test, with 0 failed and 0 skipped.
The default suite substitutes a synthetic stable fixture and still exercises
real checksums, candidate admission and PostgreSQL persistence.
