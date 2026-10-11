"""Planner: picks exactly one mode per turn with fixed precedence (design §6).

Rungs: post-crisis minimal supportive mode, then an open assessment, then an assessment
offer, then the therapy router (companion, CBT, DBT, mindfulness, or grounding under acute
overwhelm). Psychoeducation fills its rung in Phase 5.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence

from oasis.assessment import flow, trigger
from oasis.core.signals import extract
from oasis.core.templates import TEMPLATES
from oasis.router import exercise, router
from oasis.safety.normalize import base_form
from oasis.types import (
    AssessmentAction,
    AssessmentRecord,
    ConversationState,
    ExerciseAction,
    ExerciseCard,
    Plan,
    RouteDecision,
    RouterState,
)

# Explicit wish to keep talking after a crisis handoff; the UI's "Continue talking" button
# sends "I'd like to keep talking." Never inferred from anything else (design §2.4).
# Clinician review pending: CR-05.
_CONTINUE = re.compile(
    r"\b(?:(?:i(?:d| would)? (?:like|want|wanna) to|can we|could we|lets|let us|"
    r"i(?:m| am) ready to) (?:keep|continue|carry on|go on) (?:talking|chatting)|"
    r"(?:keep|continue) talking)\b"
)

# Plan constraints per mode (design §13.2); the prompt builder turns them into rules.
CONSTRAINTS: dict[str, tuple[str, ...]] = {
    "companion": ("one_question", "no_advice", "no_praise"),
    "cbt": ("validate_first", "one_question", "socratic"),
    "dbt": ("validate_first", "offer_not_instruct"),
    "mindfulness": ("follow_script", "one_step"),
}
STEP_CONSTRAINTS = ("follow_script", "one_step")
MODERATE_PLUS = frozenset({"moderate", "moderately severe", "severe"})

Action = AssessmentAction | ExerciseAction


def wants_to_continue(message: str) -> bool:
    return bool(_CONTINUE.search(base_form(message)))


def plan_turn(message: str, state: ConversationState, action: Action | None = None) -> Plan:
    if state.post_crisis:
        if not wants_to_continue(message):
            return Plan(mode="post_crisis", templated=True, template_id="post_crisis",
                        reason_codes=("post_crisis.hold",))  # fmt: skip
        return Plan(mode="companion", reason_codes=("post_crisis.cleared",))

    now = state.now or datetime.datetime.now(datetime.UTC)
    open_rec, expired = flow.active(state.assessments, now)

    if isinstance(action, ExerciseAction):
        return _exercise_button(action, state.router)
    if action is not None:  # a button on the assessment card
        if open_rec is None:
            return Plan(mode="assessment", templated=True, template_id="assessment_unavailable",
                        assessment=expired, reason_codes=("assessment.none_open",))  # fmt: skip
        return _from_step(flow.on_action(open_rec, action, now), f"assessment.{action.kind}")

    if open_rec is not None:  # typed instead of pressing a button
        step = flow.on_free_text(open_rec, now)
        return Plan(mode="companion", assessment=step.record, card=step.card,
                    reason_codes=("planner.passthrough", "assessment.free_text"))  # fmt: skip

    if state.router.exercise is None:  # no screening offer mid-exercise (design §3.2)
        offer = trigger.decide(state.history, message, state.assessments, now)
        if offer is not None:
            return _from_step(flow.offer(offer.instrument, offer.reason, now), "assessment.offer")
    return _routed(message, state, now, expired)


def _routed(
    message: str,
    state: ConversationState,
    now: datetime.datetime,
    expired: AssessmentRecord | None,
) -> Plan:
    signals = extract(message)
    decision = router.route(signals, state.router, extra=_band_flags(state.assessments, now))
    rs = decision.state
    codes = [f"router.{decision.reason}"]
    if state.router.offered is not None:
        codes.append("exercise.offer_lapsed")
    if state.router.exercise is not None and rs.exercise is None:
        codes.append("exercise.opt_out")
    if decision.reason == "acute_override":
        rs = exercise.start(rs, exercise.technique_for("grounding").id)

    if rs.exercise is not None:
        text, rs, card = exercise.deliver(rs)
        return _step_plan(decision, text, rs, card, codes, expired)
    if decision.offer is not None:
        t = exercise.technique_for(decision.offer)
        return Plan(mode=decision.mode, templated=True, text=t.offer,
                    exercise_card=ExerciseCard("offer", decision.offer, t.name),
                    router_state=rs, route=decision, assessment=expired,
                    reason_codes=tuple(codes))  # fmt: skip
    return Plan(mode=decision.mode, constraints=CONSTRAINTS.get(decision.mode, ()),
                router_state=rs, route=decision, assessment=expired,
                reason_codes=tuple(codes))  # fmt: skip


def _step_plan(
    decision: RouteDecision | None,
    text: str,
    rs: RouterState,
    card: ExerciseCard | None,
    codes: Sequence[str],
    expired: AssessmentRecord | None = None,
) -> Plan:
    # The mode is the one the step belongs to, even when it was the last step (rs.current).
    return Plan(mode=rs.current, constraints=STEP_CONSTRAINTS, snippet=text, exercise_card=card,
                router_state=rs, route=decision, assessment=expired,
                reason_codes=tuple(codes))  # fmt: skip


def _exercise_button(action: ExerciseAction, rs: RouterState) -> Plan:
    stale = rs.offered is None if action.kind in ("accept", "decline") else rs.exercise is None
    if stale:
        return Plan(mode=rs.current, templated=True, text=TEMPLATES["exercise_unavailable"],
                    reason_codes=("exercise.none_open",))  # fmt: skip
    if action.kind in ("decline", "stop"):
        after = router.decline(rs) if action.kind == "decline" else router.stop(rs)
        template = "exercise_declined" if action.kind == "decline" else "exercise_stopped"
        return Plan(mode=rs.current, templated=True, text=TEMPLATES[template],
                    router_state=after, reason_codes=(f"exercise.{action.kind}",))  # fmt: skip
    rs = router.accept(rs)
    rs = exercise.start(rs, exercise.technique_for(rs.current).id)
    text, rs, card = exercise.deliver(rs)
    return _step_plan(None, text, rs, card, ("exercise.accepted",))


def _band_flags(records: Sequence[AssessmentRecord], now: datetime.datetime) -> dict[str, float]:
    """Moderate-or-worse PHQ-9 / GAD-7 results inside the re-administration window."""
    window = trigger.config().repeat_after
    flags = {"phq_moderate_plus": 0.0, "gad_moderate_plus": 0.0}
    for r in records:
        when = datetime.datetime.fromisoformat(r.completed_at or r.created_at)
        if r.status == "scored" and r.band in MODERATE_PLUS and now - when < window:
            flags[f"{r.instrument[:3].lower()}_moderate_plus"] = 1.0
    return flags


def _from_step(step: flow.Step, code: str) -> Plan:
    if step.escalate:
        return Plan(mode="crisis", templated=True, assessment=step.record,
                    reason_codes=("assessment.item9",))  # fmt: skip
    if step.text is None:
        return Plan(mode="companion", assessment=step.record, card=step.card, reason_codes=(code,))
    return Plan(mode="assessment", templated=True, text=step.text, preface=step.preface,
                assessment=step.record, card=step.card, reason_codes=(code,))  # fmt: skip
