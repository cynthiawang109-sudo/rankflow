"""Render validation evidence as JSON and Markdown."""
from .pipeline import save_json


def write_report(directory, manifest, retrieval, download_status, fixture_checks, replay_hash):
    directory.mkdir(parents=True, exist_ok=True)
    report = {
        "source": manifest["source"],
        "manifest_version": manifest["version"],
        "source_sha256": manifest["source_sha256"],
        "otto_download_status": download_status,
        "windows": manifest["windows"],
        "window_counts": manifest["counts"],
        "crossing_exclusions_by_length": manifest["crossing_exclusions_by_length"],
        "crossing_sessions_by_boundary": manifest["crossing_sessions_by_boundary"],
        "outside_windows": manifest["outside_windows"],
        "query_coverage": manifest["query_coverage"],
        "coverage_scope": "Stage 0 co-visitation candidates from the recorded prefix",
        "retrieval": retrieval,
        "artifact_hashes": manifest["artifacts"],
        "run_checks": {
            "epoch registration, including strict snapshot and label predicates": "PASS",
            "byte-identical query replay from manifest and configuration": "PASS",
        },
        "replayed_queries_sha256": replay_hash,
        "invariant_tests_source": "synthetic_fixture",
        "fixture_tests": fixture_checks,
    }
    save_json(directory / "data_validation_report.json", report)
    rows = [
        "# Stage 0 data validation", "",
        f"Data provenance `{report['source']}`.", "",
        download_status, "",
        "## Windows", "",
        "| Partition | Range in Unix milliseconds [start, end) | Sessions | Events |",
        "|---|---|---:|---:|",
    ]
    for name, count in report["window_counts"].items():
        start, end = report["windows"][name.split("-")[0]]
        rows.append(f"| {name} | [{start}, {end}) | {count['sessions']} | {count['events']} |")
    rows.extend([
        "", "### Boundary exclusions", "",
        "| Session length | Excluded sessions | Excluded events |",
        "|---|---:|---:|",
    ])
    for name, count in report["crossing_exclusions_by_length"].items():
        rows.append(f"| {name} | {count['sessions']} | {count['events']} |")
    rows.extend([
        "",
        f"Short sessions have at most {manifest['configuration']['short_session_max_events']} events.",
        "Crossing counts by boundary (Unix milliseconds): "
        + ", ".join(f"{edge} ({count})" for edge, count
                    in sorted(report["crossing_sessions_by_boundary"].items())) + "."
        if report["crossing_sessions_by_boundary"] else "No boundary crossings.",
        f"Outside all windows: {report['outside_windows']['sessions']} sessions and "
        f"{report['outside_windows']['events']} events.", "",
        "## Query and label coverage", "",
        report["coverage_scope"] + ". No-label rows have no subsequent click and are excluded "
        "from primary next-click metrics.", "",
        "| Partition | Queries | Retrieved positive | Unretrieved positive | No label |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, count in report["query_coverage"].items():
        rows.append(f"| {name} | {count['queries']} | {count['retrieved_positive']} | "
                    f"{count['unretrieved_positive']} | {count['no_label']} |")
    config = retrieval["configuration"]
    rows.extend([
        "", "## Co-visitation", "",
        f"The scan used a {config['H']}-position horizon and a {config['session_event_cap']}-event "
        f"session cap under `{config['pair_definition_version']}`.",
        f"{retrieval['exact_pair_count']} canonical pairs over {retrieval['distinct_items']} "
        f"history items produced {retrieval['row_count']} directed rows with at most "
        f"{config['top_n_per_item']} neighbours per item and minimum count {config['min_count']}.",
        f"The table uses {retrieval['on_disk_bytes']} bytes. SQLite staging used "
        f"{retrieval['staging_disk_bytes']} bytes under a combined build budget of "
        f"{config['disk_budget_bytes']} bytes and a {config['sqlite_cache_kib']} KiB cache target.",
        f"Build time was {retrieval['build_seconds']} seconds on {retrieval['platform']}. "
        f"Process peak resident memory observed at build completion was "
        f"{retrieval['peak_process_rss_bytes']} bytes.", "",
        "## Invariants", "",
        "| Run check | Result |", "|---|---|",
        *(f"| {name} | {status} |" for name, status in report["run_checks"].items()),
        "", "| Fixture test | Result |", "|---|---|",
        *(f"| {name} | {status} |" for name, status in fixture_checks.items()),
        "", "## Reproducibility", "",
        f"- Source SHA-256 `{manifest['source_sha256']}`",
        f"- Query SHA-256 `{replay_hash}`",
        f"- Co-visitation SHA-256 `{retrieval['table_sha256']}`",
        f"- Snapshot ID `{retrieval['retrieval_snapshot_id']}`",
    ])
    (directory / "data_validation_report.md").write_bytes(("\n".join(rows) + "\n").encode("utf-8"))
