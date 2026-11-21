# Stage 3 PostgreSQL backup and restore

The drill used two disposable PostgreSQL 16.10 containers on loopback.
The source and target each started with a database created from `template0`.
The API used one database for the control plane and the event store. Recovery
used a fresh generation directory and empty artifact cache. The existing stable
generation and signing key were supplied separately from the database archive.

| Drill step | Expected | Observed |
| --- | --- | --- |
| Backup | Capture an epoch, traffic history, signed audit, decisions and feedback in a PostgreSQL custom-format archive. | `pg_dump -Fc` produced a 27,298-byte archive. |
| Clean restore | Restore the checkpoint into the second database and preserve row contents. | `pg_restore --single-transaction --exit-on-error` succeeded. The restored contents matched one epoch, two configs, one pointer, one traffic audit row, two signed audit rows, one decision and one feedback event. |
| Audit verification | Verify signatures with the original signing key and match the publish audit to its signed operation. | Both HMACs matched. The signed publish matched the traffic audit operation ID, config ID and revision. |
| Stable serving | Start the application with an empty cache, load the restored pointer and persist a stable recommendation. | Readiness reported serving ready. The API served `rule-v1` from generation `gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65` at the restored config for revision 1 and returned a persisted impression ID. |
| Recovery point | Recover the backup checkpoint and account for a committed post-backup write. | One committed post-backup decision was absent from the restored database. The observed RPO was **0.547 s**, from the response confirming the backed-up feedback checkpoint to simulated source loss after the later decision. |
| Recovery time | Verify the restored rows and signatures, cold-load the generation and complete a durable recommendation. | The observed RTO was **87.766 s**, from simulated source loss to the successful persisted recommendation. This included restore, integrity checks, artifact staging and startup. Container provisioning and artifact retrieval from remote storage were outside the measured interval. |

To repeat from the repository root, start two disposable PostgreSQL containers
with local `postgres` access and published loopback ports, then run this command
with their names and connection strings. The script creates and cleans up its
own databases, and expects the existing Stage 1 Alpha generation on disk.

```powershell
uv run --locked python -m scripts.stage3_restore rankflow-stage3-source rankflow-stage3-restore --source-dsn postgresql://postgres@127.0.0.1:55436/postgres --restore-dsn postgresql://postgres@127.0.0.1:55437/postgres
```
