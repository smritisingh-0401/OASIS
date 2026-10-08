"""Planner: picks exactly one mode per turn with fixed precedence (design §6).

Phase 2 implements the first rung — post-crisis minimal supportive mode — and passes
everything else to companion mode. Assessment, psychoeducation and the therapy router
fill in the remaining rungs in Phases 3-6.
"""

from __future__ import annotations

import re

from oasis.safety.normalize import base_form
from oasis.types import ConversationState, Plan

# Explicit wish to keep talking after a crisis handoff; the UI's "Continue talking" button
# sends "I'd like to keep talking." Never inferred from anything else (design §2.4).
# Clinician review pending: CR-05.
_CONTINUE = re.compile(
    r"\b(?:(?:i(?:d| would)? (?:like|want|wanna) to|can we|could we|lets|let us|"
    r"i(?:m| am) ready to) (?:keep|continue|carry on|go on) (?:talking|chatting)|"
    r"(?:keep|continue) talking)\b"
)


def wants_to_continue(message: str) -> bool:
    return bool(_CONTINUE.search(base_form(message)))


def plan_turn(message: str, state: ConversationState) -> Plan:
    if state.post_crisis:
        if not wants_to_continue(message):
            return Plan(mode="post_crisis", templated=True, template_id="post_crisis",
                        reason_codes=("post_crisis.hold",))  # fmt: skip
        return Plan(mode="companion", reason_codes=("post_crisis.cleared",))
    return Plan(mode="companion", reason_codes=("planner.passthrough",))
