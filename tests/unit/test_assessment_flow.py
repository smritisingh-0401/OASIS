"""Assessment state machine through the planner (design §4.1-4.2, rules S11).

Offer -> consent/decline -> items -> functional question -> score -> result, with pause,
resume, abort and PHQ-9 item-9 escalation.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import replace

import pytest

from oasis.assessment.instruments import instrument
from oasis.core.planner import plan_turn
from oasis.types import AssessmentAction, AssessmentRecord, ConversationState, Plan

NOW = datetime.datetime(2026, 10, 8, 12, 0, tzinfo=datetime.UTC)
PHQ9 = instrument("PHQ9")
GAD7 = instrument("GAD7")


def _state(*records: AssessmentRecord, now: datetime.datetime = NOW) -> ConversationState:
    return ConversationState(assessments=records, now=now)


def _act(kind: str, value: int | None = None, rec: AssessmentRecord | None = None,
         item: int | None = None) -> AssessmentAction:  # fmt: skip
    return AssessmentAction(kind, value, rec.instrument if rec else None, item)  # type: ignore[arg-type]


def _offer(inst_id: str = "PHQ9") -> AssessmentRecord:
    plan = plan_turn(f"can I take the {'phq-9' if inst_id == 'PHQ9' else 'gad-7'}?", _state())
    assert plan.assessment is not None
    return plan.assessment


def _accepted(inst_id: str = "PHQ9") -> AssessmentRecord:
    rec = _offer(inst_id)
    plan = plan_turn("Yes", _state(rec), _act("accept", rec=rec))
    assert plan.assessment is not None
    return plan.assessment


def _answer(rec: AssessmentRecord, value: int) -> Plan:
    item = len(rec.answers) + 1
    inst = instrument(rec.instrument)
    label = inst.options[value]
    return plan_turn(label, _state(rec), _act("answer", value, rec, item))


def _answer_all(rec: AssessmentRecord, values: list[int]) -> tuple[AssessmentRecord, Plan]:
    plan = Plan(mode="assessment")
    for v in values:
        plan = _answer(rec, v)
        assert plan.assessment is not None
        rec = plan.assessment
    return rec, plan


# --- offer and consent ---------------------------------------------------------------


def test_explicit_request_offers_with_a_stored_reason() -> None:
    plan = plan_turn("could we do a depression questionnaire?", _state())
    assert plan.mode == "assessment"
    assert plan.templated
    assert plan.card is not None
    assert plan.card.step == "offer"
    assert plan.assessment is not None
    assert plan.assessment.status == "offered"
    assert plan.assessment.instrument == "PHQ9"
    assert json.loads(plan.assessment.offer_reason)["reason"] == "explicit_request"


def test_anxiety_request_offers_gad7() -> None:
    assert _offer("GAD7").instrument == "GAD7"


def test_accept_shows_the_first_item_verbatim() -> None:
    rec = _offer()
    plan = plan_turn("Yes", _state(rec), _act("accept", rec=rec))
    assert plan.assessment is not None
    assert plan.assessment.status == "in_progress"
    assert plan.card is not None
    assert (plan.card.step, plan.card.item, plan.card.item_count) == ("item", 1, 9)
    assert plan.card.options == PHQ9.options
    assert plan.text is not None
    # The instruction comes once, as its own message before the first question; not on the card.
    assert plan.preface == PHQ9.stem
    assert plan.text.startswith("Question 1 of 9: ")
    assert PHQ9.items[0] in plan.text
    assert plan.assessment is not None
    assert _answer(plan.assessment, 0).preface is None


def test_decline_is_stored_with_reason_and_starts_a_cooldown() -> None:
    rec = _offer()
    plan = plan_turn("Not now", _state(rec), _act("decline", rec=rec))
    assert plan.assessment is not None
    assert plan.assessment.status == "declined"
    reason = json.loads(plan.assessment.offer_reason)
    assert reason["reason"] == "explicit_request"
    assert reason["declined_by"] == "button"
    unprompted = plan_turn("I've been feeling hopeless for weeks", _state(plan.assessment))
    assert unprompted.card is None  # no new offer within 24 h
    asked = plan_turn("can I take a depression test?", _state(plan.assessment))
    assert asked.card is not None  # but the user can always ask
    assert asked.card.step == "offer"


def test_ignoring_an_offer_counts_as_not_now() -> None:
    rec = _offer()
    plan = plan_turn("anyway, about my week", _state(rec))
    assert plan.mode == "companion"
    assert plan.assessment is not None
    assert plan.assessment.status == "declined"
    assert json.loads(plan.assessment.offer_reason)["declined_by"] == "free_text"


# --- items, functional question and result --------------------------------------------


def test_full_phq9_asks_the_functional_question_then_scores() -> None:
    rec, plan = _answer_all(_accepted(), [1, 2, 1, 2, 1, 1, 0, 1, 0])
    assert rec.status == "in_progress"
    assert plan.card is not None
    assert plan.card.step == "functional"
    assert plan.card.options == PHQ9.functional_options

    plan = plan_turn("Somewhat difficult", _state(rec), _act("answer", 1, rec, None))
    assert plan.assessment is not None
    done = plan.assessment
    assert (done.status, done.total, done.band, done.functional) == ("scored", 9, "mild", 1)
    assert done.completed_at is not None
    assert plan.card is not None
    assert (plan.card.step, plan.card.total, plan.card.band) == ("result", 9, "mild")
    assert plan.text is not None
    assert "9" in plan.text
    assert "not a diagnosis" in plan.text


def test_gad7_scores_after_the_last_item() -> None:
    rec, plan = _answer_all(_accepted("GAD7"), [3, 3, 3, 3, 3, 0, 0])
    assert (rec.status, rec.total, rec.band) == ("scored", 15, "severe")
    assert plan.card is not None
    assert plan.card.step == "result"


def test_stale_or_repeated_click_changes_nothing() -> None:
    rec, _ = _answer_all(_accepted(), [1, 1])
    plan = plan_turn("Several days", _state(rec), _act("answer", 1, rec, item=1))
    assert plan.assessment is None  # nothing to persist
    assert plan.card is not None
    assert plan.card.item == 3  # the current question is shown again


# --- item 9 ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", [1, 2, 3])
def test_item9_positive_escalates_regardless_of_total(value: int) -> None:
    rec, _ = _answer_all(_accepted(), [0] * 8)
    plan = _answer(rec, value)
    assert plan.mode == "crisis"
    assert plan.assessment is not None
    assert plan.assessment.status == "escalated"
    assert plan.assessment.total is None  # never scored or shown that turn
    assert plan.card is None


def test_item9_zero_does_not_escalate() -> None:
    rec, _ = _answer_all(_accepted(), [3] * 8)
    plan = _answer(rec, 0)
    assert plan.mode == "assessment"
    assert plan.card is not None
    assert plan.card.step == "functional"


# --- pause, resume, abort ---------------------------------------------------------------


def test_pause_and_resume_keep_answers() -> None:
    rec, _ = _answer_all(_accepted(), [2, 2, 2])
    paused = plan_turn("Pause", _state(rec), _act("pause", rec=rec))
    assert paused.assessment is not None
    assert paused.assessment.status == "paused"
    assert paused.card is not None
    assert paused.card.step == "paused"

    resumed = plan_turn("Resume", _state(paused.assessment), _act("resume", rec=rec))
    assert resumed.assessment is not None
    assert resumed.assessment.status == "in_progress"
    assert resumed.assessment.answers == (2, 2, 2)
    assert resumed.card is not None
    assert resumed.card.item == 4
    assert resumed.preface == PHQ9.stem  # re-oriented after a break


def test_free_text_mid_questionnaire_pauses_and_is_answered_normally() -> None:
    rec, _ = _answer_all(_accepted(), [1])
    plan = plan_turn("sorry, can I ask something first?", _state(rec))
    assert plan.mode == "companion"
    assert plan.assessment is not None
    assert plan.assessment.status == "paused"
    assert plan.card is not None
    assert plan.card.step == "paused"


def test_abort_discards_answers_without_scoring() -> None:
    rec, _ = _answer_all(_accepted(), [3, 3, 3, 3])
    plan = plan_turn("Stop", _state(rec), _act("abort", rec=rec))
    assert plan.assessment is not None
    assert (plan.assessment.status, plan.assessment.answers) == ("aborted", ())
    assert plan.assessment.total is None


def test_paused_questionnaire_expires_after_24_hours() -> None:
    rec, _ = _answer_all(_accepted(), [1, 1])
    paused = replace(rec, status="paused")
    later = NOW + datetime.timedelta(hours=25)
    plan = plan_turn("hello again", _state(paused, now=later))
    assert plan.assessment is not None
    assert (plan.assessment.status, plan.assessment.answers) == ("aborted", ())
    expired = plan_turn("Resume", _state(plan.assessment, now=later), _act("resume", rec=rec))
    assert expired.template_id == "assessment_unavailable"
    assert expired.assessment is None


def test_action_without_an_open_assessment_gets_a_fixed_reply() -> None:
    plan = plan_turn("Several days", _state(), AssessmentAction("answer", 1, "PHQ9", 1))
    assert plan.templated
    assert plan.template_id == "assessment_unavailable"
    assert plan.assessment is None


def test_post_crisis_mode_wins_over_an_open_assessment() -> None:
    rec = _accepted()
    state = replace(_state(rec), post_crisis=True)
    assert plan_turn("Several days", state, _act("answer", 1, rec, 1)).mode == "post_crisis"


def test_stale_clicks_while_paused_or_offered_change_nothing() -> None:
    rec, _ = _answer_all(_accepted(), [1])
    paused = replace(rec, status="paused")
    plan = plan_turn("Several days", _state(paused), _act("answer", 1, rec, 2))
    assert plan.assessment is None
    assert plan.card is not None
    assert plan.card.step == "paused"

    offered = _offer()
    plan = plan_turn("Several days", _state(offered), _act("answer", 1, offered, 1))
    assert plan.assessment is None
    assert plan.card is not None
    assert plan.card.step == "offer"


def test_free_text_while_paused_is_a_normal_turn() -> None:
    rec, _ = _answer_all(_accepted(), [1])
    plan = plan_turn("just chatting", _state(replace(rec, status="paused")))
    assert (plan.mode, plan.assessment, plan.card) == ("companion", None, None)


def test_unknown_instrument_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown instrument"):
        instrument("BDI")
