"""Fetch the release identified by the official OTTO repository."""
import argparse
import gzip
from pathlib import Path, PurePosixPath
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from .ingestion import file_hash
from .pipeline import save_json

OFFICIAL_REPOSITORY = "https://github.com/otto-de/recsys-dataset"
DATASET = "otto/recsys-dataset"
ARCHIVE = "recsys-dataset.zip"


def extract_jsonl(archive, directory):
    hashes = {}
    with ZipFile(archive) as package:
        for target in ("train.jsonl", "test.jsonl"):
            members = [member for member in package.infolist() if not member.is_dir()
                       and PurePosixPath(member.filename).name in {target, target + ".gz"}]
            if len(members) != 1:
                raise ValueError(f"Expected exactly one {target} (plain or gzipped)")
            member = members[0]
            path = directory / target
            # Fixed output names avoid trusting archive paths.
            with package.open(member) as raw, path.open("wb") as output:
                if member.filename.endswith(".gz"):
                    with gzip.GzipFile(fileobj=raw) as decoded:
                        shutil.copyfileobj(decoded, output)
                else:
                    shutil.copyfileobj(raw, output)
            if not path.stat().st_size:
                raise ValueError(f"Downloaded {target} is empty")
            hashes[target] = file_hash(path)
    return hashes


def fetch(output):
    if output.exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as temp:
        directory = Path(temp)
        subprocess.run(["kaggle", "datasets", "download", "-d", DATASET, "-p", str(directory)],
                       check=True)
        archive = directory / ARCHIVE
        files = extract_jsonl(archive, directory)
        archive_hash = file_hash(archive)
        save_json(directory / "download_manifest.json", {
            "source": "otto_offline", "official_repository": OFFICIAL_REPOSITORY,
            "dataset": DATASET, "archive": ARCHIVE, "archive_sha256": archive_hash,
            "files": files,
        })
        directory.replace(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/otto"))
    args = parser.parse_args()
    fetch(args.output)
