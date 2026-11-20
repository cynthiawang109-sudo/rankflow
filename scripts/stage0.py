"""Build and validate Stage 0 data or reproduce a recorded query set."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rankflow.data.ingestion import file_hash
from rankflow.data.pipeline import FIXTURE, build_run, read_config, replay_queries
from rankflow.data.report import write_report


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args):
        super().__init__(*args)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id().rsplit(".", 1)[-1])


def fixture_evidence():
    suite = unittest.defaultTestLoader.discover("tests")
    expected = suite.countTestCases()
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    if not result.wasSuccessful() or expected == 0 or len(result.passed) != expected:
        raise SystemExit("The fixture suite did not pass. Validation report was not published.")
    return dict.fromkeys(sorted(result.passed), "PASS")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/stage0.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)

    build = commands.add_parser("build")
    build.add_argument("--profile", choices=["fixture", "otto"], default="fixture")
    build.add_argument("--input", type=Path)
    build.add_argument("--download-manifest", type=Path)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--report-dir", type=Path)

    replay = commands.add_parser("replay")
    replay.add_argument("--run", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = read_config(args.config)
    if args.command == "replay":
        replay_queries(args.run, args.output, config)
        return
    if args.profile == "otto" and (not args.input or not args.download_manifest):
        build.error("--profile otto requires --input and --download-manifest")
    report_dir = args.report_dir or args.output
    if args.profile == "otto" and report_dir.resolve().is_relative_to(Path("docs").resolve()):
        build.error("Write OTTO data validation reports to the ignored artifacts directory")
    evidence = fixture_evidence()
    manifest, retrieval, download_status = build_run(
        args.input or FIXTURE, args.output, config, args.profile, args.download_manifest,
    )
    with TemporaryDirectory() as temp:
        replayed = Path(temp) / "queries.jsonl"
        replay_queries(args.output, replayed, config)
        write_report(report_dir, manifest, retrieval, download_status, evidence, file_hash(replayed))


if __name__ == "__main__":
    main()
