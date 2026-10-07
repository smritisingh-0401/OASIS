"""Phase 1 safety stub: fail-closed wrapper and startup tripwire (rules S5, S13)."""

from __future__ import annotations

import pytest

from oasis.safety.gate import (
    SafetyStubNotAllowed,
    StubSafetyGate,
    check_fail_closed,
    ensure_allowed,
)
from oasis.types import SafetyVerdict


class ExplodingGate:
    is_stub = False

    def check(self, text: str) -> SafetyVerdict:
        raise RuntimeError("detector crashed")


class RealishGate:
    is_stub = False

    def check(self, text: str) -> SafetyVerdict:
        return SafetyVerdict(is_crisis=False, ruleset_version="test")


def test_stub_returns_clear_verdict() -> None:
    assert check_fail_closed(StubSafetyGate(), "hello").is_crisis is False


def test_gate_exception_fails_closed() -> None:
    verdict = check_fail_closed(ExplodingGate(), "hello")
    assert verdict.is_crisis is True
    assert "internal_error" in verdict.tiers


def test_tripwire_refuses_stub_without_dev_flag() -> None:
    with pytest.raises(SafetyStubNotAllowed):
        ensure_allowed(StubSafetyGate(), dev_mode=False)


def test_tripwire_allows_stub_in_dev_mode() -> None:
    ensure_allowed(StubSafetyGate(), dev_mode=True)


def test_tripwire_allows_real_gate_without_dev_flag() -> None:
    ensure_allowed(RealishGate(), dev_mode=False)
