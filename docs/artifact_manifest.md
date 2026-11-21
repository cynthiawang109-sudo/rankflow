# RankFlow closure artifact manifest

## Archive layout

Paths below are relative to the archive root, using the original workspace layout. The
dataset and model bodies are kept in the local artifact archive outside Git. Use
the checksum and byte length together when transferring these files to another machine.
The Stage 1 manifest pins the original Stage 0 inputs. The Stage 2 registered run
and Stage 4 deployment record identify the original model and stable generation.

| Artifact | Bytes | SHA-256 | Archive file timestamp (UTC) |
| --- | ---: | --- | --- |
| `data/otto/download_manifest.json` | 450 | `36bda14e1f11cf5aaeb577260ea4041d300bbca278a479f6d36d20ad293c3386` | 2026-11-20 04:23:26 |
| `data/otto/recsys-dataset.zip` | 2127848819 | `d2ff7ce4b709ab6bff96adda843e42c4d094ae17d510e84822e4a9d31bbca888` | 2023-02-13 18:44:45 |
| `data/otto/test.jsonl` | 750426722 | `ff413623d47ba0d0cfb9703accb9148ed32664a81c3930ffae8bd118b5741848` | 2026-11-20 04:23:10 |
| `data/otto/train.jsonl` | 11307535945 | `06716132f1ab1d500f1515ba2c16187d7b0e98066ca66d33b95f022f8c3a340d` | 2026-11-20 04:21:48 |
| `artifacts/stage0-otto/covisitation.jsonl` | 97005269 | `2505618567cf2d8d5c9c73c1b44343efa25e005f529655145e6d15dc6ca088a0` | 2026-11-20 04:49:34 |
| `artifacts/stage0-otto/data_manifest.json` | 4289161 | `b4ce68b9761b403f895acf3c77d7748a8634034abcf12fa701e5d44a05a86b00` | 2026-11-20 04:51:08 |
| `artifacts/stage0-otto/evaluation_epoch.json` | 655 | `78bfc10ac838f5d106acc277bb2b7c084def9fe823cb4b16d6162ac953fe89a3` | 2026-11-20 04:51:19 |
| `artifacts/stage0-otto/history.jsonl` | 16116835 | `277ce29ac2cd8d93d3408237506ee6d42ee9b7f6b2ef19440e999f4fba69557b` | 2026-11-20 04:48:05 |
| `artifacts/stage0-otto/retrieval_manifest.json` | 889 | `a546300791a4b13bd95ac30f4d0dd71b0d5fde4d650df44818220d9ef7fbd4bf` | 2026-11-20 04:49:34 |
| `artifacts/stage0-otto/sessions.jsonl` | 238825399 | `9fb2d0a3249720c94e2228b3453ad24c919669f016f55cc606ce0fb650607200` | 2026-11-20 04:48:05 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/covisitation.jsonl` | 97005269 | `2505618567cf2d8d5c9c73c1b44343efa25e005f529655145e6d15dc6ca088a0` | 2026-11-20 13:09:29 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/data_manifest.json` | 4289161 | `b4ce68b9761b403f895acf3c77d7748a8634034abcf12fa701e5d44a05a86b00` | 2026-11-20 13:09:28 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/evaluation_epoch.json` | 655 | `78bfc10ac838f5d106acc277bb2b7c084def9fe823cb4b16d6162ac953fe89a3` | 2026-11-20 13:09:28 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/history.jsonl` | 16116835 | `277ce29ac2cd8d93d3408237506ee6d42ee9b7f6b2ef19440e999f4fba69557b` | 2026-11-20 13:09:28 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/lgbm-v1.txt` | 92970 | `8d06f0f97a3485540addeae9d6604b3fae3c948c2de2862d08d7de79e7cebd6d` | 2026-11-20 13:09:29 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/manifest.json` | 1697 | `826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65` | 2026-11-20 13:09:46 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/public_prefixes.json` | 8723 | `f542b6e0711b32512627689277a0573042bf2e6f6af573906a6c96bb6c0d7d2c` | 2026-11-20 13:09:45 |
| `artifacts/stage2/generations/gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65/strategy_report.json` | 3976 | `8d1de5a1418df26b393d6265a7370c4f5b5d4fd638767ba5bea1ef877cbb2517` | 2026-11-20 13:09:29 |
| `artifacts/stage2/training/156bb1b48bf3aa4c1d8de6b935a25aa323bc0f5c10a294a69853077f41a94b15-verified/lgbm-v1.txt` | 92970 | `8d06f0f97a3485540addeae9d6604b3fae3c948c2de2862d08d7de79e7cebd6d` | 2026-11-20 14:34:45 |
| `artifacts/stage2/training/156bb1b48bf3aa4c1d8de6b935a25aa323bc0f5c10a294a69853077f41a94b15-verified/run.json` | 4762 | `73707fda1f725afe8b956820b12f7cc95db8fd7597203db0a7b08d3c3589ae66` | 2026-11-20 14:49:04 |
| `rankflow/features.py` | 2262 | `cc885ae447b4a1b9b066e082d990db7a070ebb3cee5f8b2674b3e6f514af071d` | 2026-11-20 13:05:05 |
| `artifacts/stage2/stable_traffic_config.json` | 332 | `df3eb5fc5e4973bceca98930ae1e01357852b1541506a871a64ed98f520e8d0b` | 2026-11-21 14:17:05 |
| `uv.lock` | 200249 | `3d6d133e828eb72cef28bcdaae709e8b6f6af9ee1161446dc7ec087b00b7b984` | 2026-11-20 13:05:49 |

## Provenance and deterministic identities

- **OTTO source.** The Stage 0 fetch used the OTTO recsys dataset ZIP and extracted
  its original train and test files. The download manifest records the publisher
  and the pinned source hashes. Archive timestamps above are observed file times.
  [Stage 0 data quality report](stage0_data_quality_report.md)
- **W1 and W2-dev.** The Stage 0 OTTO pipeline produced the session archive, epoch,
  data manifest and retrieval artifacts from the pinned OTTO inputs and
  `configs/stage0.yaml`. The snapshot ID is
  `cd5b998f1172df6d53ce28560fe1d9a79ca4086759c8830b3a0246187ba357a9`.
  Regenerate only governed W1 or W2-dev query streams with
  `rankflow.evaluate_retrieval.queries(directory, snapshot, window)`. The manifest
  pins membership and query policy, and the epoch pins the original query
  manifest digest `0101abfbc038bf4c36a1dc7e59a7307c77cc79311d75a15209537cff445fb670`.
  W1 and W2-dev share this lineage. [Stage 1 baseline](stage1_baseline_manifest.md)
- **Archived lgbm-v1.** The Stage 2 frozen registration used W1, the pinned
  retrieval snapshot, the recorded LambdaRank configuration and the
  session-features-v1 transform. Its original code revision, inputs, model hash
  and W2-dev metrics are recorded in the archived run.json.
  [Stage 2 training lineage](stage2_training_evidence.json)
- **Feature schema.** The Stage 1 baseline froze the version and ordered names
  defined by `rankflow/features.py` on 2026-11-20. The transform derives its
  prefix and candidate features from the governed prefix events, W0 retrieval
  snapshot and source ranks. The stable bundle manifest and archived Stage 2
  run pin the exact source digest. [Stage 1 baseline](stage1_baseline_manifest.md)
- **Stable rule-v1.** The Stage 4 deployment on 2026-11-21 used the listed
  Stage 2 registry bundle. Its manifest pins the rule weights, feature schema
  and transform hash, retrieval settings and member bytes. The embedded
  lgbm-v1 bytes match the archived model SHA-256.
  [Stage 4 deployment](stage4_deployment.md)
- **Stable TrafficConfig.** The closure sprint serialized the Stage 4 stable
  rescue configuration from `infra/stage4_entry.py` and the
  `TrafficConfigSnapshot` defaults as sorted compact UTF-8 JSON with no
  newline. Its ID matches the restored Stage 4 checkpoint and named rollback.
  [Stage 4 reliability evidence](stage4_reliability_evidence.json)

The TrafficConfig can be reconstructed byte-for-byte from this single line.
Write it as UTF-8 without a BOM or trailing newline.

```json
{"canary_generation_id":null,"canary_percent":0,"experiment_id":"alpha","guardrail_mode":"synthetic_operational","guardrail_policy_version":"stage2-v1","routing_salt_id":"v1","shadow_generation_id":null,"shadow_mode":null,"stable_generation_id":"gen-826a2cf8b370f7c6fb55c22cf299279c034298e744dc21585c0dca1b7c6f0c65","state":"draft"}
```

See [independent W2-dev replay](closure_replay_evidence.md) for verification.
