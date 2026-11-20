"""Build and verify immutable, self-contained Alpha serving generations."""
import argparse
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from .data.ingestion import file_hash
from .features import FEATURE_NAMES, FEATURE_VERSION, feature_code_hash
from .retrieval import RetrievalConfig, Snapshot
from .strategies import RULE, RULE_CONFIG, RankingStrategy, load_model

FILES = (
    "evaluation_epoch.json", "data_manifest.json", "history.jsonl", "covisitation.jsonl",
    "strategy_report.json", "lgbm-v1.txt", "public_prefixes.json",
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def identity(manifest):
    return "gen-" + hashlib.sha256(encoded(manifest)).hexdigest()


def public_prefixes(directory):
    from .evaluate_retrieval import governed_sessions

    manifest = json.loads((directory / "data_manifest.json").read_text())
    if file_hash(directory / "sessions.jsonl") != manifest["artifacts"]["sessions.jsonl"]:
        raise ValueError("Session checksum mismatch")
    examples = {}
    for window in ("W2-dev", "W1"):
        examples[window] = []
        for row in governed_sessions(directory, window):
            events = [{key: event[key] for key in ("aid", "ts", "type")} for event in row["events"][:10]]
            if events:
                examples[window].append({"prefix_id": len(examples[window]), "window": window,
                                         "cutoff_ts": events[-1]["ts"], "events": events})
            if len(examples[window]) == 12:
                break
    return examples


def build(directory, training, registry, assigned_strategy=RULE.strategy_id):
    report = json.loads((training / "strategy_report.json").read_text())
    registry.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=registry) as temporary:
        target = Path(temporary) / "bundle"
        target.mkdir()
        for name in FILES[:-1]:
            source = training if name in {"strategy_report.json", "lgbm-v1.txt"} else directory
            shutil.copyfile(source / name, target / name)
        files = FILES
        run = training / "run.json"
        if run.is_file():
            shutil.copyfile(run, target / "run.json")
            files = (*FILES, "run.json")
        (target / "public_prefixes.json").write_bytes(encoded(public_prefixes(directory)))
        manifest = {
            "version": "serving-generation-v1", "assigned_strategy": assigned_strategy,
            "retrieval": report["retrieval"], "retrieval_snapshot_id": report["protocol"]["snapshot_id"],
            "compatibility": {"mode": "ranker-only", "feature_schema": FEATURE_VERSION,
                              "feature_names": FEATURE_NAMES, "feature_code_sha256": feature_code_hash()},
            "rule_configuration": RULE_CONFIG, "rule_configuration_sha256": RULE.artifact_hash,
            "checksums": {name: file_hash(target / name) for name in files},
        }
        generation_id = identity(manifest)
        (target / "manifest.json").write_bytes(encoded(manifest))
        Generation.load(target, generation_id)
        destination = registry / generation_id
        if destination.exists():
            Generation.load(destination)
        else:
            target.rename(destination)
        return destination


@dataclass(frozen=True)
class Generation:
    generation_id: str
    snapshot: Snapshot
    config: RetrievalConfig
    assigned: object
    challenger: object
    examples: dict
    model_path: Path | None = None

    @classmethod
    def load(cls, directory, expected_id=None, *, isolated=False):
        manifest = json.loads((directory / "manifest.json").read_bytes())
        generation_id = identity(manifest)
        if generation_id != (expected_id or directory.name) or manifest["version"] != "serving-generation-v1":
            raise ValueError("Serving generation identity mismatch")
        checksums = manifest["checksums"]
        valid_files = (set(FILES), {*FILES, "run.json"})
        if set(checksums) not in valid_files or any(file_hash(directory / name) != digest
                                                   for name, digest in checksums.items()):
            raise ValueError("Serving generation checksum mismatch")
        compatibility = manifest["compatibility"]
        if (compatibility["feature_schema"] != FEATURE_VERSION
                or tuple(compatibility["feature_names"]) != FEATURE_NAMES
                or compatibility["feature_code_sha256"] != feature_code_hash()):
            raise ValueError("Serving feature compatibility mismatch")
        snapshot = Snapshot.load(directory)
        model_path = directory / "lgbm-v1.txt"
        model = (RankingStrategy("lgbm-v1", "lightgbm", 1, "evaluated",
                                 checksums["lgbm-v1.txt"], None)
                 if isolated else load_model(model_path))
        report = json.loads((directory / "strategy_report.json").read_bytes())
        if (report["artifact_sha256"] != model.artifact_hash
                or report["feature_code_sha256"] != feature_code_hash()
                or report["feature_schema"] != FEATURE_VERSION
                or tuple(report["feature_names"]) != FEATURE_NAMES
                or report["retrieval"] != manifest["retrieval"]
                or report["protocol"]["snapshot_id"] != snapshot.snapshot_id
                or manifest["retrieval_snapshot_id"] != snapshot.snapshot_id
                or manifest["rule_configuration"] != RULE_CONFIG
                or manifest["rule_configuration_sha256"] != RULE.artifact_hash):
            raise ValueError("Serving lineage mismatch")
        if "run.json" in checksums:
            record = json.loads((directory / "run.json").read_bytes())
            lineage = dict(record["lineage"])
            run_id = lineage.pop("run_id")
            if (hashlib.sha256(encoded(lineage)).hexdigest() != run_id
                    or lineage["source"] != "otto_offline"
                    or lineage["artifact_sha256"] != model.artifact_hash
                    or lineage["retrieval_snapshot_id"] != snapshot.snapshot_id
                    or lineage["feature_code_sha256"] != feature_code_hash()):
                raise ValueError("Training run is incompatible with the serving bundle")
        strategies = {strategy.strategy_id: strategy for strategy in (RULE, model)}
        assigned = strategies[manifest["assigned_strategy"]]
        examples = json.loads((directory / "public_prefixes.json").read_bytes())
        if set(examples) != {"W1", "W2-dev"}:
            raise ValueError("Invalid Playground boundary")
        return cls(generation_id, snapshot, RetrievalConfig(**manifest["retrieval"]), assigned,
                   model if assigned == RULE else RULE, examples, model_path if isolated else None)



def cached_generation(source, cache):
    """Copy a complete immutable generation, verify it, then publish the directory."""
    identifier = source.name
    if cache is None:
        return Generation.load(source, isolated=True)
    destination = cache / identifier
    if destination.is_dir():
        return Generation.load(destination, isolated=True)
    cache.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=cache) as temporary:
        staging = Path(temporary)
        manifest = source / "manifest.json"
        shutil.copyfile(manifest, staging / manifest.name)
        checksums = json.loads((staging / manifest.name).read_bytes())["checksums"]
        if set(checksums) not in (set(FILES), {*FILES, "run.json"}):
            raise ValueError("Generation file inventory mismatch")
        for filename in checksums:
            shutil.copyfile(source / filename, staging / filename)
        generation = Generation.load(staging, identifier, isolated=True)
        try:
            staging.rename(destination)
        except OSError:
            if not destination.is_dir():
                raise
            return Generation.load(destination, isolated=True)
        return replace(generation, model_path=destination / "lgbm-v1.txt")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "training", "registry"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--candidate", action="store_true")
    args = parser.parse_args()
    destination = build(args.directory, args.training, args.registry,
                        "lgbm-v1" if args.candidate else RULE.strategy_id)
    if args.candidate:
        print(destination)
        return
    pointer = args.registry / "alpha.tmp"
    pointer.write_text(destination.name + "\n", encoding="ascii")
    pointer.replace(args.registry / "alpha.txt")
    print(destination)


if __name__ == "__main__":
    main()
