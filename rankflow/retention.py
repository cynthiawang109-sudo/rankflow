"""Expire pseudonymous demo records after the configured retention interval."""
from argparse import ArgumentParser
from datetime import timedelta
import json
import os

from .store import PostgresStore


def expire(store, age, limit=1000):
    if age.total_seconds() <= 0 or not 1 <= limit <= 10000:
        raise ValueError("Retention age and batch size must be positive and bounded")
    if age < max(store.ack_window, store.attribution_window):
        raise ValueError("Retention must exceed acknowledgement and attribution windows")
    with store.connect() as conn:
        expired = conn.execute("""
            SELECT i.id FROM impressions i
            WHERE i.created_at < statement_timestamp() - %s AND NOT EXISTS (
                SELECT 1 FROM outbox o WHERE o.impression_id = i.id AND o.delivered_at IS NULL
            )
            ORDER BY i.created_at LIMIT %s FOR UPDATE OF i SKIP LOCKED
            """, (age, limit)).fetchall()
        ids = [row["id"] for row in expired]
        delivered = conn.execute("""
            DELETE FROM delivered_events WHERE event_id IN (
                SELECT event_id FROM outbox WHERE impression_id = ANY(%s)
            )
            """, (ids,)).rowcount
        for table in ("feedback_events", "acknowledgements", "shadow_observations", "outbox", "decisions"):
            conn.execute(f"DELETE FROM {table} WHERE impression_id = ANY(%s)", (ids,))
        impressions = conn.execute("DELETE FROM impressions WHERE id = ANY(%s)", (ids,)).rowcount
    return {"impressions_deleted": impressions, "delivery_payloads_deleted": delivered}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=int(os.getenv("RANKFLOW_RETENTION_DAYS", "30")))
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()
    store = PostgresStore(os.environ["RANKFLOW_DATABASE_URL"])
    print(json.dumps(expire(store, timedelta(days=args.days), args.batch_size)))


if __name__ == "__main__":
    main()
