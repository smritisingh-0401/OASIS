"""Safety gate: rule-based crisis detection that runs first on every message.

Pure Python: no LLM, network or database imports (rules S8, enforced by import-linter
and an AST test). Fails closed: any internal error is a crisis verdict (rules S5).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from oasis.safety.rules import RuleSet, load_ruleset
from oasis.types import SafetyVerdict

# Optional extra detector. It may only ADD alerts (rules S7): it receives the raw text and
# returns alert names; an empty result never clears a rule-based match.
Classifier = Callable[[str], Sequence[str]]


class SafetyGate(Protocol):
    def check(self, text: str) -> SafetyVerdict: ...


class RuleBasedSafetyGate:
    def __init__(self, ruleset: RuleSet, classifier: Classifier | None = None) -> None:
        self.ruleset = ruleset
        self._classifier = classifier

    @classmethod
    def load(cls) -> RuleBasedSafetyGate:
        return cls(load_ruleset())

    def check(self, text: str) -> SafetyVerdict:
        hits = self.ruleset.hits(text)
        if self._classifier is not None:
            for alert in self._classifier(text):
                hits[f"classifier.{alert}"] = "classifier"
        return SafetyVerdict(
            is_crisis=bool(hits),
            tiers=frozenset(hits.values()),
            pattern_ids=tuple(sorted(hits)),
            ruleset_version=self.ruleset.version,
        )


def check_fail_closed(gate: SafetyGate, text: str) -> SafetyVerdict:
    """Run the gate; any internal error is treated as a crisis (rules S5)."""
    try:
        return gate.check(text)
    except Exception:  # fail-closed boundary: a broken detector must never let a turn through
        return SafetyVerdict(
            is_crisis=True, tiers=frozenset({"internal_error"}), pattern_ids=("internal_error",)
        )
