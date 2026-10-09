"""Planner: picks exactly one mode per turn with fixed precedence (design §6).

Implemented rungs: post-crisis minimal supportive mode, then an open assessment, then an
assessment offer, then companion mode. Psychoeducation and the therapy router fill in the
remaining rungs in Phases 4-6.
"""

from __future__ import annotations

import datetime
import re

from oasis.assessment import flow, trigger
from oasis.safety.normalize import base_form
from oasis.types import AssessmentAction, ConversationState, Plan

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


def plan_turn(
    message: str, state: ConversationState, action: AssessmentAction | None = None
) -> Plan:
    if state.post_crisis:
        if not wants_to_continue(message):
            return Plan(mode="post_crisis", templated=True, template_id="post_crisis",
                        reason_codes=("post_crisis.hold",))  # fmt: skip
        return Plan(mode="companion", reason_codes=("post_crisis.cleared",))

    now = state.now or datetime.datetime.now(datetime.UTC)
    open_rec, expired = flow.active(state.assessments, now)

    if action is not None:  # a button on the assessment card
        if open_rec is None:
            return Plan(mode="assessment", templated=True, template_id="assessment_unavailable",
                        assessment=expired, reason_codes=("assessment.none_open",))  # fmt: skip
        return _from_step(flow.on_action(open_rec, action, now), f"assessment.{action.kind}")

    if open_rec is not None:  # typed instead of pressing a button
        step = flow.on_free_text(open_rec, now)
        return Plan(mode="companion", assessment=step.record, card=step.card,
                    reason_codes=("planner.passthrough", "assessment.free_text"))  # fmt: skip

    offer = trigger.decide(state.history, message, state.assessments, now)
    if offer is not None:
        return _from_step(flow.offer(offer.instrument, offer.reason, now), "assessment.offer")
    return Plan(mode="companion", assessment=expired, reason_codes=("planner.passthrough",))


def _from_step(step: flow.Step, code: str) -> Plan:
    if step.escalate:
        return Plan(mode="crisis", templated=True, assessment=step.record,
                    reason_codes=("assessment.item9",))  # fmt: skip
    if step.text is None:
        return Plan(mode="companion", assessment=step.record, card=step.card, reason_codes=(code,))
    return Plan(mode="assessment", templated=True, text=step.text, preface=step.preface,
                assessment=step.record, card=step.card, reason_codes=(code,))  # fmt: skip
