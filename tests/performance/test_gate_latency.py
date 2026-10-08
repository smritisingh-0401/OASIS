"""Safety gate latency budget: p99 under 10 ms per message (design §2.3)."""

from __future__ import annotations

import statistics
import time

from oasis.safety.gate import RuleBasedSafetyGate
from oasis.safety.rules import load_ruleset

MESSAGES = [
    "I had a long day at work and I'm tired",
    "my exams are next week and I can't focus",
    "I want to kill myself",
    "everyone would be better off without me",
    "k i l l  m y s e l f",
    "I'm d3ad tired of all this " * 20,
    "x" * 2000,
]


def test_gate_p99_under_10ms() -> None:
    gate = RuleBasedSafetyGate(load_ruleset())
    for text in MESSAGES:
        gate.check(text)  # warm regex caches
    samples = []
    for _ in range(50):
        for text in MESSAGES:
            start = time.perf_counter()
            gate.check(text)
            samples.append((time.perf_counter() - start) * 1000)
    p99 = statistics.quantiles(samples, n=100)[98]
    assert p99 < 10, f"p99 {p99:.2f} ms"
