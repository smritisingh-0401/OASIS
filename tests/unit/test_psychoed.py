"""Psychoeducation: cue detection, item selection, content checks and planner precedence.

The trigger set must fire and pick the expected item; the ordinary-talk set must stay quiet
(FR-PSY-2). Every item carries source, reading level, version and review status (FR-PSY-3).
"""

from __future__ import annotations

import datetime
import pathlib
from typing import Any

import pytest
import yaml

from oasis.assessment.trigger import Offer
from oasis.core import planner
from oasis.core.planner import plan_turn
from oasis.core.signals import extract
from oasis.llm.prompt import build_messages
from oasis.psychoed.selector import MAX_GRADE, load_all, parse, reading_grade, select
from oasis.router.exercise import technique_for
from oasis.router.router import dump_state, load_state
from oasis.types import AssessmentRecord, ConversationState, Plan, RouterState

DATA = pathlib.Path(__file__).parents[1] / "data" / "psychoed"
TRIGGERS = yaml.safe_load((DATA / "trigger.yaml").read_text(encoding="utf-8"))["messages"]
ORDINARY = yaml.safe_load((DATA / "ordinary.yaml").read_text(encoding="utf-8"))["messages"]
NOW = datetime.datetime(2026, 10, 11, 12, 0, tzinfo=datetime.UTC)
ITEMS = {i.id: i for i in load_all()}


def state(rs: RouterState | None = None, **kw: Any) -> ConversationState:
    return ConversationState(now=NOW, router=rs or RouterState(), **kw)


# --- cue detection and selection ------------------------------------------------------


@pytest.mark.parametrize("case", TRIGGERS, ids=lambda c: c["message"][:40])
def test_trigger_set_fires_and_picks_the_expected_item(case: dict[str, str]) -> None:
    assert extract(case["message"]).psychoed_cue
    item = select(case["message"], frozenset())
    assert item is not None
    assert item.id == case["item"]


@pytest.mark.parametrize("message", ORDINARY)
def test_ordinary_talk_stays_quiet(message: str) -> None:
    assert not extract(message).psychoed_cue


def test_an_item_is_shown_once_per_session() -> None:
    assert select("what's wrong with me?", frozenset({"general"})) is None


def test_a_shown_topic_falls_back_to_the_general_item() -> None:
    item = select("why can't I sleep, is something wrong with me", frozenset({"sleep"}))
    assert item is not None
    assert item.id == "general"


# --- content checks (FR-PSY-3, rules CL6) -----------------------------------------------


def test_every_item_has_provenance_and_is_flagged_for_review() -> None:
    assert len(ITEMS) == 11
    for item in ITEMS.values():
        assert all((item.source, item.version, item.text))
        assert item.review_status == "needs_clinician_review"
        assert "nhs.uk" in item.source or "who.int" in item.source


def test_every_item_reads_at_or_below_the_target_grade() -> None:
    for item in ITEMS.values():
        assert item.reading_level == round(reading_grade(item.text), 1)
        assert item.reading_level <= MAX_GRADE


def test_reading_grade_rises_with_longer_words_and_sentences() -> None:
    plain = reading_grade("The cat sat on the mat. It was warm.")
    dense = reading_grade(
        "Psychological distress frequently accompanies considerable occupational "
        "uncertainty, particularly following organisational restructuring."
    )
    assert plain < 4 < 12 < dense
    assert reading_grade("") == 0.0


DENSE = (
    "Notwithstanding considerable interdisciplinary disagreement, contemporary "
    "epidemiological investigations consistently demonstrate substantial comorbidity."
)


def _raw(**item_overrides: Any) -> dict[str, Any]:
    text = "Most people feel low sometimes. It often gets better."
    general = {"id": "general", "topic": "general", "text": text,
               "reading_level": round(reading_grade(text), 1), "cues": [],
               "source": "https://www.nhs.uk/x", "version": "1",
               "review_status": "needs_clinician_review"}  # fmt: skip
    first = {**general, "id": "sleep", "topic": "sleep", "cues": [r"\bsleep\b"]}
    first.update(item_overrides)
    return {"version": "2026.10.0", "review_status": "needs_clinician_review",
            "items": [first, general]}  # fmt: skip


def test_parse_accepts_a_valid_file() -> None:
    assert [i.id for i in parse(_raw())] == ["sleep", "general"]


@pytest.mark.parametrize("override", [
    {"source": ""},
    {"version": None},
    {"review_status": "clinician_reviewed_maybe"},
    {"reading_level": 1.0},
    {"text": DENSE, "reading_level": round(reading_grade(DENSE), 1)},  # above the target
    {"cues": [r"\b(unclosed"]},
    {"cues": "sleep"},
    {"cues": []},  # a second item without cues: two general items
    {"id": "general"},  # duplicate id
])  # fmt: skip
def test_parse_rejects_invalid_items(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="psychoed"):
        parse(_raw(**override))


def test_parse_rejects_a_file_without_a_general_item() -> None:
    raw = _raw()
    raw["items"] = raw["items"][:1]
    with pytest.raises(ValueError, match="general"):
        parse(raw)


def test_parse_rejects_a_file_without_review_status() -> None:
    raw = _raw()
    del raw["review_status"]
    with pytest.raises(ValueError, match="psychoed"):
        parse(raw)


# --- planner precedence -----------------------------------------------------------------


def test_a_cue_gets_one_vetted_item_for_the_llm_to_phrase() -> None:
    plan = plan_turn("what's wrong with me?", state())
    assert plan.mode == "psychoed"
    assert plan.snippet == ITEMS["general"].text
    assert plan.constraints == ("no_diagnosis", "use_snippet_only")
    assert not plan.templated
    assert "psychoed.general" in plan.reason_codes
    assert plan.router_state is not None
    assert plan.router_state.psychoed_shown == frozenset({"general"})


def test_a_repeated_cue_falls_through_to_the_router() -> None:
    first = plan_turn("what's wrong with me?", state())
    again = plan_turn("what's wrong with me?", state(first.router_state))
    assert again.mode == "companion"
    assert again.router_state is not None
    assert again.router_state.psychoed_shown == frozenset({"general"})


def test_an_explicit_screening_request_gets_the_item_then_the_offer() -> None:
    message = "what's wrong with me, can I take a depression test?"
    item = select(message, frozenset())
    assert item is not None
    plan = plan_turn(message, state())
    assert plan.mode == "assessment"
    assert plan.card is not None
    assert plan.card.step == "offer"
    assert plan.preface == item.text
    assert plan.router_state is not None
    assert item.id in plan.router_state.psychoed_shown
    assert f"psychoed.{item.id}" in plan.reason_codes


def test_psychoeducation_wins_over_an_unprompted_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(planner.trigger, "decide", lambda *a: Offer("PHQ9", "{}"))
    plan = plan_turn("what's wrong with me?", state())
    assert plan.mode == "psychoed"
    assert plan.card is None


def test_no_psychoeducation_mid_exercise() -> None:
    rs = RouterState(current="cbt", exercise=technique_for("cbt").id, step=1,
                     consented=frozenset({"cbt"}))  # fmt: skip
    plan = plan_turn("is it normal to feel anxious all the time?", state(rs))
    assert plan.mode == "cbt"
    assert plan.snippet == technique_for("cbt").steps[1]


def test_acute_overwhelm_goes_to_grounding_not_an_explanation() -> None:
    rs = RouterState(psychoed_shown=frozenset({"panic"}))
    plan = plan_turn("is this a panic attack? I can't breathe, everything is too much", state(rs))
    assert plan.mode == "grounding"
    assert plan.router_state is not None
    assert plan.router_state.psychoed_shown == frozenset({"panic"})  # kept by the override


def test_an_open_exercise_offer_lapses() -> None:
    rs = RouterState(challenger="cbt", streak=3, offered="cbt")
    plan = plan_turn("what's wrong with me?", state(rs))
    assert plan.mode == "psychoed"
    assert plan.router_state is not None
    assert (plan.router_state.offered, plan.router_state.streak) == (None, 0)
    assert "exercise.offer_lapsed" in plan.reason_codes


def test_post_crisis_and_open_questionnaires_come_first() -> None:
    assert plan_turn("what's wrong with me?", state(post_crisis=True)).mode == "post_crisis"
    rec = AssessmentRecord("a1", "PHQ9", "in_progress", "{}", NOW.isoformat())
    plan = plan_turn("what's wrong with me?", state(assessments=(rec,)))
    assert "assessment.free_text" in plan.reason_codes


# --- router memory and prompt ------------------------------------------------------------


def test_shown_items_survive_the_router_memory_round_trip() -> None:
    rs = RouterState(psychoed_shown=frozenset({"sleep", "general"}))
    assert load_state(dump_state(rs)) == rs
    assert load_state('{"psychoed_shown": [1]}') == RouterState()


def test_the_prompt_asks_for_a_plain_explanation_of_the_item() -> None:
    plan = Plan(mode="psychoed", constraints=("no_diagnosis",), snippet="Stress is common.")
    system = build_messages(plan, [], "why", history_turns=6)[0].content
    assert "- script: Stress is common." in system
    assert "without diagnosing" in system
    assert "Guide them through" not in system


def test_parse_rejects_a_general_item_that_is_not_last() -> None:
    raw = _raw()
    raw["items"].reverse()  # the general item would answer every cue before any topic
    with pytest.raises(ValueError, match="last"):
        parse(raw)
