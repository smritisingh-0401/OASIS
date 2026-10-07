"""Per-turn trace: stage timings and decision codes, never user text (rules P2)."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from typing import Any

from oasis.types import StageTiming, TurnTrace


class StageClock:
    def __init__(self) -> None:
        self.stages: list[StageTiming] = []
        self._start = time.perf_counter()

    def mark(self, name: str, outcome: str) -> None:
        """Close the stage that began at the previous mark."""
        now = time.perf_counter()
        self.stages.append(StageTiming(name, round((now - self._start) * 1000, 3), outcome))
        self._start = now


def _jsonable(value: Any) -> Any:
    if isinstance(value, frozenset | set):
        return sorted(value)
    raise TypeError(type(value).__name__)


def trace_to_json(trace: TurnTrace) -> str:
    return json.dumps(asdict(trace), default=_jsonable, separators=(",", ":"))
