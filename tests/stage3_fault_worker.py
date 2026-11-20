"""Subprocess targets for local simulated scorer and transaction failures."""
import json
import os
import sys
from threading import Event

from rankflow.store import PostgresStore


def inference():
    for message in sys.stdin.buffer:
        path, _, rows = json.loads(message)
        if rows and path == "hang":
            Event().wait()
        if rows and path == "crash":
            os._exit(23)
        print(json.dumps([0] * len(rows)), flush=True)


def transaction(operation):
    class InterruptedStore(PostgresStore):
        def connect(self):
            connection = super().connect()

            class InterruptedTransaction:
                def __enter__(self):
                    connection.__enter__()
                    return self

                def __exit__(self, *exc):
                    return connection.__exit__(*exc)

                def execute(self, statement, *args):
                    result = connection.execute(statement, *args)
                    if statement.startswith(checkpoint):
                        print("transaction_open", flush=True)
                        Event().wait()
                    return result

            return InterruptedTransaction()

    checkpoint = {"persist": "INSERT INTO decisions", "drain": "INSERT INTO delivered_events"}[operation]
    store = InterruptedStore(os.environ["RANKFLOW_FAULT_DATABASE_URL"])
    if operation == "persist":
        store.persist({"request_id": "interrupted", "items": [], "serving_generation": "stable"})
    else:
        store.drain()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        inference()
    else:
        transaction(sys.argv[1])
