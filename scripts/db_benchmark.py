"""SQLite repository latency: one turn's writes and the history read.

Usage:  uv run python scripts/db_benchmark.py [--turns 1000] [--db PATH]
Uses a temporary database unless --db is given (must be on local disk, not a network share).
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import tempfile
import time
import uuid
from pathlib import Path

from oasis.storage.sqlite import SQLiteRepository


def pct(samples: list[float], q: float) -> float:
    return statistics.quantiles(samples, n=100, method="inclusive")[int(q) - 1]


async def bench(path: Path, turns: int) -> None:
    repo = SQLiteRepository(path)
    uid = await repo.create_user_session("bench")
    writes: list[float] = []
    reads: list[float] = []
    for i in range(turns):
        start = time.perf_counter()
        for role in ("user", "assistant"):
            await repo.append_turn(
                uid,
                "bench",
                turn_id=uuid.uuid4().hex,
                role=role,
                content=f"message {i} " * 20,
                mode=None,
                trace_json="{}",
            )
        writes.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        await repo.recent_turns(uid, "bench", 6)
        reads.append((time.perf_counter() - start) * 1000)
    await repo.close()

    print(f"SQLite benchmark: {turns} turns (2 writes + 1 history read each), db={path}")
    print(f"{'operation':<22}{'p50 ms':>10}{'p95 ms':>10}{'p99 ms':>10}")
    for name, samples in (("write turn pair", writes), ("read last 6 turns", reads)):
        print(
            f"{name:<22}{pct(samples, 50):>10.3f}{pct(samples, 95):>10.3f}{pct(samples, 99):>10.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--turns", type=int, default=1000)
    parser.add_argument("--db", type=Path)
    args = parser.parse_args()
    if args.db:
        asyncio.run(bench(args.db, args.turns))
        return
    with tempfile.TemporaryDirectory() as tmp:
        asyncio.run(bench(Path(tmp) / "bench.db", args.turns))


if __name__ == "__main__":
    main()
