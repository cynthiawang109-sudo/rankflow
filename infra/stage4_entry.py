"""Fetch immutable generation files and launch the normal API factory."""
import json
import os
from pathlib import Path

import boto3
from psycopg.conninfo import make_conninfo

from rankflow.generation import FILES


root = Path("/tmp/rankflow")
root.mkdir(mode=0o700, exist_ok=True)
registry = root / "generations"
stable = os.environ["RANKFLOW_STABLE_ID"]
bucket = os.environ["RANKFLOW_BUNDLE_BUCKET"]
s3 = boto3.client("s3")
for identifier in {stable, os.environ["RANKFLOW_FIXTURE_ID"]}:
    directory = registry / identifier
    directory.mkdir(parents=True, exist_ok=True)
    prefix = f"generations/{identifier}"
    manifest_file = directory / "manifest.json"
    s3.download_file(bucket, f"{prefix}/manifest.json", str(manifest_file))
    names = json.loads(manifest_file.read_bytes())["checksums"]
    if set(names) not in (set(FILES), {*FILES, "run.json"}):
        raise ValueError("Invalid generation file list")
    for name in names:
        s3.download_file(bucket, f"{prefix}/{name}", str(directory / name))
rescue = root / "rescue.json"
rescue.write_text(json.dumps({"stable_generation_id": stable}), encoding="utf-8")
salts = root / "salts.json"
salts.write_text(json.dumps({"v1": os.environ.pop("RANKFLOW_ROUTING_KEY")}), encoding="utf-8")
os.environ.update(
    RANKFLOW_GENERATION=str(registry / stable),
    RANKFLOW_RESCUE_CONFIG=str(rescue),
    RANKFLOW_ROUTING_SALTS=str(salts),
    RANKFLOW_ARTIFACT_CACHE=str(root / "cache"),
    RANKFLOW_DATABASE_URL=make_conninfo(
        host=os.environ["RANKFLOW_DB_HOST"], dbname="rankflow", sslmode="require",
        user=os.environ.pop("RANKFLOW_DB_USER"), password=os.environ.pop("RANKFLOW_DB_PASSWORD"),
    ),
)
os.execv("/app/.venv/bin/uvicorn", [
    "uvicorn", "rankflow.api:from_environment", "--factory", "--host", "0.0.0.0",
    "--port", "8000", "--no-access-log",
])
