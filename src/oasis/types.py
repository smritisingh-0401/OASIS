"""Shared data types.

This module imports nothing from the project so that every package — including the
isolated safety layer — can depend on it without import cycles. No type here that
reaches the trace or logs may carry user text.
"""

from __future__ import annotations

import datetime
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

InstrumentId = Literal["PHQ9", "GAD7"]
AssessmentStatus = Literal[
    "offered", "declined", "in_progress", "paused", "aborted", "escalated", "scored"
]
# Assessments that are still open: an offer awaiting an answer, or a questionnaire underway.
ACTIVE_STATUSES = frozenset({"offered", "in_progress", "paused"})


@dataclass(frozen=True)
class SafetyVerdict:
    is_crisis: bool
    tiers: frozenset[str] = frozenset()
    pattern_ids: tuple[str, ...] = ()
    ruleset_version: str = ""


@dataclass(frozen=True)
class AssessmentRecord:
    """One PHQ-9 or GAD-7 administration. `answers` holds item values in order (0-3)."""

    assessment_id: str
    instrument: InstrumentId
    status: AssessmentStatus
    offer_reason: str  # JSON reason code and score (design §3.2); never message text
    created_at: str
    answers: tuple[int, ...] = ()
    functional: int | None = None
    total: int | None = None
    band: str | None = None
    completed_at: str | None = None


@dataclass(frozen=True)
class AssessmentAction:
    """A button press on the assessment card. Answers are never parsed from free text."""

    kind: Literal["accept", "decline", "answer", "pause", "resume", "abort"]
    value: int | None = None
    # The item the card showed (None for the functional question). Used to ignore stale or
    # repeated clicks, and for the item-9 check that runs before storage is touched.
    instrument: InstrumentId | None = None
    item: int | None = None


@dataclass(frozen=True)
class AssessmentCard:
    """What the UI shows under the reply: buttons for the current step."""

    step: Literal["offer", "item", "functional", "result", "paused"]
    instrument: InstrumentId
    name: str
    item: int | None = None
    item_count: int | None = None
    options: tuple[str, ...] = ()
    total: int | None = None
    band: str | None = None


@dataclass(frozen=True)
class Plan:
    """What the reply must do. The LLM only phrases a plan; it never chooses one."""

    mode: Mode
    templated: bool = False
    template_id: str | None = None
    constraints: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    # Fixed reply text built by the decision plane (assessment steps); wins over template_id.
    text: str | None = None
    # Fixed message sent as its own bubble before the reply (e.g. a questionnaire's instruction).
    preface: str | None = None
    # Assessment state to persist before replying, and the card to show with the reply.
    assessment: AssessmentRecord | None = None
    card: AssessmentCard | None = None


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
class ConversationState:
    """What the planner may read about the conversation (loaded after the safety gate)."""

    history: tuple[TurnRecord, ...] = ()
    post_crisis: bool = False
    assessments: tuple[AssessmentRecord, ...] = ()  # this user's, oldest first
    now: datetime.datetime | None = None


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
