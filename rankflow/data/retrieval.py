"""Exact SQLite aggregation and deterministic pruned snapshot export."""
from contextlib import closing
import heapq
import json
import os
import platform
import sqlite3
from time import perf_counter

from .ingestion import write_row


class DiskBudgetExceeded(ValueError):
    pass


def session_pairs(events, horizon, session_cap):
    aids = [event["aid"] for event in events[:session_cap]]
    return {
        (min(aid, other), max(aid, other))
        for index, aid in enumerate(aids)
        for other in aids[index + 1:index + 1 + horizon]
        if aid != other
    }


def peak_rss_bytes():
    if os.name == "nt":
        import psutil

        return psutil.Process().memory_info().peak_wset
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return rss if platform.system() == "Darwin" else rss * 1024


def build_snapshot(sessions, directory, config, source):
    started = perf_counter()
    if any(type(config[key]) is not int or config[key] <= 0 for key in (
        "H", "session_event_cap", "disk_budget_bytes", "sqlite_cache_kib",
        "top_n_per_item", "min_count", "candidate_cap",
    )):
        raise ValueError("Retrieval capacities must be positive integers")

    database = directory / "build.sqlite"
    output = directory / "covisitation.jsonl"
    budget = config["disk_budget_bytes"]
    result = {"source": source, "store": "SQLite", "configuration": config}
    completed = False
    try:
        with closing(sqlite3.connect(database)) as conn:
            # The database is disposable staging. Disable separate journal files and
            # cap SQLite pages before any write. Queries use indexed scans.
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA temp_store=FILE")
            conn.execute(f"PRAGMA cache_size=-{config['sqlite_cache_kib']}")
            page_size = conn.execute("PRAGMA page_size").fetchone()[0]
            if budget < page_size:
                raise DiskBudgetExceeded("Co-visitation disk budget is smaller than a SQLite page")
            conn.execute(f"PRAGMA max_page_count={budget // page_size}")
            conn.execute("""CREATE TABLE pairs (
                         a INTEGER, b INTEGER, n INTEGER NOT NULL,
                         PRIMARY KEY (a, b)) WITHOUT ROWID""")
            conn.execute("CREATE INDEX by_second ON pairs (b, a)")
            conn.execute("CREATE TABLE items (aid INTEGER PRIMARY KEY)")
            for _, events in sessions:
                conn.executemany("INSERT OR IGNORE INTO items VALUES (?)",
                                 ((event["aid"],) for event in events))
                conn.executemany(
                    """INSERT INTO pairs VALUES (?, ?, 1)
                       ON CONFLICT(a, b) DO UPDATE SET n = n + 1""",
                    sorted(session_pairs(events, config["H"], config["session_event_cap"])),
                )
            conn.commit()
            staging_size = database.stat().st_size
            rows = 0
            exported_size = 0
            with output.open("wb") as stream:
                for (aid,) in conn.execute("SELECT aid FROM items ORDER BY aid"):
                    neighbours = conn.execute(
                        """SELECT b, n FROM pairs WHERE a = ? AND n >= ?
                           UNION ALL
                           SELECT a, n FROM pairs WHERE b = ? AND n >= ?""",
                        (aid, config["min_count"], aid, config["min_count"]),
                    )
                    for other, count in heapq.nsmallest(
                        config["top_n_per_item"], neighbours, key=lambda row: (-row[1], row[0])
                    ):
                        row = {"aid": aid, "neighbour_aid": other, "count": count, "source": source}
                        encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
                        exported_size += len(encoded)
                        if staging_size + exported_size > budget:
                            raise DiskBudgetExceeded("Co-visitation staging and export exceed disk budget")
                        stream.write(encoded)
                        rows += 1
            result.update(
                row_count=rows,
                exact_pair_count=conn.execute("SELECT COUNT(*) FROM pairs").fetchone()[0],
                distinct_items=conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
                on_disk_bytes=exported_size,
                staging_disk_bytes=staging_size,
                peak_process_rss_bytes=peak_rss_bytes(),
                platform=platform.platform(),
                build_seconds=round(perf_counter() - started, 6),
            )
        completed = True
        return result
    except (DiskBudgetExceeded, sqlite3.OperationalError) as error:
        if not isinstance(error, DiskBudgetExceeded) and getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_FULL:
            raise
        with (directory / "disk_budget_abort.json").open("w", encoding="utf-8", newline="\n") as stream:
            write_row(stream, {**result, "status": "aborted", "reason": str(error),
                               "staging_disk_bytes": database.stat().st_size if database.exists() else 0})
        raise DiskBudgetExceeded(f"Co-visitation disk budget ({budget} bytes): {error}") from error
    finally:
        database.unlink(missing_ok=True)
        if not completed:
            output.unlink(missing_ok=True)


def candidate_inputs(query, neighbours, cap):
    """Prepare Stage 0 co-visitation candidate inputs from the recorded prefix."""
    items = {}
    for event in reversed(query["prefix_events"]):
        for aid in neighbours(event["aid"]):
            items.setdefault(aid, None)
            if len(items) == cap:
                return list(items)
    return list(items)
