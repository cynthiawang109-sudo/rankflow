# Independent W2-dev replay

The replay used a fresh clone at `b945e6b`, a new lockfile environment,
CPython 3.11.18 on Windows build 26300, LightGBM 4.7.0, NumPy 2.4.6 and
psycopg 3.3.9. A separate disposable PostgreSQL 16.16 container started
with an empty data volume and zero public tables. W2-dev evaluation
runs offline from archive files and writes no PostgreSQL results.
Verification ran from `2026-11-21T14:18:43.707588+00:00` through
`2026-11-21T14:22:15.051165+00:00`.

The run verified SHA-256 and byte length for all 23 entries in the
[artifact manifest](artifact_manifest.md) before evaluation. It loaded
the archived stable bundle and verified the standalone archived model
had the same SHA-256 as the embedded challenger and registered run.
The stable TrafficConfig reproduced the Stage 4 checkpoint ID
`cfg-d48c54e3a82cb72dfab3cfa7b36e98f9f6500ebf9785bc4d4947f2f75900bed7`.

The source-file checks treated the OTTO snapshot and mixed session
archive as opaque bytes. The governed query reader selected W2-dev
records by window before decoding them. The replay used archived model
weights and W2-dev results. W2-gate and W3 evaluation remained sealed.

## Field-by-field comparison

Every displayed value is identical in the archive and replay at the
stored precision. The comparison also checks the complete evaluation
objects against the archived Stage 2 run and the Stage 4 reproduction
record. No metric tolerance was applied.

| Field | Archived | Replayed |
| --- | ---: | ---: |
| No-label queries | 12205 | 12205 |
| overall / sessions | 13226 | 13226 |
| overall / labeled | 54776 | 54776 |
| overall / retrieved | 12234 | 12234 |
| overall / candidate_coverage | 0.2233459909449394 | 0.2233459909449394 |
| overall / lgbm-v1 / HitRate@20 | 0.19935738279538484 | 0.19935738279538484 |
| overall / lgbm-v1 / MRR@20 | 0.14246080410483988 | 0.14246080410483988 |
| overall / lgbm-v1 / NDCG@20 | 0.15567292001012817 | 0.15567292001012817 |
| overall / rule-v1 / HitRate@20 | 0.19630860230757996 | 0.19630860230757996 |
| overall / rule-v1 / MRR@20 | 0.13396252373193315 | 0.13396252373193315 |
| overall / rule-v1 / NDCG@20 | 0.1484113796392154 | 0.1484113796392154 |
| prefix/cold / sessions | 6466 | 6466 |
| prefix/cold / labeled | 16434 | 16434 |
| prefix/cold / retrieved | 88 | 88 |
| prefix/cold / candidate_coverage | 0.00535475234270415 | 0.00535475234270415 |
| prefix/cold / lgbm-v1 / HitRate@20 | 0.0016429353778751369 | 0.0016429353778751369 |
| prefix/cold / lgbm-v1 / MRR@20 | 0.0008920339281892447 | 0.0008920339281892447 |
| prefix/cold / lgbm-v1 / NDCG@20 | 0.001044011739655195 | 0.001044011739655195 |
| prefix/cold / rule-v1 / HitRate@20 | 0.0013386880856760374 | 0.0013386880856760374 |
| prefix/cold / rule-v1 / MRR@20 | 0.00016200518208550336 | 0.00016200518208550336 |
| prefix/cold / rule-v1 / NDCG@20 | 0.0004096257508790894 | 0.0004096257508790894 |
| prefix/warm / sessions | 8947 | 8947 |
| prefix/warm / labeled | 38342 | 38342 |
| prefix/warm / retrieved | 12146 | 12146 |
| prefix/warm / candidate_coverage | 0.316780553961713 | 0.316780553961713 |
| prefix/warm / lgbm-v1 / HitRate@20 | 0.2841009858640655 | 0.2841009858640655 |
| prefix/warm / lgbm-v1 / MRR@20 | 0.20313946377525555 | 0.20313946377525555 |
| prefix/warm / lgbm-v1 / NDCG@20 | 0.22194936564460085 | 0.22194936564460085 |
| prefix/warm / rule-v1 / HitRate@20 | 0.27987585415471283 | 0.27987585415471283 |
| prefix/warm / rule-v1 / MRR@20 | 0.19131158538359966 | 0.19131158538359966 |
| prefix/warm / rule-v1 / NDCG@20 | 0.21184731995012568 | 0.21184731995012568 |
| session_length/21_to_100 / sessions | 892 | 892 |
| session_length/21_to_100 / labeled | 8920 | 8920 |
| session_length/21_to_100 / retrieved | 1848 | 1848 |
| session_length/21_to_100 / candidate_coverage | 0.20717488789237667 | 0.20717488789237667 |
| session_length/21_to_100 / lgbm-v1 / HitRate@20 | 0.17443946188340806 | 0.17443946188340806 |
| session_length/21_to_100 / lgbm-v1 / MRR@20 | 0.10843351835750728 | 0.10843351835750728 |
| session_length/21_to_100 / lgbm-v1 / NDCG@20 | 0.12364226926486462 | 0.12364226926486462 |
| session_length/21_to_100 / rule-v1 / HitRate@20 | 0.17298206278026906 | 0.17298206278026906 |
| session_length/21_to_100 / rule-v1 / MRR@20 | 0.10195746013073927 | 0.10195746013073927 |
| session_length/21_to_100 / rule-v1 / NDCG@20 | 0.11826930733037028 | 0.11826930733037028 |
| session_length/over_100 / sessions | 25 | 25 |
| session_length/over_100 / labeled | 250 | 250 |
| session_length/over_100 / retrieved | 20 | 20 |
| session_length/over_100 / candidate_coverage | 0.08 | 0.08 |
| session_length/over_100 / lgbm-v1 / HitRate@20 | 0.064 | 0.064 |
| session_length/over_100 / lgbm-v1 / MRR@20 | 0.021067169431875313 | 0.021067169431875313 |
| session_length/over_100 / lgbm-v1 / NDCG@20 | 0.030257150311666463 | 0.030257150311666463 |
| session_length/over_100 / rule-v1 / HitRate@20 | 0.064 | 0.064 |
| session_length/over_100 / rule-v1 / MRR@20 | 0.013606511376480416 | 0.013606511376480416 |
| session_length/over_100 / rule-v1 / NDCG@20 | 0.02469030244086194 | 0.02469030244086194 |
| session_length/up_to_20 / sessions | 12309 | 12309 |
| session_length/up_to_20 / labeled | 45606 | 45606 |
| session_length/up_to_20 / retrieved | 10366 | 10366 |
| session_length/up_to_20 / candidate_coverage | 0.22729465421216508 | 0.22729465421216508 |
| session_length/up_to_20 / lgbm-v1 / HitRate@20 | 0.2049730298644915 | 0.2049730298644915 |
| session_length/up_to_20 / lgbm-v1 / MRR@20 | 0.14978159078936523 | 0.14978159078936523 |
| session_length/up_to_20 / lgbm-v1 / NDCG@20 | 0.16262523652708502 | 0.16262523652708502 |
| session_length/up_to_20 / rule-v1 / HitRate@20 | 0.20159628119107134 | 0.20159628119107134 |
| session_length/up_to_20 / rule-v1 / MRR@20 | 0.14088209945467867 | 0.14088209945467867 |
| session_length/up_to_20 / rule-v1 / NDCG@20 | 0.15498502245582896 | 0.15498502245582896 |
| target_popularity/head / sessions | 635 | 635 |
| target_popularity/head / labeled | 1087 | 1087 |
| target_popularity/head / retrieved | 839 | 839 |
| target_popularity/head / candidate_coverage | 0.7718491260349586 | 0.7718491260349586 |
| target_popularity/head / lgbm-v1 / HitRate@20 | 0.6292548298068077 | 0.6292548298068077 |
| target_popularity/head / lgbm-v1 / MRR@20 | 0.4001710974659638 | 0.4001710974659638 |
| target_popularity/head / lgbm-v1 / NDCG@20 | 0.4533219393793182 | 0.4533219393793182 |
| target_popularity/head / rule-v1 / HitRate@20 | 0.6494940202391905 | 0.6494940202391905 |
| target_popularity/head / rule-v1 / MRR@20 | 0.3775208280642612 | 0.3775208280642612 |
| target_popularity/head / rule-v1 / NDCG@20 | 0.4408498059629389 | 0.4408498059629389 |
| target_popularity/tail / sessions | 8521 | 8521 |
| target_popularity/tail / labeled | 24629 | 24629 |
| target_popularity/tail / retrieved | 11395 | 11395 |
| target_popularity/tail / candidate_coverage | 0.46266596288927686 | 0.46266596288927686 |
| target_popularity/tail / lgbm-v1 / HitRate@20 | 0.4156076170368265 | 0.4156076170368265 |
| target_popularity/tail / lgbm-v1 / MRR@20 | 0.29917767764428993 | 0.29917767764428993 |
| target_popularity/tail / lgbm-v1 / NDCG@20 | 0.3262162052202465 | 0.3262162052202465 |
| target_popularity/tail / rule-v1 / HitRate@20 | 0.4079337366519144 | 0.4079337366519144 |
| target_popularity/tail / rule-v1 / MRR@20 | 0.2812767899563333 | 0.2812767899563333 |
| target_popularity/tail / rule-v1 / NDCG@20 | 0.31061667108026897 | 0.31061667108026897 |
| target_popularity/unseen / sessions | 9377 | 9377 |
| target_popularity/unseen / labeled | 29060 | 29060 |
| target_popularity/unseen / retrieved | 0 | 0 |
| target_popularity/unseen / candidate_coverage | 0.0 | 0.0 |
| target_popularity/unseen / lgbm-v1 / HitRate@20 | 0.0 | 0.0 |
| target_popularity/unseen / lgbm-v1 / MRR@20 | 0.0 | 0.0 |
| target_popularity/unseen / lgbm-v1 / NDCG@20 | 0.0 | 0.0 |
| target_popularity/unseen / rule-v1 / HitRate@20 | 0.0 | 0.0 |
| target_popularity/unseen / rule-v1 / MRR@20 | 0.0 | 0.0 |
| target_popularity/unseen / rule-v1 / NDCG@20 | 0.0 | 0.0 |

## Commands

In PowerShell, start a fresh local PostgreSQL 16.16 container and enter a
fresh checkout of the pinned revision. Set `RANKFLOW_ARCHIVE` to the archive
root and `RANKFLOW_MANIFEST` to the absolute path to the closure manifest.
The actual run used the following image and lockfile commands.

```powershell
docker run --rm -d --name rankflow-closure-replay -e POSTGRES_HOST_AUTH_METHOD=trust `
  -p 127.0.0.1:55437:5432 postgres:16@sha256:23fdb7b8156ad34bc663ed911f360764c5a5e237d6d70d1e379e025f63439a2f
$env:RANKFLOW_TEST_DATABASE_URL = "postgresql://postgres@127.0.0.1:55437/postgres"
$env:OMP_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
git checkout --detach b945e6b
uv sync --locked --offline --python 3.11
uv run --locked --offline python ../verify.py
docker stop rankflow-closure-replay
```

Use the Python body below for `../verify.py`. The offline flags use the
local package cache.

```python
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
import re
import sys

import psycopg

from rankflow.data.ingestion import file_hash
from rankflow.generation import Generation, encoded
from rankflow.traffic import TrafficConfigSnapshot
from rankflow.training_pipeline import paired_evaluation, pinned_inputs, queries, read_json

root = Path(os.environ['RANKFLOW_ARCHIVE']).resolve()
manifest = Path(os.environ['RANKFLOW_MANIFEST']).read_text(encoding='utf-8')
rows = re.findall(r'^\| `([^`]+)` \| (\d+) \| `([0-9a-f]{64})` \|', manifest, re.MULTILINE)
assert rows
print(datetime.now(timezone.utc).isoformat(), platform.platform(), sys.version, flush=True)
print({name: version(name) for name in ('lightgbm', 'numpy', 'psycopg')}, flush=True)
with psycopg.connect(os.environ['RANKFLOW_TEST_DATABASE_URL']) as db:
    count = db.execute("SELECT count(*) FROM pg_tables WHERE schemaname = 'public'").fetchone()[0]
    assert count == 0
    print(f'PostgreSQL {db.info.server_version}, public tables {count}', flush=True)

for relative, size, digest in rows:
    path = Path(relative) if relative in ('rankflow/features.py', 'uv.lock') else root / relative
    assert path.stat().st_size == int(size) and file_hash(path) == digest, relative
    print(f'Verified {relative}', flush=True)

paths = {Path(relative) for relative, _, _ in rows}
stable_paths = {path.parent for path in paths if path.name == 'manifest.json'}
run_paths = {path for path in paths if path.name == 'run.json'}
stable_path, = stable_paths
run_path, = run_paths
stable = Generation.load(root / stable_path)
assert stable.assigned.strategy_id == 'rule-v1'
traffic_path, = (path for path in paths if path.name == 'stable_traffic_config.json')
traffic = TrafficConfigSnapshot(**read_json(root / traffic_path))
assert traffic.stable_generation_id == stable.generation_id
assert encoded(asdict(traffic)) == (root / traffic_path).read_bytes()
assert traffic.config_id == 'cfg-d48c54e3a82cb72dfab3cfa7b36e98f9f6500ebf9785bc4d4947f2f75900bed7'
data, = {root / path.parent for path in paths if path.name == 'retrieval_manifest.json'}
_, _, _, snapshot, config = pinned_inputs(data)
assert stable.snapshot.snapshot_id == snapshot.snapshot_id and stable.config == config
record = read_json(root / run_path)
assert stable.challenger.artifact_hash == record['lineage']['artifact_sha256']
assert stable.challenger.artifact_hash == file_hash(root / run_path.with_name('lgbm-v1.txt'))
actual, _ = paired_evaluation(queries(data, snapshot, 'W2-dev'), snapshot, config, stable.challenger,
                              reference=stable.assigned)
assert actual == record['evaluation']
assert actual == read_json(Path('docs/stage4_reproduction_evidence.json'))['training_and_w2_dev']['evaluation']
Path('../verified_result.json').write_text(json.dumps(actual, indent=2), encoding='utf-8')
print(f'All {len(rows)} manifest entries and all evaluation fields match', flush=True)
print(datetime.now(timezone.utc).isoformat(), flush=True)
```
