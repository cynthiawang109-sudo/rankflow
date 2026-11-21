"""Subprocess targets for local simulated scorer and transaction failures."""
import json
import os
import sys
from threading import Event


def inference():
    for message in sys.stdin.buffer:
        path, _, rows = json.loads(message)
        if rows and path == "hang":
            Event().wait()
        if rows and path == "crash":
            os._exit(23)
        print(json.dumps([0] * len(rows)), flush=True)


def transaction(operation):
    from rankflow.store import PostgresStore

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
                    if statement.lstrip().startswith(checkpoint):
                        print("transaction_open", flush=True)
                        Event().wait()
                    return result

            return InterruptedTransaction()

    checkpoint = {"persist": "WITH impression AS", "drain": "INSERT INTO delivered_events"}[operation]
    store = InterruptedStore(os.environ["RANKFLOW_FAULT_DATABASE_URL"])
    if operation == "persist":
        store.persist({"request_id": "interrupted", "items": [], "serving_generation": "stable"})
    else:
        store.drain()


def send_completion():
    import asyncio

    from rankflow.api import create_app
    from rankflow.store import PostgresStore
    from tests.test_stage1 import GENERATION, event, payload

    class InterruptedStore(PostgresStore):
        def record_send(self, impression_id, state):
            assert state == "send_completed"
            Event().wait()

    app = create_app(GENERATION, InterruptedStore(os.environ["RANKFLOW_FAULT_DATABASE_URL"]))
    body = json.dumps(payload([event(1)])).encode()
    scope = {"type": "http", "method": "POST", "path": "/v1/recommend", "root_path": "",
             "query_string": b"", "headers": [(b"content-type", b"application/json")],
             "scheme": "http", "server": ("local", 80), "http_version": "1.1", "state": {}}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.body":
            print(message["body"].decode(), flush=True)

    asyncio.run(app(scope, receive, send))


if __name__ == "__main__":
    if len(sys.argv) == 1:
        inference()
    elif sys.argv[1] == "send":
        send_completion()
    else:
        transaction(sys.argv[1])
