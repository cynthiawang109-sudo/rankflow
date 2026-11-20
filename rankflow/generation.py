"""Build and verify immutable, self-contained Alpha serving generations."""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from .data.ingestion import file_hash
from .features import FEATURE_NAMES, FEATURE_VERSION, feature_code_hash
from .retrieval import RetrievalConfig, Snapshot
from .strategies import RULE, RULE_CONFIG, load_model

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


def build(directory, training, registry):
    report = json.loads((training / "strategy_report.json").read_text())
    registry.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=registry) as temporary:
        target = Path(temporary) / "bundle"
        target.mkdir()
        for name in FILES[:-1]:
            source = training if name in {"strategy_report.json", "lgbm-v1.txt"} else directory
            shutil.copyfile(source / name, target / name)
        (target / "public_prefixes.json").write_bytes(encoded(public_prefixes(directory)))
        manifest = {
            "version": "serving-generation-v1", "assigned_strategy": RULE.strategy_id,
            "retrieval": report["retrieval"], "retrieval_snapshot_id": report["protocol"]["snapshot_id"],
            "compatibility": {"mode": "ranker-only", "feature_schema": FEATURE_VERSION,
                              "feature_names": FEATURE_NAMES, "feature_code_sha256": feature_code_hash()},
            "rule_configuration": RULE_CONFIG, "rule_configuration_sha256": RULE.artifact_hash,
            "checksums": {name: file_hash(target / name) for name in FILES},
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

    @classmethod
    def load(cls, directory, expected_id=None):
        manifest = json.loads((directory / "manifest.json").read_bytes())
        generation_id = identity(manifest)
        if generation_id != (expected_id or directory.name) or manifest["version"] != "serving-generation-v1":
            raise ValueError("Serving generation identity mismatch")
        checksums = manifest["checksums"]
        if set(checksums) != set(FILES) or any(file_hash(directory / name) != checksums[name] for name in FILES):
            raise ValueError("Serving generation checksum mismatch")
        compatibility = manifest["compatibility"]
        if (compatibility["feature_schema"] != FEATURE_VERSION
                or tuple(compatibility["feature_names"]) != FEATURE_NAMES
                or compatibility["feature_code_sha256"] != feature_code_hash()):
            raise ValueError("Serving feature compatibility mismatch")
        snapshot = Snapshot.load(directory)
        model = load_model(directory / "lgbm-v1.txt")
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
        strategies = {strategy.strategy_id: strategy for strategy in (RULE, model)}
        assigned = strategies[manifest["assigned_strategy"]]
        examples = json.loads((directory / "public_prefixes.json").read_bytes())
        if set(examples) != {"W1", "W2-dev"}:
            raise ValueError("Invalid Playground boundary")
        return cls(generation_id, snapshot, RetrievalConfig(**manifest["retrieval"]), assigned,
                   model if assigned == RULE else RULE, examples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("directory", "training", "registry"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    destination = build(args.directory, args.training, args.registry)
    pointer = args.registry / "alpha.tmp"
    pointer.write_text(destination.name + "\n", encoding="ascii")
    pointer.replace(args.registry / "alpha.txt")
    print(destination)


if __name__ == "__main__":
    main()
