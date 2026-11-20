"""Generate the synthetic OTTO-format acceptance fixture."""
import json
from pathlib import Path
from random import Random

SEED = 734


def main():
    rng = Random(SEED)

    def session(session_id, aids, timestamps, types=None):
        return {
            "session": session_id,
            "events": [
                {"aid": aid, "ts": ts, "type": types[i] if types else "clicks"}
                for i, (aid, ts) in enumerate(zip(aids, timestamps, strict=True))
            ],
        }

    rows = [
        session(1, [1, 2, 1, 3, 2], [110, 110, 111, 112, 113]),
        session(2, [4] + [5] * 19 + [6, 7], range(120, 142)),
        session(3, [8] * 500 + [9], [150] * 501),
        session(4, [2, 1], [160, 161]),
        session(5, [1, 2, 3, 999], [210, 210, 210, 211],
                ["clicks", "carts", "clicks", "clicks"]),
        session(6, [1, 2], [199, 200]),
        session(7, [1, 2, 3], [299, 300, 301]),
        session(8, [1, 2], [410, 411], ["clicks", "orders"]),
        session(9, [1] * 22, [399] * 21 + [400]),
    ]
    for session_id in range(10, 26):
        rows.append(session(session_id, rng.choices(range(1, 8), k=4), range(310, 314)))
    fixture = Path(__file__).resolve().parents[1] / "tests/fixtures/synthetic_otto.jsonl"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode("utf-8"))


if __name__ == "__main__":
    main()
