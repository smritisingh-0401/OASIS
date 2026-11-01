"""Shared data types.

This module imports nothing from the project so that every package — including the
isolated safety layer — can depend on it without import cycles. No type here that
reaches the trace or logs may carry user text.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
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

RouterMode = Literal["companion", "cbt", "dbt", "mindfulness"]
ROUTER_MODES: tuple[RouterMode, ...] = ("companion", "cbt", "dbt", "mindfulness")

Role = Literal["user", "assistant", "placeholder"]

InstrumentId = Literal["PHQ9", "GAD7"]
AssessmentStatus = Literal[
    "offered", "declined", "in_progress", "paused", "aborted", "escalated", "scored"
]
Directness = Literal["direct", "balanced", "indirect"]
Formality = Literal["casual", "neutral", "formal"]

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
    offer_reason: str
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
class Signals:
    """One message's detector outputs (design §5). Scores in [0, 1]; valence in [-1, 1].

    Holds numbers and category names only, never text, so it can go into the trace.
    """

    valence: float = 0.0
    emotions: Mapping[str, float] = field(default_factory=dict)
    dysregulation: float = 0.0
    distortion: float = 0.0
    distortion_types: frozenset[str] = frozenset()
    overwhelm: float = 0.0
    wants_to_talk: float = 0.0
    opt_out: bool = False
    psychoed_cue: bool = False
    asks_advice: bool = False


@dataclass(frozen=True)
class RouterState:
    """Per-session router memory (design §7.2), persisted as JSON with the session."""

    current: Mode = "companion"
    challenger: RouterMode | None = None
    streak: int = 0
    offered: RouterMode | None = None
    exercise: str | None = None
    step: int = 0
    consented: frozenset[RouterMode] = frozenset()
    psychoed_shown: frozenset[str] = frozenset()


@dataclass(frozen=True)
class Contribution:
    signal: str
    value: float


@dataclass(frozen=True)
class ModeScore:
    mode: RouterMode
    score: float
    bias: float
    contributions: tuple[Contribution, ...]


@dataclass(frozen=True)
class RouteDecision:
    """The router's answer for one turn: the mode, why, and every mode's full breakdown."""

    mode: Mode
    reason: str
    scores: tuple[ModeScore, ...]
    state: RouterState
    offer: RouterMode | None = None


@dataclass(frozen=True)
class ExerciseAction:
    """A button press on the exercise card."""

    kind: Literal["accept", "decline", "stop"]


@dataclass(frozen=True)
class ExerciseCard:
    """What the UI shows for a structured mode: a consent offer or the running exercise."""

    step: Literal["offer", "active"]
    mode: Mode
    name: str
    item: int | None = None
    item_count: int | None = None
    instruction: str | None = None


@dataclass(frozen=True)
class StyleProfile:
    """How replies are worded; changes framing only, never what a reply does (FR-CUL-3)."""

    directness: Directness = "balanced"
    formality: Formality = "neutral"


@dataclass(frozen=True)
class Plan:
    """What the reply must do. The LLM only phrases a plan; it never chooses one."""

    mode: Mode
    templated: bool = False
    template_id: str | None = None
    constraints: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    text: str | None = None
    preface: str | None = None
    assessment: AssessmentRecord | None = None
    card: AssessmentCard | None = None
    snippet: str | None = None
    exercise_card: ExerciseCard | None = None
    router_state: RouterState | None = None
    route: RouteDecision | None = None
    avoid_openers: tuple[str, ...] = ()
    # Thinking-trap turns (Phase 7): the categories found and each distorted clause of the
    # user's message as a set of content words, for the guard's echo checks. Derived from
    # user text, so never stored or traced (rules P2).
    distortion_types: frozenset[str] = frozenset()
    claims: tuple[frozenset[str], ...] = ()
    claim_texts: tuple[str, ...] = ()
    style: StyleProfile = StyleProfile()

    @property
    def is_step(self) -> bool:
        """An exercise step: the LLM writes only a short acknowledgement, and the engine
        adds the step text after it word for word (psychoed snippets are explained instead)."""
        return self.snippet is not None and self.mode != "psychoed"


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
class TurnFeatures:
    """Language features of one user message (design §9.1). Numbers only, never text."""

    valence: float
    sadness: float
    anxiety: float
    anger: float
    shame: float
    loneliness: float
    fp_pronoun_rate: float
    absolutist_rate: float
    msg_length: int
    reply_latency_s: float | None
    hour_of_day: int | None


@dataclass(frozen=True)
class SignalRecord:
    session_hash: str
    created_at: str
    features: TurnFeatures


@dataclass(frozen=True)
class TurnRecord:
    turn_id: str
    seq: int
    role: Role
    content: str
    mode: Mode | None
    created_at: str
    has_explanation: bool = False


@dataclass(frozen=True)
class ConversationState:
    """What the planner may read about the conversation (loaded after the safety gate)."""

    history: tuple[TurnRecord, ...] = ()
    post_crisis: bool = False
    assessments: tuple[AssessmentRecord, ...] = ()
    now: datetime.datetime | None = None
    router: RouterState = RouterState()
    psychoed_match: str | None = None


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
    reason_codes: tuple[str, ...] = ()
    route: RouteDecision | None = None
