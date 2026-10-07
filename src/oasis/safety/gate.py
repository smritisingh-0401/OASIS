"""Safety gate interface, fail-closed wrapper and startup tripwire.

Phase 1 ships only a stub detector. The tripwire stops anyone running the stub outside
development (rules S13); Phase 2 replaces the stub with the rule-based detector.
"""

from __future__ import annotations

from typing import Protocol

from oasis.types import SafetyVerdict


class SafetyGate(Protocol):
    is_stub: bool

    def check(self, text: str) -> SafetyVerdict: ...


class StubSafetyGate:
    """Development placeholder: never detects anything."""

    is_stub = True

    def check(self, text: str) -> SafetyVerdict:
        return SafetyVerdict(is_crisis=False, ruleset_version="stub")


class SafetyStubNotAllowed(RuntimeError):
    pass


def check_fail_closed(gate: SafetyGate, text: str) -> SafetyVerdict:
    """Run the gate; any internal error is treated as a crisis (rules S5)."""
    try:
        return gate.check(text)
    except Exception:  # fail-closed boundary: a broken detector must never let a turn through
        return SafetyVerdict(
            is_crisis=True, tiers=frozenset({"internal_error"}), pattern_ids=("internal_error",)
        )


def ensure_allowed(gate: SafetyGate, *, dev_mode: bool) -> None:
    if gate.is_stub and not dev_mode:
        raise SafetyStubNotAllowed(
            "The safety layer is a development stub. Set OASIS_DEV_MODE=1 to run it locally; "
            "it must not be used by anyone until the Phase 2 safety layer is in place."
        )
