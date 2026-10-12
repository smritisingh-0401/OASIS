"""Planner with the router wired in (design §6): consent, exercises, acute override, precedence."""

from __future__ import annotations

import datetime

from oasis.assessment.trigger import config as trigger_config
from oasis.core.planner import plan_turn
from oasis.core.templates import TEMPLATES
from oasis.router.exercise import technique_for
from oasis.router.weights import config
from oasis.types import (
    AssessmentRecord,
    ConversationState,
    ExerciseAction,
    Plan,
    RouterState,
)

NOW = datetime.datetime(2026, 10, 11, 12, 0, tzinfo=datetime.UTC)
N = config().hysteresis_turns
DISTORTED = "I'm such a failure, I always mess everything up"
ACUTE = "I can't breathe, everything is too much, I'm falling apart"
FRESH = RouterState()


def state(rs: RouterState = FRESH, **kw: object) -> ConversationState:
    return ConversationState(now=NOW, router=rs, **kw)  # type: ignore[arg-type]


def turns(messages: list[str], rs: RouterState = FRESH) -> list[Plan]:
    plans = []
    for m in messages:
        plan = plan_turn(m, state(rs))
        plans.append(plan)
        rs = plan.router_state or rs
    return plans


def offered() -> Plan:
    plan = turns([DISTORTED] * N)[-1]
    assert plan.router_state is not None
    assert plan.router_state.offered == "cbt"
    return plan


def test_reworded_self_criticism_reaches_the_thought_check_offer() -> None:
    # The manual test (2026-10-12) that never reached CBT: only the first message counted.
    # The long second message falls just short of the margin, which holds the streak.
    plans = turns(["I'm such a failure, I always mess everything up",
                   "I always do something wrong, feeling very bad right now",
                   "It feels like i am carrying a burden of my failure"])  # fmt: skip
    assert [p.router_state.offered if p.router_state else None for p in plans] == [
        None, None, "cbt"]  # fmt: skip


def test_a_sustained_cue_ends_in_a_consent_offer() -> None:
    plans = turns([DISTORTED] * N)
    assert all(p.mode == "companion" for p in plans)
    assert all(p.exercise_card is None for p in plans[:-1])
    offer = plans[-1]
    assert offer.templated
    assert offer.text == technique_for("cbt").offer
    assert offer.exercise_card is not None
    assert (offer.exercise_card.step, offer.exercise_card.mode) == ("offer", "cbt")
    assert "router.offer_structured_mode" in offer.reason_codes


def test_accepting_starts_the_exercise_with_its_first_step() -> None:
    rs = offered().router_state
    assert rs is not None
    plan = plan_turn("Yes, let's try", state(rs), ExerciseAction("accept"))
    t = technique_for("cbt")
    assert plan.mode == "cbt"
    assert plan.snippet == t.steps[0]
    assert plan.exercise_card is not None
    assert (plan.exercise_card.step, plan.exercise_card.item) == ("active", 1)
    assert plan.router_state is not None
    assert "cbt" in plan.router_state.consented
    assert set(plan.constraints) >= {"follow_script", "one_step"}


def test_declining_keeps_talking_and_clears_the_offer() -> None:
    rs = offered().router_state
    assert rs is not None
    plan = plan_turn("Not now", state(rs), ExerciseAction("decline"))
    assert plan.templated
    assert plan.text == TEMPLATES["exercise_declined"]
    assert plan.exercise_card is None
    assert plan.router_state is not None
    assert plan.router_state.offered is None


def test_typing_over_an_offer_counts_as_not_now() -> None:
    rs = offered().router_state
    assert rs is not None
    plan = plan_turn("hmm, I'm not sure", state(rs))
    assert plan.router_state is not None
    assert plan.router_state.offered is None
    assert plan.exercise_card is None
    assert "exercise.offer_lapsed" in plan.reason_codes


def test_each_message_moves_the_exercise_one_step_until_it_ends() -> None:
    t = technique_for("cbt")
    rs = plan_turn("Yes", state(offered().router_state or RouterState()),
                   ExerciseAction("accept")).router_state  # fmt: skip
    assert rs is not None
    for k in range(2, len(t.steps) + 1):
        plan = plan_turn("okay, I've thought about it", state(rs))
        assert plan.mode == "cbt"
        assert plan.snippet == t.steps[k - 1]
        rs = plan.router_state
        assert rs is not None
    assert plan.exercise_card is None
    assert rs.exercise is None
    after = plan_turn("thanks, that helped a bit", state(rs))
    assert after.snippet is None


def test_a_strong_other_cue_does_not_interrupt_the_exercise() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    plan = plan_turn("I'm so angry I want to smash something, I can't control it", state(rs))
    assert plan.mode == "cbt"
    assert plan.snippet == technique_for("cbt").steps[1]
    assert "router.mid_exercise_hold" in plan.reason_codes


def test_stop_button_ends_the_exercise() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    plan = plan_turn("Stop", state(rs), ExerciseAction("stop"))
    assert plan.text == TEMPLATES["exercise_stopped"]
    assert plan.exercise_card is None
    assert plan.router_state is not None
    assert plan.router_state.exercise is None


def test_typed_opt_out_ends_the_exercise() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    plan = plan_turn("Can we stop the exercise?", state(rs))
    assert plan.router_state is not None
    assert plan.router_state.exercise is None
    assert plan.snippet is None
    assert "exercise.opt_out" in plan.reason_codes


def test_a_button_with_nothing_to_act_on_is_answered_safely() -> None:
    for action in ("accept", "decline", "stop"):
        plan = plan_turn("Yes", state(), ExerciseAction(action))  # type: ignore[arg-type]
        assert plan.text == TEMPLATES["exercise_unavailable"]
        assert plan.exercise_card is None


def test_acute_overwhelm_starts_grounding_at_once_without_asking() -> None:
    plan = plan_turn(ACUTE, state())
    g = technique_for("grounding")
    assert plan.mode == "grounding"
    assert plan.snippet == g.steps[0]
    assert plan.exercise_card is not None
    assert plan.exercise_card.step == "active"
    assert plan.router_state is not None
    assert plan.router_state.exercise == g.id
    assert "router.acute_override" in plan.reason_codes


def test_acute_overwhelm_mid_grounding_carries_on_with_the_next_step() -> None:
    first = plan_turn(ACUTE, state())
    assert first.router_state is not None
    second = plan_turn(ACUTE, state(first.router_state))
    assert second.snippet == technique_for("grounding").steps[1]


def test_every_routed_plan_carries_the_full_decision() -> None:
    plan = plan_turn(DISTORTED, state())
    assert plan.route is not None
    assert {s.mode for s in plan.route.scores} == {"companion", "cbt", "dbt", "mindfulness"}
    assert plan.route.scores[0].contributions


def test_mode_constraints_follow_the_prompt_table() -> None:
    companion = plan_turn("I just want to vent about my day", state())
    assert set(companion.constraints) == {
        "validate_first",
        "one_question",
        "no_advice",
        "no_praise",
    }
    cbt = plan_turn(DISTORTED, state(RouterState(current="cbt", consented=frozenset({"cbt"}))))
    assert set(cbt.constraints) == {"validate_first", "one_question", "socratic"}


# --- precedence ----------------------------------------------------------------------------


def test_no_screening_offer_mid_exercise() -> None:
    rs = RouterState(current="cbt", exercise="thought_check", step=1, consented=frozenset({"cbt"}))
    plan = plan_turn("can I take a depression test?", state(rs))
    assert plan.assessment is None
    assert plan.snippet == technique_for("cbt").steps[1]


def test_screening_offer_outranks_the_router() -> None:
    plan = plan_turn("can I take a depression test?", state())
    assert plan.assessment is not None
    assert plan.router_state is None


def test_an_open_questionnaire_outranks_the_router() -> None:
    rec = AssessmentRecord("a1", "PHQ9", "in_progress", "{}", NOW.isoformat())
    plan = plan_turn(DISTORTED, state(assessments=(rec,)))
    assert plan.router_state is None
    assert plan.exercise_card is None


def test_post_crisis_mode_outranks_everything() -> None:
    plan = plan_turn(ACUTE, state(post_crisis=True))
    assert plan.mode == "post_crisis"
    assert plan.router_state is None


def test_a_recent_moderate_phq9_result_feeds_the_router() -> None:
    when = (NOW - datetime.timedelta(days=2)).isoformat()
    rec = AssessmentRecord("a1", "PHQ9", "scored", "{}", when, total=12, band="moderate",
                           completed_at=when)  # fmt: skip
    plan = plan_turn("I don't know", state(assessments=(rec,)))
    assert plan.route is not None
    cbt = next(s for s in plan.route.scores if s.mode == "cbt")
    assert {c.signal: c.value for c in cbt.contributions}["phq_moderate_plus"] > 0


def test_an_old_phq9_result_does_not() -> None:
    when = (NOW - trigger_config().repeat_after - datetime.timedelta(days=1)).isoformat()
    rec = AssessmentRecord("a1", "PHQ9", "scored", "{}", when, total=12, band="moderate",
                           completed_at=when)  # fmt: skip
    plan = plan_turn("I don't know", state(assessments=(rec,)))
    assert plan.route is not None
    cbt = next(s for s in plan.route.scores if s.mode == "cbt")
    assert {c.signal: c.value for c in cbt.contributions}["phq_moderate_plus"] == 0
