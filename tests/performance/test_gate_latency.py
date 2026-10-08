"""Safety gate latency budget: under 10 ms per message (design §2.3)."""

from __future__ import annotations

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


def test_gate_stays_under_10ms_per_message() -> None:
    gate = RuleBasedSafetyGate(load_ruleset())
    for text in MESSAGES:
        # Best of 5 measures the gate's own cost, not scheduler noise on a busy machine;
        # scripts/safety_eval.py reports the full latency distribution.
        best = min(_elapsed_ms(gate, text) for _ in range(5))
        assert best < 10, f"{best:.2f} ms for {text[:30]!r}"


def _elapsed_ms(gate: RuleBasedSafetyGate, text: str) -> float:
    start = time.perf_counter()
    gate.check(text)
    return (time.perf_counter() - start) * 1000
