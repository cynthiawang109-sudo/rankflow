"""Recover the frozen Stage 0 manifest from a freshly rebuilt OTTO run."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from rankflow.data.ingestion import file_hash
from rankflow.data.pipeline import read_json, save_json
from rankflow.training_pipeline import BASELINE_PATH


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = args.directory
    baseline = read_json(BASELINE_PATH)["files_sha256"]
    recorded = read_json(BASELINE_PATH.with_name("data_validation_report_real.json"))
    manifest = read_json(directory / "data_manifest.json")
    epoch = read_json(directory / "evaluation_epoch.json")
    if any(file_hash(directory / name) != digest for name, digest in manifest["artifacts"].items()):
        raise ValueError("Rebuilt artifact differs from its own manifest")
    for name in ("history.jsonl", "sessions.jsonl", "queries.jsonl", "covisitation.jsonl"):
        if file_hash(directory / name) != recorded["artifact_hashes"][name]:
            raise ValueError(f"Rebuilt {name} differs from the original")

    with TemporaryDirectory(dir=directory) as scratch:
        staging = Path(scratch)
        retrieval = staging / "retrieval_manifest.json"
        fresh = read_json(directory / retrieval.name)
        historical = recorded["retrieval"]
        variable = {"build_seconds", "on_disk_bytes", "peak_process_rss_bytes", "platform", "staging_disk_bytes"}
        if {key: value for key, value in fresh.items() if key not in variable} != {
                key: value for key, value in historical.items() if key not in variable}:
            raise ValueError("Rebuilt retrieval metadata differs from the historical snapshot")
        save_json(retrieval, historical)
        manifest["artifacts"][retrieval.name] = file_hash(retrieval)
        dataset = staging / "data_manifest.json"
        save_json(dataset, manifest)
        epoch["dataset_manifest_hash"] = file_hash(dataset)
        registered = staging / "evaluation_epoch.json"
        save_json(registered, epoch)
        for path in (dataset, registered):
            if file_hash(path) != baseline[f"artifacts/stage0-otto/{path.name}"]:
                raise ValueError(f"Reconstructed {path.name} differs from the frozen baseline")
        (directory / retrieval.name).rename(directory / "retrieval_manifest.rebuild.json")
        for path in (retrieval, dataset, registered):
            path.replace(directory / path.name)
    print("Reconstructed the frozen Stage 0 manifest and evaluation epoch.")


if __name__ == "__main__":
    main()
