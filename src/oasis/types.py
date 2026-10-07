"""Shared data types.

This module imports nothing from the project so that every package — including the
isolated safety layer — can depend on it without import cycles. No type here that
reaches the trace or logs may carry user text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Mode = Literal[
    "crisis",
    "post_crisis",
    "assessment",
    "psychoed",
    "companion",
    "cbt",
    "dbt",
    "mindfulness",
    "grounding",
    "fallback",
]

Role = Literal["user", "assistant", "placeholder"]


@dataclass(frozen=True)
class SafetyVerdict:
    is_crisis: bool
    tiers: frozenset[str] = frozenset()
    pattern_ids: tuple[str, ...] = ()
    ruleset_version: str = "stub"


@dataclass(frozen=True)
class Plan:
    """What the reply must do. The LLM only phrases a plan; it never chooses one."""

    mode: Mode
    templated: bool = False
    template_id: str | None = None
    constraints: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GuardVerdict:
    ok: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatMessage:
    """One message in an LLM prompt (role uses the chat-completion vocabulary)."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class TurnRecord:
    turn_id: str
    seq: int
    role: Role
    content: str
    mode: Mode | None
    created_at: str


@dataclass(frozen=True)
class StageTiming:
    name: str
    duration_ms: float
    outcome: str


@dataclass(frozen=True)
class TurnTrace:
    """Per-turn record of what happened. Holds IDs, timings and codes — never text."""

    turn_id: str
    stages: tuple[StageTiming, ...]
    safety: SafetyVerdict
    plan_mode: Mode
    llm_attempts: int
    guard_outcomes: tuple[str, ...]
    fallback_reason: str | None
    degraded: frozenset[str] = field(default_factory=frozenset)
