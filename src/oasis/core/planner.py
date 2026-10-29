"""Planner: picks exactly one mode per turn with fixed precedence (design §6).

Rungs: post-crisis minimal supportive mode, then an open assessment, then an explicit
questionnaire request, then psychoeducation, then an unprompted questionnaire offer, then the
therapy router (companion, CBT, DBT, mindfulness, or grounding under acute overwhelm).
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Sequence
from dataclasses import replace

from oasis.assessment import flow, trigger
from oasis.core.signals import claims, extract
from oasis.core.templates import TEMPLATES
from oasis.guard.checks import medication_topic, opener
from oasis.psychoed import selector as psychoed
from oasis.router import exercise, router
from oasis.router.weights import config as router_config
from oasis.safety.normalize import base_form
from oasis.types import (
    AssessmentAction,
    AssessmentRecord,
    ConversationState,
    ExerciseAction,
    ExerciseCard,
    Mode,
    Plan,
    RouteDecision,
    RouterState,
    Signals,
)

# Explicit wish to keep talking after a crisis handoff; the UI's "Continue talking" button
# sends "I'd like to keep talking." Never inferred from anything else (design §2.4).
# Clinician review pending: CR-05.
_CONTINUE = re.compile(
    r"\b(?:(?:i(?:d| would)? (?:like|want|wanna) to|can we|could we|lets|let us|"
    r"i(?:m| am) ready to) (?:keep|continue|carry on|go on) (?:talking|chatting)|"
    r"(?:keep|continue) talking)\b"
)
# Asking for no questions (demo testing, 2026-10-29: "you are asking me how much sad").
# Clinician review pending: CR-14.
_JUST_LISTEN = re.compile(
    r"\b(?:(?:stop|quit) asking|(?:no|dont want(?: any)?|do not want(?: any)?) (?:more )?"
    r"questions|too many questions|(?:just|only) (?:listen|vent)|(?:just |only )?need to vent|"
    r"(?:you|youre|you are|you keep|you always) (?:keep )?asking me)\b"
)
# A question about what OASIS is or who made it, as the whole message (demo testing,
# 2026-10-29: "Who is your owner" got "created by Google"). Answered with a fixed text.
_IDENTITY = re.compile(
    r"^(?:(?:hi|hey|hello|so|ok|okay|but|wait|oasis|tell me),? )*(?:"
    r"(?:who|what)(?: are|re) (?:you|u)|"
    r"(?:who|which company|what company) (?:made|created|built|developed|owns|designed|"
    r"programmed|trained|runs) (?:you|u)|"
    r"whos (?:your|ur) (?:owner|maker|creator|developer|company)|"
    r"who is (?:your|ur) (?:owner|maker|creator|developer|company)|"
    r"are (?:you|u) (?:chatgpt|chat gpt|gpt|google|gemini|bard|claude|qwen|siri|alexa|"
    r"a bot|a robot|an ai|ai|human|a human|a person|a real person|real)"
    r")(?: exactly| really| anyway| then| lol)?\s*[?.!]*\s*$"
)
LISTEN_AFTER = 2  # replies ending in a question in a row before one that only listens
LONG_MESSAGE_WORDS = 40  # an outpouring this long gets a listening reply
BRIEF_WORDS = 5  # a statement this short gets a one-sentence acknowledgement
IDEA_EVERY = 4  # at most one unasked idea in this many replies
NEUTRAL = 0.05  # VADER's own neutral band: a message below -NEUTRAL describes a difficulty
_QUESTION_WORDS = frozenset({
    "who", "what", "why", "how", "when", "where", "which", "can", "could", "should", "would",
    "is", "are", "am", "do", "does", "did", "will", "was", "were",
})  # fmt: skip

# Plan constraints per mode (design §13.2); the prompt builder turns them into rules.
CONSTRAINTS: dict[str, tuple[str, ...]] = {
    # Suggestions (when asked for) come before the closing question, so no_advice sits first.
    "companion": ("validate_first", "no_advice", "one_question", "no_praise"),
    "cbt": ("validate_first", "one_question", "socratic"),
    "dbt": ("validate_first", "offer_not_instruct"),
    "mindfulness": ("follow_script", "one_step"),
    "psychoed": ("no_diagnosis", "use_snippet_only"),
}
STEP_CONSTRAINTS = ("ack_only",)
# Added to any generated reply to a thinking-trap message, in every mode (design §8.2).
DISTORTION_RULES = ("validate_first", "one_question", "socratic", "no_agreeing")
RECENT_OPENERS = 3  # companion replies whose openers the next one must not reuse
SHORT_REPLY_WORDS = 2  # "okay", "yes sure": nothing to respond to before an exercise step
MODERATE_PLUS = frozenset({"moderate", "moderately severe", "severe"})

Action = AssessmentAction | ExerciseAction


def wants_to_continue(message: str) -> bool:
    return bool(_CONTINUE.search(base_form(message)))


def plan_turn(message: str, state: ConversationState, action: Action | None = None) -> Plan:
    plan = _plan(message, state, action)
    if plan.is_step and not plan.templated and len(message.split()) <= SHORT_REPLY_WORDS:
        # The model only had "Okay." or "That is a good start." to add (tone check, 2026-10-13).
        return replace(plan, templated=True, text=plan.snippet,
                       reason_codes=(*plan.reason_codes, "exercise.short_reply"))  # fmt: skip
    if plan.templated or plan.snippet is not None:
        return plan
    plan = with_thinking_trap(plan, message)
    if medication_topic(message) and "no_agreeing" not in plan.constraints:
        # "Should I stop my antidepressants?" must not get "you are right to want..." (stress
        # check, 2026-10-13).
        plan = replace(plan, constraints=(*plan.constraints, "no_agreeing"))
    if plan.mode != "companion":
        return plan
    # So a conversation does not open every reply the same way (tone check, 2026-10-11).
    said = [t.content for t in state.history if t.role == "assistant" and t.mode == "companion"]
    recent = (o for o in map(opener, said[-RECENT_OPENERS:]) if len(o.split()) == 3)
    plan = _listening(replace(plan, avoid_openers=tuple(dict.fromkeys(recent))), message, state)
    return _idea(plan, message, state)


def _idea(plan: Plan, message: str, state: ConversationState) -> Plan:
    """Every IDEA_EVERY-th reply to someone describing a difficulty offers one small idea with
    hopeful encouragement, unasked (demo testing, 2026-10-29). Not when the reply listens or
    is short, not on a thinking trap, and not soon after crisis support."""
    if not {"no_advice", "one_question"} <= set(plan.constraints) or plan.distortion_types:
        return plan
    if "post_crisis.cleared" in plan.reason_codes or extract(message).valence > -NEUTRAL:
        return plan
    recent = state.history[-IDEA_EVERY:]
    if any(t.role == "placeholder" or t.mode in ("crisis", "post_crisis") for t in recent):
        return plan
    # ponytail: the reply's number from the stored turn count (two turns per exchange), since
    # only the last few turns are loaded; a preface or placeholder shifts it by one.
    reply_number = (state.history[-1].seq if state.history else 0) // 2 + 1
    if reply_number % IDEA_EVERY:
        return plan
    swap = {"no_advice": ("offer_one_idea", "encourage")}
    rules = tuple(c for r in plan.constraints for c in swap.get(r, (r,)))
    return replace(plan, constraints=rules, reason_codes=(*plan.reason_codes, "idea.offered"))


def _listening(plan: Plan, message: str, state: ConversationState) -> Plan:
    """Swap the closing question for listening when asked, after LISTEN_AFTER questions in a
    row, or after a long message. Asked-for ideas and thinking traps keep their question."""
    if "one_question" not in plan.constraints or "offer_ideas" in plan.constraints:
        return plan
    if plan.distortion_types:
        return plan
    replies = [t.content.rstrip() for t in state.history if t.role == "assistant"]
    last = replies[-LISTEN_AFTER:]
    if _JUST_LISTEN.search(base_form(message)):
        why = "asked"
    elif replies and _short_statement(message):
        # "food", "ok thanks": one sentence back, not a paragraph (demo testing, 2026-10-29).
        rules = ("brief", *(c for c in plan.constraints if c in ("no_advice", "no_praise")))
        return replace(plan, constraints=rules,
                       reason_codes=(*plan.reason_codes, "brief.short_message"))  # fmt: skip
    elif len(last) == LISTEN_AFTER and all(r.endswith("?") for r in last):
        why = "two_questions"
    elif len(message.split()) >= LONG_MESSAGE_WORDS:
        why = "long_message"
    else:
        return plan
    rules = tuple("no_question" if c == "one_question" else c for c in plan.constraints)
    return replace(plan, constraints=rules, reason_codes=(*plan.reason_codes, f"listen.{why}"))


def _short_statement(message: str) -> bool:
    words = base_form(message).split()
    question = message.rstrip().endswith("?") or (bool(words) and words[0] in _QUESTION_WORDS)
    return 0 < len(words) <= BRIEF_WORDS and not question


def _plan(message: str, state: ConversationState, action: Action | None) -> Plan:
    if state.post_crisis:
        if not wants_to_continue(message):
            return Plan(mode="post_crisis", templated=True, template_id="post_crisis",
                        reason_codes=("post_crisis.hold",))  # fmt: skip
        return Plan(mode="companion", constraints=rules_for("companion", extract(message)),
                    reason_codes=("post_crisis.cleared",))  # fmt: skip

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
        return Plan(mode="companion", constraints=rules_for("companion", extract(message)),
                    assessment=step.record, card=step.card,
                    reason_codes=("planner.passthrough", "assessment.free_text"))  # fmt: skip

    if _IDENTITY.search(base_form(message)):
        return Plan(mode="companion", templated=True, text=TEMPLATES["identity"],
                    assessment=expired, reason_codes=("identity.asked",))  # fmt: skip
    signals = extract(message)
    if state.router.exercise is not None:  # no offer or explanation mid-exercise (design §3.2)
        return _routed(signals, state, now, expired)
    offer = trigger.decide(state.history, message, state.assessments, now)
    item = _explanation(message, signals, state.router)
    if offer is not None and (item is None or offer.explicit):
        plan = _from_step(flow.offer(offer.instrument, offer.reason, now), "assessment.offer")
        if item is None:
            return plan
        # Asked for a questionnaire and cued an explanation: the item comes first, as its own
        # message, then the offer (Smriti, 2026-10-11).
        rs, codes = _after_item(state.router, item)
        return replace(plan, preface=item.text, router_state=rs,
                       reason_codes=(*plan.reason_codes, *codes))  # fmt: skip
    if item is not None:
        rs, codes = _after_item(state.router, item)
        return Plan(mode="psychoed", constraints=CONSTRAINTS["psychoed"], snippet=item.text,
                    router_state=rs, assessment=expired, reason_codes=codes)  # fmt: skip
    return _routed(signals, state, now, expired)


def _explanation(message: str, signals: Signals, rs: RouterState) -> psychoed.Item | None:
    """The vetted item for a psychoeducation cue; acute overwhelm needs grounding first."""
    if not signals.psychoed_cue or signals.overwhelm >= router_config().acute_threshold:
        return None
    return psychoed.select(message, rs.psychoed_shown)


def _after_item(rs: RouterState, item: psychoed.Item) -> tuple[RouterState, tuple[str, ...]]:
    codes: tuple[str, ...] = (f"psychoed.{item.id}",)
    if rs.offered is not None:  # typing over an exercise offer is "not now" (router rule)
        rs = replace(rs, offered=None, challenger=None, streak=0)
        codes = (*codes, "exercise.offer_lapsed")
    return replace(rs, psychoed_shown=rs.psychoed_shown | {item.id}), codes


def _routed(
    signals: Signals,
    state: ConversationState,
    now: datetime.datetime,
    expired: AssessmentRecord | None,
) -> Plan:
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
        mode = rs.current
        text, rs, card = exercise.deliver(rs)
        return _step_plan(mode, decision, text, rs, card, codes, expired)
    if decision.offer is not None:
        t = exercise.technique_for(decision.offer)
        return Plan(mode=decision.mode, templated=True, text=t.offer,
                    exercise_card=ExerciseCard("offer", decision.offer, t.name),
                    router_state=rs, route=decision, assessment=expired,
                    reason_codes=tuple(codes))  # fmt: skip
    return Plan(mode=decision.mode, constraints=rules_for(decision.mode, signals),
                router_state=rs, route=decision, assessment=expired,
                reason_codes=tuple(codes))  # fmt: skip


def _step_plan(
    mode: Mode,
    decision: RouteDecision | None,
    text: str,
    rs: RouterState,
    card: ExerciseCard | None,
    codes: Sequence[str],
    expired: AssessmentRecord | None = None,
) -> Plan:
    # The mode is the one the step belongs to, even on the last step (rs is companion again).
    return Plan(mode=mode, constraints=STEP_CONSTRAINTS, snippet=text, exercise_card=card,
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
    mode = rs.current
    text, rs, card = exercise.deliver(rs)
    # They just pressed "Yes": nothing to respond to, so the first step is shown as written.
    return replace(_step_plan(mode, None, text, rs, card, ("exercise.accepted",)),
                   templated=True, text=text)  # fmt: skip


def with_thinking_trap(plan: Plan, message: str) -> Plan:
    """A reply to a thinking trap validates the feeling, then asks one Socratic question, and
    never agrees with the distortion; the guard gets the distorted claim (design §8)."""
    found = extract(message).distortion_types
    if not found:
        return plan
    rules = plan.constraints + tuple(r for r in DISTORTION_RULES if r not in plan.constraints)
    return replace(plan, constraints=rules, distortion_types=found, claims=claims(message))


def rules_for(mode: str, signals: Signals) -> tuple[str, ...]:
    rules = CONSTRAINTS.get(mode, ())
    if mode == "companion" and signals.asks_advice:  # advice was asked for (FR-CMP-2)
        rules = tuple("offer_ideas" if r == "no_advice" else r for r in rules)
    return rules


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
        return Plan(mode="companion", constraints=CONSTRAINTS["companion"], assessment=step.record,
                    card=step.card, reason_codes=(code,))  # fmt: skip
    return Plan(mode="assessment", templated=True, text=step.text, preface=step.preface,
                assessment=step.record, card=step.card, reason_codes=(code,))  # fmt: skip
