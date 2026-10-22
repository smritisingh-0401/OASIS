"""Explanation overhead: a small share of the 150 ms non-LLM budget (PRD §6.1, L1 d)."""

from __future__ import annotations

import datetime
import time

from oasis.core.planner import plan_turn
from oasis.explain.builder import build
from oasis.types import ConversationState

NOW = datetime.datetime(2026, 10, 22, 12, tzinfo=datetime.UTC)
MESSAGES = [
    "I had a long day at work and I'm tired",
    "I always mess everything up and nobody likes me",
    "I'm so anxious and worried, everything is too much and I can't cope",
    "I always feel like a failure and nobody cares " * 40,  # ~1 900 characters
]


def test_explanation_stays_under_20ms_per_reply() -> None:
    state = ConversationState(now=NOW)
    for text in MESSAGES:
        plan = plan_turn(text, state)
        build(text, plan)  # first call loads the content files and background means
        # Best of 5 measures the builder's own cost, not scheduler noise.
        best = min(_elapsed_ms(text, plan) for _ in range(5))
        assert best < 20, f"{best:.2f} ms for {text[:30]!r}"


def _elapsed_ms(text: str, plan: object) -> float:
    start = time.perf_counter()
    build(text, plan)  # type: ignore[arg-type]
    return (time.perf_counter() - start) * 1000
